# 05 — Persistence, Ops, and Quality

What the harness stores, what it emits off-box, and how a change is built and tested. Every claim below traces to a file opened for this digest — cited paths are repo-relative and exist in this checkout.

## 1. Session log

### 1.1 Format and durability seam

The durability seam is `SessionPersistence` (`ctx.sessionPersistence`), described in `docs/subsystems/persistence.md`. It exposes `create`/`open`/`stat`/`list` over the existing `SessionEvent` log — there is no parallel persisted event type. `create` and `open` return a per-session `SessionHandle` (`read`/`append`/`flush`/`close`) that owns all log access and enforces single-writer ownership: a second `open(id, 'write')` while a write handle is active rejects with `SessionAlreadyOwnedError`.

The shipped provider is `packages/session/session-persistence-jsonl` (`docs/subsystems/persistence.md`, "The backend" section):

- **Format**: append-only logical JSONL log per session, stored as **checksummed concatenated Zstandard frames by default**, or raw lines by configuration.
- **Durability**: crash-safe atomic materialization, per-batch `fsync` appends, torn-tail truncation before the first new append.
- **Location artifact**: `SessionLocation` (kind `jsonl`) supplies the absolute transcript path inside the session's project/session directory — but this is refusal-diagnostics only (surfaced by `SessionFormatUnsupportedError`), never a consumer-facing read path; ordinary reads always go through `SessionHandle.read`.

### 1.2 The flush checkpoint (what is durable, when)

Per `docs/subsystems/persistence.md` ("The flush checkpoint"):

- `append` is **best-effort**: on resolution the batch is accepted, ordered, and visible to reads on that backend instance, but only a resolved `flush` promises survival across a crash.
- `session/event` triggers a bounded internal batching window that starts one durable `append`; `session/flush` cancels the wait and drains to quiescence.
- A created session is observable in-process as soon as `create` resolves even if physical materialization is deferred; other processes see only materialized sessions. **A session that never materialized before a crash never existed.**
- `SessionHandle.close()` drains the routed buffer through still-open storage before releasing ownership.

### 1.3 Crash recovery / resume semantics

From `docs/subsystems/persistence.md` ("Crash recovery preserves an interrupted turn"):

- Persistence does **not** truncate or repair a log crashed mid-turn (open `turn/start`, no `turn/end`) — a turn can be huge (many steps, large tool output) and those events were already durably appended.
- Only the incomplete fragment of a torn physical tail — belonging to an `append` that never resolved — is discarded. The JSONL backend partially decodes a torn Zstandard frame and durably rewrites recovered complete records before the handle's first new append.
- **Repair is the reader's job.** Resume (agent-loop) reads the stored log through its write handle, computes `interruptedTurnClosers` (missing tool errors, any open `step/end`, a synthetic `turn/end { reason: { kind: 'interrupted' } }`), and appends them as an ordinary batch. `interrupted` is the one `TurnEndReason` no loop emits.
- Repair writes only under write ownership — a live session's write handle is held by its owner, so a concurrent read never races repair.
- Read-only observers (session-query) balance an interrupted cold log **in memory only**, writing nothing back.

### 1.4 Format version and release status

Per `docs/session-format-status.md`:

| Field | Value | Source |
|---|---|---|
| Checkout writer (`SESSION_FORMAT_VERSION`) | in `packages/core/session/src/types.ts` (hand-maintained current-writer number) | code constant |
| `latestFinalizedVersion` | `4` | `docs/session-format-status.md` finalization record |
| `latestReleasedVersion` | `3` | `docs/session-format-status.md` release record |
| Evidence tag | `dsh-v0.1.5-alpha.1` (tagged writer `packages/core/session/src/types.ts`) | same |

V4 has an accepted compatibility baseline (checkpoint `docs/persistence-changes/finalized/v4.json`) but is not yet the verified-published version; breaking changes require a higher writer version and their own header transition. The format references (`docs/persistence-changes/historical-formats/README.md`) document every integer from zero through the checkout writer.

### 1.5 `SessionHeader` — metadata beside the log

Per-session metadata travels separately from the event log (`docs/subsystems/persistence.md`, "`SessionHeader` — metadata beside the log", source `packages/core/session/src/types.ts`): `version`, `id`, `createdAt`, optional `cwd`, optional `parentSession`, `isSeeded` (fork lineage bit), optional `origin: 'subagent'`, optional `delegationDepth`, optional `agentPreset`. The header is never part of `SessionEventMap` and never reaches `deriveMessages()`.

### 1.6 Reading, querying, and repairing without going live

`docs/subsystems/session-query.md` documents `ctx.sessionQuery` (`packages/session-query/session-query`), the live-preferred query layer over persisted + in-memory sessions:

- `SessionRecord` exposes `live` (currently in `ctx.sessions`) and `persisted` (currently listed by the backend, including a created-but-unmaterialized session).
- `readSession(sessionId)` returns a `SessionLogSnapshot` — cloned header, `inheritedEventCount`, and the complete raw event log after **in-memory** interrupted-turn balancing and replay validation (writes nothing back, per section 1.3).
- `filterSessions`/`filterEvents` apply provider-independent AND/OR predicates; `searchSessions`/`searchEvents` are full-text (SQLite provider owns the index, `packages/session-query/session-query-sqlite`).
- `SessionLineageTrace`, `traceEvent`, `readEvent` (bounded windows) round out browsing without materializing a live agent.

Errors are a closed `SessionQueryErrorCode` union (e.g. `SESSION_QUERY_SESSION_NOT_FOUND`, `SESSION_QUERY_STALE_CURSOR`, `SESSION_QUERY_SEARCH_DISABLED`).

### 1.7 Session projections (derived read models, not the log itself)

`docs/subsystems/session-projection.md` describes `ctx.sessionProjections` (`packages/session/session-projection`): domains register a pure synchronous fold (`ProjectionDefinition`) driven off every committed `session/event`; `ctx.sessionProjectionCache` (`packages/session/session-projection-cache`) persists a version-stamped checkpoint per `(sessionId, key)` under the `session_projcache` storage domain (per-record layout — see section 2), checkpointed at session creation, `turn/end`, and session disposal, plus a throttled write-behind. Every durable checkpoint write is fail-soft (logs a warning, self-heals next write); this cache is a hint/cold-read accelerator, never the source of truth — the log always wins.

### Cannot / does not (session log)

- Cannot rewrite or truncate a crashed log's already-durable events — only the torn tail fragment is discarded.
- Cannot serve a `SessionFormatUnsupportedError` refusal by silently dropping unknown required events (`ignorable` marker required, or the build refuses the whole log).
- Historical v0/v1/v2 migration refuses an unknown type even when marked `ignorable`; only current-format restoration tolerates unknown-but-`ignorable` events.
- `SessionLocation` is not a query path — it exists only to name a raw log file in refusal diagnostics.

## 2. Storage, settings, credentials on disk

`docs/subsystems/storage.md` describes the non-session-log persistence seam: **`ctx.storage`** is a routing hub only (no I/O itself), backends register under names (`json` -> `packages/storage/storage-json`, `sqlite` -> `packages/storage/storage-sqlite`), and the sole shipped Consumer data form is **`ctx.storageDomain`** (also `ctx.storage.domain`, from `packages/storage/storage-domain`).

- A **domain** (`DomainSpec`) is declared once by its owning package: `name` (matches `UNIT_NAME_RE`, also the backend unit name), `version`, `layout` (`single` — one document for the whole unit, default; or `per-record` — one document per record, used by the projection cache), optional `compatibleVersions`, optional `invalidRecords: 'backup-and-skip'`, an optional `global` singleton slot, and `tables`.
- The `json` backend republishes one whole human-readable file per unit atomically; the `sqlite` backend stores one document per row in one database, for frequently updated data.
- Reads are synchronous from authoritative in-memory state; every write (`put`/`delete`/`update`/`global.set`) queues on a per-domain chain, reaches backend durability **first**, then mutates memory, then emits `domain/changed` — a rejected backend write leaves memory untouched.
- `domain/changed` is in-process only; cross-process change push is a documented limitation (`packages/storage/storage-domain/README.md`).

`docs/subsystems/spill.md` covers tool-output/session-reference spill artifacts — `ctx.spillStore.saveText`, shipped local backend `packages/spill/spill-local`: writes under `<root>/session-<hash>/<random>-<safeName>`, a **configured or lazily-created private (0700) root**, `sha256(sessionId)` session subdirectory, exclusive owner-only (`open(path, 'wx', 0o600)`) write to resist a planted symlink. `saveText` rejects on real storage failure (permissions, ENOSPC, backend unavailable); the policy consumer (`dsh-spill-policy`) treats a save failure as best-effort and keeps the original inline result.

### Paths under DSH_HOME

DSH_HOME is the harness home root (default `~/.dsh` — confirmed in `apps/desktop/README.md`, which repeatedly writes "normally `~/.dsh`"). Documented DSH_HOME-scoped paths, from `apps/desktop/README.md`:

| Path (relative to DSH_HOME) | Contents | Source |
|---|---|---|
| `dsh-runtimes/dsh-primary-runtime` | Offline-installed Python/Node/pnpm payload for `load_workspace_dependencies` (numpy, pandas, python-docx, python-pptx, openpyxl, Pillow, lxml, XlsxWriter) | `apps/desktop/README.md` |
| `profiles/desktop` | Desktop's exclusively owned profile: `dependencies` (pnpm-installed packages), `dsh.profile.bundles` (built-in bundles plus enabled plugins); CLI cannot boot or mutate this profile | `apps/desktop/README.md` |
| `.anonymous-user-id` | Random UUID identity used as the OTel Resource's `user.id` on session-telemetry exports; delete the file to reset identity | `apps/desktop/README.md` (via `packages/bundle/base/cordis.patch.yml` comment) |
| (root) | Sessions, settings, credentials, plugins — shared between CLI dsh and Desktop, but never executable packages, plugin activation, lockfiles, or `node_modules` | `apps/desktop/README.md` |

Desktop-specific isolation: Electron acquires a process-lifetime single-instance lock before any profile access and exclusively owns DSH_HOME/profiles/desktop; CLI and Desktop share supported product data under DSH_HOME but never executable state. On Windows, the uninstaller explicitly **never touches** the harness home (`~/.dsh` or DSH_HOME: "sessions, settings, credentials, plugins") — confirmed twice in `apps/desktop/README.md`. A DSH_HOME published as a Windows environment variable additionally protects any uninstall target overlapping it. Development builds default the Harness home to `apps/desktop/.desktop-build/development/home` instead, isolating dev sessions/settings/credentials from a real DSH_HOME; an explicit DSH_HOME env var overrides only that development home.

`docs/subsystems/workspace.md`: workspaces (directory-scoped session grouping) store their records through the storage-domain form (`ctx.workspaceRegistry`, `packages/workspace/workspace`) — not a separate file tree. `docs/subsystems/ssh.md` covers remote execution over an operator-owned SSH connection; it explicitly keeps the harness, model transport, and **session storage on the local host** — SSH providers extend filesystem/process access to a remote machine but do not relocate DSH_HOME or the session log.

### Cannot / does not (storage)

- The storage hub performs no I/O itself and enforces no backend choice — routing is each domain's own configuration.
- `domain/changed` never crosses process boundaries.
- Spill storage defines no retention policy, no tool-result replacement policy, and no retrieval/search API — those live in the consumer (`dsh-spill-policy`).
- Desktop's `profiles/desktop` is never accessible to the CLI profile, and vice versa for executable state.

## 3. Telemetry — what phones home by default, and how this bundle disables it

Two independent, non-overlapping telemetry seams exist upstream. **Neither is loaded by this bundle's default composition** in one case, and the other simply is not wired in at all.

### 3.1 `session-telemetry` (Session-log mirror)

`docs/subsystems/session-telemetry.md`: Service Definition plus capture coordinator `ctx.sessionTelemetry` (`packages/session/session-telemetry`) owns canonical-event capture, a redaction waterfall (`session-telemetry/record`), and the handoff cursor. Its **only shipped Service Provider** is `packages/session/session-telemetry-otel` — the OpenTelemetry JS SDK's log pipeline "configured verbatim." This is optional, not part of the agent-loop spine, and nothing in it reaches a model request.

Upstream `dsh-base` bundle default (confirmed in `packages/bundle/base/cordis.patch.yml`, around lines 190-211):

```yaml
- id: session-telemetry-otel
  name: '@deepseek-ai/dsh-session-telemetry-otel'
  config:
    mode: !!js process.env.DSH_TELEMETRY_MODE || 'FEEDBACK_ONLY'
    shutdownTimeoutMillis: 3000
    exporter:
      url: !!js process.env.DSH_TELEMETRY_OTLP_URL ?? 'https://harness-telemetry.deepseeksvc.com/v1/logs'
      compression: gzip
      timeoutMillis: 1000
    processor:
      scheduledDelayMillis: 10000
      maxQueueSize: 2048
```

- Default mode `FEEDBACK_ONLY`: per the accompanying comment, "OTel releases a Session-log prefix only after explicit user feedback, regardless of model provider. Ordinary activity never triggers capture." `SessionTelemetrySharingStatus` is `'full' | 'feedback-only' | 'disabled'`.
- Default OTLP target: `https://harness-telemetry.deepseeksvc.com/v1/logs`.
- `DSH_TELEMETRY_OTLP_URL` overrides the endpoint; `DSH_TELEMETRY_DISABLED` (any value, including `'0'`/`'false'`) opts the process out via launcher-level row disabling — the comment notes "config cannot disable a row."
- Exports carry DSH_HOME/.anonymous-user-id as the Resource's `user.id`.

**This bundle (plexar) disables it outright.** Confirmed in `packages/bundle/plexar/cordis.patch.yml`:

```yaml
- id: session-telemetry-otel
  disabled: true
```

So in the plexar-harness fork, `session-telemetry` has no active Service Provider at all — captured records never leave the process, redaction waterfall or not, because `emit()` is never reached by a mounted OTel backend.

### 3.2 `product-telemetry` (host analytics)

`docs/subsystems/product-telemetry.md`: `packages/host/product-telemetry-otel`'s `ctx.productTelemetry.emit(record)` sends explicitly selected analytics events via OTLP/HTTP; "No Session data or identifiers are collected automatically." `ProductTelemetryRecord` requires `eventName`, `body`, `timestamp`, optional `severityNumber`, optional scalar `attributes` — "no automatic device or account identity."

A grep of `packages/bundle/base/cordis.patch.yml` and `packages/bundle/plexar/cordis.patch.yml` for `product-telemetry`/`productTelemetry` returns no matches — this plugin is simply not composed into either bundle, so it never activates and sends nothing.

### 3.3 Net effect: nothing phones home by default in this bundle

- `session-telemetry-otel`: explicitly `disabled: true` in `packages/bundle/plexar/cordis.patch.yml`.
- `product-telemetry-otel`: not referenced by either `packages/bundle/base/cordis.patch.yml` or `packages/bundle/plexar/cordis.patch.yml` — not composed at all.
- The plexar bundle also disables DeepSeek-cloud-only rows unrelated to telemetry but worth noting as "nothing else phones home": `llm-deepseek`, `deepseek-llm-api-extensions`, `plugin-package-inventory-deepseek`, `session-log-deepseek`, `deepseek-account`, `web-search-deepseek` — all `disabled: true` in `packages/bundle/plexar/cordis.patch.yml`.
- Model traffic itself routes to the operator's own rig (`llm-pi-ai` provider `plexar`, `baseURL` defaulting to `https://plexar-llm.boord-its.com/v1`) — see section 7 Plexar notes.

### Cannot / does not (telemetry)

- `session-telemetry`'s redaction waterfall (`session-telemetry/record`) ships **no rules of its own** — with no listener mounted, records reach the backend exactly as captured; irrelevant here since no backend is mounted in this bundle.
- `product-telemetry` never collects Session data or identifiers automatically — only what a caller explicitly passes.
- Neither seam's `emit()` blocks the agent loop; both are fire-and-forget/enqueue-only per their contracts.

## 4. Token meter and cost accounting

`docs/subsystems/token-meter.md`: `ctx.tokenMeter` (`packages/llm/token-meter`) exposes `measure(session, requestHeader?) -> TokenMeasurement` — a detached, immutable replay snapshot at one consumed log revision (`logRevision`, "equal to the next unread event seq").

`TokenMeasurement` fields: `baseline` (`TokenMeasurementBaseline` — `'usage'` when a matching prior successful provider call's usage can be reused, `'estimated'` otherwise), `surfaceDeltaTokens` (signed repricing delta vs. baseline), `totalTokens` (non-negative current request-and-response pressure), `surfaceTokens` (sum of routed per-node prices), and `nodes: readonly TokenSurfaceNode[]` (positional, head-to-tail).

Each `TokenSurfaceNode` carries `seq`, `tokens` (route-priced — image occurrences priced via the routed adapter's declared visual pricing when present, otherwise the fixed heuristic), and `heuristicTokens` (route-independent fixed heuristic, used so the O(1) projection fold for replacement nodes stays consistent with its own appends). `estimateMessage(message)` is the pure per-message heuristic estimator, independent of any route.

Pricing is resolved through the effective envelope's routed provider/model via `ctx.llm`; routes/compositions without declared pricing fall back to the fixed heuristic. A later successful request replaces the earlier usage anchor.

### Cannot / does not (token meter)

- Does not track cumulative session-lifetime spend/cost in dollars — it measures token pressure per snapshot, not a running ledger.
- Does not reprice historical nodes independently of the current route selection — `surfaceTokens`/`nodes` describe the **current** surface under the **current** routed model.

## 5. Build and test

Commands and Node requirement, from root `AGENTS.md` (symlinked as `CLAUDE.md`) and `docs/development.md`/`docs/testing.md`:

- **Node**: `22.19+` or `24+` (`docs/development.md` Prerequisites; CI covers 22.19, 24, and 26).
- **Package manager**: Corepack-enabled pnpm, pinned `pnpm@11.7.0`.

```sh
pnpm install            # pnpm workspaces, node ^22.19 || >=24
pnpm run test           # unit tests
pnpm run test:coverage  # CI coverage gate: per-file 100% on packages/*/*/src
pnpm run test:e2e       # real-API tests; self-skip without DEEPSEEK_API_KEY
pnpm run test:expected  # owner-local process expectations
pnpm run test:snapshot  # keyless recorded-session replay through shipped profiles
pnpm run typecheck
pnpm run lint
pnpm run build          # tsc emits lib/types, tsdown bundles runtime
pnpm run doc-sync       # documentation gates
```

### Vitest / test-tier families (`docs/testing.md`)

| Tier | Command | What it covers |
|---|---|---|
| Unit | `pnpm run test` | vitest over `tests/**` per package plus `scripts/**/*.spec.ts`; every registry gets an HMR-safety test (dispose the contributing fiber, assert cleanup) |
| Coverage gate | `pnpm run test:coverage` | per-file 100% on `packages/*/*/src`; an uncovered line is treated as a dead-code signal, not a missing-test signal |
| Real-API e2e | `pnpm run test:e2e` | live provider calls; each suite self-skips without its key (`DEEPSEEK_API_KEY`, `EXA_API_KEY`, `PERPLEXITY_API_KEY`, ...) |
| Owner-local expected | `pnpm run test:expected` | keyless assembled CLI/process expectations, `*.expected.e2e.ts` beside `tests/expected/` |
| Performance benchmarks | `pnpm run test:bench` | `benchmarks/` user-path gates; timed code runs under plain Node, never TSX; required Linux PR gate `node 24 / benchmarks` |
| Snapshot | `pnpm run test:snapshot` | recorded-session round trips (`session[.vN].jsonl` parents, `session.<ordinal>[.vN].jsonl` children) through shipped `dsh` profiles (headless/SDK/ACP/Web) |
| Web browser snapshot | `pnpm run test:web` | Chromium comparison under `snapshots/web/`; CI forces read-only `DSH_SNAPSHOT=replay` |

Vitest config resolution: every vitest config points `vite-tsconfig-paths` at `tsconfig.base.json`, so bare workspace imports resolve to package `src`, never through `exports` to built `lib/` (`docs/testing.md` "Test resolution: source plane only"). CI/build-having lanes run subprocess-launching tests from built `lib/` through a shared dual-mode launcher instead.

Recorded-session testing detail: the "with-key policy" ("We are DeepSeek — do not ration real-API tests") states real inference is treated as cheap for this project and calls for covering file-writing prompts, multi-turn conversations, tool use, and mid-stream cancellation; smoke tests that boot a shipped `dsh` profile and check the world are called out as highest-value.

### Build layout (`docs/development.md`)

Build order: `tsc -b tsconfig.host.json` then `tsdown --env.DSH_BUILD_FACE host` then `tsc -b tsconfig.client.json` then `tsdown --env.DSH_BUILD_FACE client` then `pnpm run build:web`. Host and Client are two separate TypeScript aggregate programs (both declaration-merge the cordis `Context` under the same keys with different services; one program seeing both would collide).

`BENCHMARK.md` points to running benchmarks through the **Python SDK** (`docs/user/guide/python-sdk.md`, `jsonrpc-agent` minimal variant) with separate workspaces/session IDs per independent benchmark task — this is the only content of that file; it defers entirely to the Python SDK guide rather than describing an in-repo perf harness itself.

### Runtime invariants (`docs/subsystems/invariants.md`)

`ctx.invariants` (`packages/runtime-diagnostics/invariants`) is a configurable registry for package-owned runtime checks — every workspace package ships a `./invariant` companion registered under its exact npm package name. Checks may assert only over **authoritative event streams or mutable data**, never service/method presence; `pnpm run verify-package-invariants` mechanically rejects generated markers and unexplained empty installers. This is a correctness/quality gate adjacent to but distinct from the vitest tiers above.

### Cannot / does not (build/test)

- Coverage gate does not by itself prove correctness — line coverage "proves lines ran, not that the feature works as shipped" (`docs/testing.md`).
- `pwsh`-dependent coverage (`packages/shell/pwsh-local/src`) self-skips without a real `pwsh` on the host; `vitest.config.ts` exempts the file so pwsh-less hosts stay green, while CI enforces the full bar.
- Static analysis/tests never resolve through built `lib/` — only explicit built-artifact smokes and `lib`-mode subprocess launches do.

## 6. Safety notice and license obligations

### Safety (`SAFETY.md`)

DeepSeek Harness (upstream, and by inheritance this fork) is described as **"experimental developer-preview software"** that **"has not undergone a security audit and must not be treated as secure or production-ready."** It can execute model-generated code/commands, load third-party plugins, and access network/processes/credentials/files made available to it; incorrect output, defects, misconfiguration, malicious input, or untrusted plugins "may damage the host computer, modify or delete files, disclose data or credentials, or cause other unintended effects."

Sandboxing/approval prompts/permission controls "can reduce risk" but "do not guarantee isolation or prevent damage," even when correctly enforced, for resources the project is allowed to access; the harness must not be the sole security control for untrusted workloads. Responsible-use guidance: least privilege, disposable VM/container/dedicated environment, keep backups, do not expose sensitive credentials unless accepting the risk, review plugins/config/commands before allowing them to run.

**No warranty or liability**: use at your own risk under the MIT License; authors/copyright holders are not responsible for damage, data loss/disclosure, or other harm "to the maximum extent permitted by applicable law."

### License obligations (`THIRD_PARTY_NOTICES.md`)

DeepSeek Harness itself is **MIT**-licensed (`LICENSE`). `THIRD_PARTY_NOTICES.md` is machine-generated (`scripts/gen-third-party-notices.ts`, pre-commit-hook-regenerated, test-asserted) and lists:

- **Vendored source** (`vendor/`): the Cordis framework and foundation libraries (`@deepseek-ai/cordis`, `cosmokit`, `schemastery`, and the `@cordisjs/plugin-*` family) are source-vendored and republished under the `@deepseek-ai` scope — all MIT, upstream commits and local modifications recorded in `vendor/README.md`.
- **Runtime npm dependencies**: direct dependencies plus the disclosed Claude Code platform payload closure and bundled Python distributions, each under its own upstream license — predominantly MIT and Apache-2.0, with some BSD-2-Clause/BSD-3-Clause and dual-license entries (e.g. `dompurify`: MPL-2.0 OR Apache-2.0). Full transitive npm closure with pinned versions is in `pnpm-lock.yaml`; the Python SDK closure is in `python/sdk/uv.lock`.
- The notice file explicitly states: "Each project remains under its own license; nothing in this file changes those terms."

### Cannot / does not (safety/license)

- SAFETY.md does not claim any sandbox guarantees isolation — this is stated as a hard limitation, not a caveat.
- THIRD_PARTY_NOTICES.md is not hand-maintained — editing it directly would be overwritten/flagged by the generator's test-lane assertion.

## 7. Plexar notes

- **Telemetry is a non-issue for this deployment**: `session-telemetry-otel` is explicitly disabled in `packages/bundle/plexar/cordis.patch.yml`, and `product-telemetry-otel` is never composed into either the base or plexar bundle — no session content, redacted or not, and no product analytics leave the process by default. This should be re-verified any time the plexar bundle patch is touched, since the mechanism is a config-row disable, not a code-level removal (the underlying `dsh-session-telemetry-otel` package still ships and could be re-enabled by a future bundle edit).
- **Model routing to the self-hosted rig is already wired via `llm-pi-ai`**: `packages/bundle/plexar/cordis.patch.yml` configures a `plexar` provider using `api: openai-completions` against `PLEXAR_RIG_URL` (default `https://plexar-llm.boord-its.com/v1`), model id from `PLEXAR_MODEL` (default `qwen3.8-27b`), auth via `PLEXAR_HARNESS_KEY`. This is the integration point for the vLLM/Qwen rig — any endpoint or model change is a one-line env var or patch edit, not a code change.
- **DeepSeek-cloud rows are fully disabled**, not merely unconfigured: `llm-deepseek`, `deepseek-llm-api-extensions`, `plugin-package-inventory-deepseek`, `session-log-deepseek`, `deepseek-account`, `web-search-deepseek` are all `disabled: true`. This matters for persistence specifically because `session-log-deepseek` (a cloud session-log delivery integration, evidenced by the `session-log-deepseek/delivery-accepted` event type in `docs/persistence-catalog.md`) is off — session logs stay strictly local under DSH_HOME.
- **The session log is the only durable "memory" surface a Studio embedding needs to reconcile**: since `SessionHandle.append`/`flush` and the crash-repair contract (sections 1.2-1.3) are well-specified and the JSONL backend is local-file-based, a Studio process embedding this harness over stdio can treat DSH_HOME's session store as its own durable conversation history without inventing a separate persistence layer — but it must account for `FEEDBACK_ONLY`/disabled telemetry meaning Studio gets **no automatic usage signal**; any product analytics Studio wants must go through its own explicit `ctx.productTelemetry.emit()` calls (currently unwired here) rather than assuming the harness reports anything.
- **Token-meter output (`ctx.tokenMeter.measure`) is route-aware**, so once the rig's `plexar` provider is the active route, `TokenSurfaceNode.tokens` reflects that route's declared pricing (or the fixed heuristic if the rig does not declare image/token pricing) — Studio should not assume DeepSeek-cloud pricing numbers apply; check whether the `llm-pi-ai` provider config declares request-image pricing before trusting `surfaceTokens` as a cost proxy for the local rig.
- **Storage/spill paths are all local and private by default** (spill root is 0700, owner-only writes) — embedding in Studio over stdio does not require any new sandboxing for these paths, but Studio should be aware it shares DSH_HOME state (sessions, settings, credentials, plugins) with any CLI `dsh` invocation on the same machine unless it sets a distinct DSH_HOME, mirroring how Desktop isolates itself via `profiles/desktop`.
- **Build/test story for a Studio-embedded process is standard Node/pnpm**: no special build step is needed beyond `pnpm install` plus `pnpm run build` (Node `22.19+`/`24+`); if Studio drives the harness via a built `dsh` bin, it should launch from `lib/` (the "real entry path" testing rule in `docs/testing.md`), not from source via tsx, to match how the project itself validates production behavior.
- **Safety posture must be surfaced to Studio operators, not hidden**: `SAFETY.md`'s explicit "not production-ready, no security audit" stance and "sandboxing does not guarantee isolation" language should propagate into any Studio-facing documentation or UI that embeds this harness, since Studio inherits the same arbitrary code/command execution surface.
