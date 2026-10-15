# 06 — Plexar integration: current state, capability matrix, and gaps

Audience: Plexar framework team and Plexar Studio team. Scope: what Plexar has already built on top of `dsh` (deepseek-ai/deepseek-harness, forked here), what the harness can and cannot do for us today, the Studio embedding recipe, the `plexar-chat` relationship, rig-lane header propagation, and a prioritized gap list. This document does not restate `01-surfaces.md`, `02-kernel.md`, `03-tools-and-capabilities.md`, `04-configuration-and-plugins.md`, or `05-persistence-ops-and-quality.md` — read those first; they are cited here by path.

## 1. Current state

### 1.1 The plexar bundle, row by row

Source: `packages/bundle/plexar/cordis.patch.yml`, `packages/bundle/plexar/README.md`. The bundle is "one patch file, applied over `dsh-base` and `dsh-headless`; no upstream file is edited" (`packages/bundle/plexar/README.md`) — every row is either an id-targeted override or a `disabled: true` against a row `dsh-base`/`dsh-headless` already declare, per the patch grammar in `docs/plexar/04-configuration-and-plugins.md` section 3.

| Row id | Action | What it does | Why |
|---|---|---|---|
| `llm-pi-ai` | override `config.providers.plexar` | Registers a hand-declared route `plexar`: `displayName: Plexar Rig`, `apiKeyEnv: PLEXAR_HARNESS_KEY`, `api: openai-completions`, `baseURL: (PLEXAR_RIG_URL ?? 'https://llm.plexar.tech') + '/v1'`, `retryPolicy: {mode: normal, maxRetries: 2}`, one model entry `id: PLEXAR_MODEL ?? 'Qwen/Qwen3.6-35B-A3B'` with `contextWindow: 131072`, `maxTokens: 16384` | Points the harness at the self-hosted vLLM/Qwen rig instead of any hosted provider — see `docs/plexar/04-configuration-and-plugins.md` section 4 for the full `PiAiProviderProfile` field set this row uses |
| `agent-default-model` | override | `provider: plexar`, `model: PLEXAR_MODEL ?? 'Qwen/Qwen3.6-35B-A3B'` | Makes the rig route the session default instead of `deepseek-official`/`deepseek-flash` |
| `system-prompt` | override | `personaPrefix`: "You are Plexar, a coding agent running on a self-hosted {{model}} model. Work in the repository you are given. Prefer reading files and running commands over guessing." `personaSuffix`: "Your working directory is {{cwd}}." | Re-personas the agent per `docs/plexar/04-configuration-and-plugins.md` section 4's `system-prompt` row (`{{model}}`/`{{cwd}}` interpolation) |
| `llm-deepseek` | `disabled: true` | Turns off the DeepSeek-cloud model adapter | No DeepSeek-cloud traffic |
| `deepseek-llm-api-extensions` | `disabled: true` | Turns off a DeepSeek-cloud API extension row | Same; comment in the patch notes these two "hard-inject deepseekLlmApiExtensions and would wait forever" if left enabled without a DeepSeek route |
| `plugin-package-inventory-deepseek` | `disabled: true` | Turns off DeepSeek plugin-inventory reporting | No DeepSeek-cloud dependency |
| `session-log-deepseek` | `disabled: true` | Turns off DeepSeek-cloud session-log delivery | Session logs stay strictly local under `DSH_HOME` (confirmed in `docs/plexar/05-persistence-ops-and-quality.md` section 7) |
| `deepseek-account` | `disabled: true` | Turns off the DeepSeek account/sign-in service | No DeepSeek identity coupling |
| `web-search-deepseek` | `disabled: true` | Turns off DeepSeek-cloud web search | Search is disabled outright (see `tool-web` row below) |
| `session-telemetry-otel` | `disabled: true` | Turns off the only shipped `session-telemetry` Service Provider | Nothing phones home from the session log — verified independently in `docs/plexar/05-persistence-ops-and-quality.md` section 3 |
| `plugin-manager` | `disabled: true` | Turns off the `plugin_manager` tool and plugin marketplace | Surface trim: no runtime plugin install/enable/disable |
| `tool-plugin-manager` | `disabled: true` | Turns off the plugin-manager tool row specifically | Same |
| `tool-ralph` | `disabled: true` | Turns off the `ralph` tool | No fresh-agent Ralph loop |
| `tool-web` | override | `config: { fetch: true, search: false }` | Keeps `web_fetch`, drops `web_search` (no search provider is configured anyway once `web-search-deepseek` is off) |
| `ui-settings-models` | override | `config: { credentialOnboarding: false }` | Suppresses the "configure the official DeepSeek provider" onboarding flow in the Web UI |

Everything else in `dsh-base` stays composed unchanged: bash/pwsh sandbox, fs tools, skills, plan mode, compaction, subagents, MCP, web fetch (`packages/bundle/plexar/README.md`, "What is switched off").

### 1.2 The two profiles

- **`plexar`** — headless. `base + headless + plexar` bundle stack. Created once via `pnpm dsh --profile plexar --from-default-profile headless --help`, then the bundle is linked in via `pnpm dsh plugin --profile plexar add link:<abs path>/packages/bundle/plexar` (`packages/bundle/plexar/README.md`, "Install (once)"). This is the profile pattern documented generically in `docs/plexar/01-surfaces.md` section 8 (`dsh <name>` / `dsh --profile <name>`) and section 9 (bundle apps backing stdio surfaces) — `plexar` itself is a headless (stdout-final-answer) composition, not sdk/acp.
- **`plexar-web`** — the interactive browser GUI. `base + web-app + plexar` bundle, "plus a profile patch disabling `account-controller` and `ui-settings-account` (they hard-inject the DeepSeek account service)" (`packages/bundle/plexar/README.md`, "Web UI (interactive)"). Needs a built tree (`pnpm run build`, Node 24); `pnpm dsh --profile plexar-web` opens `http://127.0.0.1:3080`.

### 1.3 The minted key model

`PLEXAR_HARNESS_KEY` is the bearer credential the `plexar` provider route resolves via `apiKeyEnv` (`docs/plexar/04-configuration-and-plugins.md` section 4, `PiAiProviderProfile.apiKeyEnv`, resolved per request through `ctx.credentials`, never cached — `docs/plexar/02-kernel.md` section 5's credential-seam note applies the same way here). Per `packages/bundle/plexar/README.md` ("Gotchas," measured 2026-09-22): "Off-loopback the rig requires a bearer. `PLEXAR_HARNESS_KEY` is minted (2026-09-22): rig key `key_9dfcca42cccd49db`, label 'Plexar Harness', scope guest, models `*`, visible in the plexar-llm console key table." The key is stored in Len's Windows user env; new shells pick it up, existing ones need a restart. Scope `guest` and models `*` mean this key currently has no narrower per-model or per-capability restriction on the rig side — see gap G6 below.

### 1.4 How to run each surface

From `packages/bundle/plexar/README.md`:

```sh
export PLEXAR_HARNESS_KEY=<rig bearer key>
pnpm dsh --profile plexar "run the tests"
pnpm dsh --profile plexar --json "summarize this repo" > events.jsonl
```

`PLEXAR_RIG_URL` overrides `https://llm.plexar.tech`; `PLEXAR_MODEL` overrides `Qwen/Qwen3.6-35B-A3B`. For `plexar-web`: build first (`pnpm run build`, Node 24), then `pnpm dsh --profile plexar-web`, opens `http://127.0.0.1:3080`. Source-mode gotchas (Node ≥ 22.19/24 required, `TSX_TSCONFIG_PATH` for out-of-repo invocation, harmless `typert-loader` warning, WireGuard hijacking `the LAN subnet`) are recorded verbatim in `packages/bundle/plexar/README.md` and cross-referenced in `docs/plexar/04-configuration-and-plugins.md` section 5.

## 2. Capability matrix

Columns: **Upstream status** (native/experimental/absent, doc citation) / **Works on our rig today** (yes/no/untested) / **Plexar gap** (none/config/build).

| Capability | Upstream status | Works on our rig today | Plexar gap |
|---|---|---|---|
| Edit files | Native — `edit`/`read`/`read_image`/`write` (`dsh-tool-fs`), enabled by default (`docs/plexar/03-tools-and-capabilities.md` section 1) | Yes (default-on, unmodified by the plexar patch) | None |
| Run shell | Native — `bash` (POSIX default), `pwsh` (Windows default), each sandbox-confined per session mode (`docs/plexar/03-tools-and-capabilities.md` section 1, 2.1-2.3) | Yes | None |
| Run tests | Native, via `bash`/`pwsh` — no dedicated "test runner" tool exists; tests run as ordinary shell commands | Yes | None |
| Git | Native, via `bash`/`pwsh` — no dedicated git tool; git runs as ordinary shell commands under the same sandbox | Yes | None |
| Web fetch | Native — `web_fetch`/`web_search` (`dsh-tool-web`), gated per-route config `fetch`/`search` | `web_fetch: true` on the plexar route; `web_search: false` (no provider configured) — fetch yes, search no | None (deliberate; search re-enable is config-only if desired) |
| MCP | Native — `dsh-mcp-client` (stdio/streamable-http), no server configured by default (`docs/plexar/03-tools-and-capabilities.md` section 3) | Untested — no MCP server row exists in either `base` or `plexar` patch | Config (add an `id: mcp-*` row; see section 4 below for the plexar-chat/office case) |
| Skills | Native — `dsh-skill` + `dsh-skill-filesystem`, project/user/bundled discovery roots (`docs/plexar/03-tools-and-capabilities.md` section 4) | Untested against this profile specifically, but the `skill` tool row is not disabled by the plexar patch, so it should be Yes | None expected; untested |
| Hooks | Native but a compatibility shim only — Claude Code bridge (7/30 events) and Codex bridge (5/10 events) (`docs/plexar/03-tools-and-capabilities.md` section 5) | Untested — no hook config present in the plexar bundle | Config if wanted; the harness's own extension points (`agent/pre-step`, `tools/pre-execute`, etc.) are the better Plexar-native integration point per that section's Plexar notes |
| Subagents | Native — one-shot (`dsh-tool-subagent`) and continuable background children, `maxActiveSubagents` default 8 (`docs/plexar/02-kernel.md` section 7) | Yes (default-on, unmodified by the plexar patch) | None |
| Plan mode | Native, soft guidance only, no enforcement (`docs/plexar/02-kernel.md` section 8) | Yes (default-on) | None |
| Resume sessions | Native — `--session-id` in headless (with adoption restrictions, `docs/plexar/01-surfaces.md` section 3), full `session/resume` in ACP (`docs/plexar/01-surfaces.md` section 4) | Yes for headless `--session-id`; ACP untested on this bundle (bundle only composes `headless`, not `acp`) | Build/config — mounting `acp` on the plexar rig is a new profile, not yet composed |
| Structured event stream | Native — headless `--json` NDJSON (`docs/plexar/01-surfaces.md` section 3), SDK JSON-RPC `session.event`/`session.status`/`subagent.*` notifications (section 2), ACP `session/update` (section 4) | Headless `--json` yes (works today); SDK/ACP streams untested — no `sdk`/`acp` profile composed with the plexar bundle yet | Build — needs a `plexar-sdk` profile (see section 3) |
| Approval/permission | Native — `ctx.approval` (`ask`/`never` policy), permission presets (`workspace-write`/`danger-full-access`) (`docs/plexar/03-tools-and-capabilities.md` section 2.4-2.5) | Yes, unmodified defaults apply | None |
| Sandboxing | Native — POSIX (bwrap/Landlock/Seatbelt) + Windows ACL restricted-token backend, `read-only`/`workspace-write`/`danger-full-access` (`docs/plexar/03-tools-and-capabilities.md` section 2.1-2.2) | Yes on POSIX; Windows pwsh sandbox parity is an explicitly flagged open question (see Risks, section 8) | None functionally, but verify Windows pwsh sandbox parity before promising it |
| LSP | Native but opt-in, 4 fixed operations only (`docs/plexar/03-tools-and-capabilities.md` section 1, 7) | Untested — `lsp` tool row not composed in the plexar patch | Config (add the row if wanted) |
| Scheduling | Native but opt-in, session-local delivery only, no cron, `every_seconds` min 300s (`docs/plexar/03-tools-and-capabilities.md` section 1, 7) | Untested — `schedule_*` tools not composed | Config if wanted; not useful for Studio's cross-session needs (see section 4 below and that section's Cannot/does not) |
| PDF/Office | Not model-facing at all — `packages/document/office-to-pdf` is host-only, consumed by preview UI (`docs/plexar/03-tools-and-capabilities.md` section 6) | No native model-facing PDF/Office capability in the harness at all | Build — this is exactly the gap `plexar-chat`'s `chat/office` module fills; the plan is to expose it to the harness as an MCP server, not port it in (section 4) |
| Browser | Experimental, explicit opt-in, single-provider-slot (Stagehand/Playwright/Chrome DevTools MCP) (`docs/plexar/03-tools-and-capabilities.md` section 1, 6) | No — not composed in the plexar bundle | Config to enable; treat as pre-GA per that section's Plexar notes |
| Voice | Not found in any read source (`01`-`05`) | No | Absent upstream; out of scope for this digest's read set |
| Multi-tenant | Absent from the harness's own trust model — SDK/ACP wire notifications carry "zero authentication or per-connection scoping" (`docs/plexar/02-kernel.md` section 1 Plexar notes, section 9 Web route table) | No — single-tenant per subprocess is the harness's own stated model | Build, and out of harness scope — must live at the Studio/rig layer (see section 3 and section 5) |
| Auth | Harness-side: none on SDK/ACP stdio wire (trust = the parent process); Web has Connection-layer Host/Origin + browser-session auth (`docs/plexar/01-surfaces.md` section 1, 11) | Web UI: yes, via `dsh-host-webserver`'s Connection layer. Stdio (SDK/ACP): no auth at all — trust boundary is the subprocess owner | None for Web; for stdio embedding, auth must be enforced by whatever spawns the harness process (Studio), not by the harness itself |

## 3. Studio embedding recipe

**Surface: SDK JSON-RPC over stdio (`dsh --profile sdk`).** Not ACP, and not PTY.

- **Why not PTY**: no PTY-based interactive surface is documented as a first-class automation entry point in `01-surfaces.md` — the only stdio-automation surfaces are SDK JSON-RPC and ACP. A PTY would force Studio to parse terminal escape sequences and reconstruct structure the harness already emits as typed JSON-RPC frames; this contradicts the harness's own "Model-visible ⟺ logged" and typed-event design (`CLAUDE.md`, `docs/plexar/02-kernel.md` section 2).
- **Why SDK over ACP for this embedding**: SDK JSON-RPC is "process-owned, stdout-pure-by-contract, and has typed TS/Python clients with documented teardown ladders" (`docs/plexar/02-kernel.md` section 1 Plexar notes). ACP is the better fit only if Studio wants protocol-level `session/list`/`session/resume`/`session/close` across restarts and richer permission prompts, at the cost of building its own presentation layer entirely from `session/update` since ACP exposes no DSH-specific cards/plans/todos (same section). Given Studio already needs a custom UI layer either way, SDK's simpler three-method surface (`initialize`/`session/prompt`/`shutdown`, `docs/plexar/01-surfaces.md` section 2) is the lower-integration-cost starting point; ACP remains the fallback if Studio later needs multi-restart session listing.

**Exact profile to create: `plexar-sdk` = `dsh-base` + `dsh-sdk-app` + `@plexar/dsh-plexar`.** This mirrors the existing `plexar` (headless) and `plexar-web` (web) profiles' composition pattern (`packages/bundle/plexar/README.md` section 1.2 above) but stacks the SDK bundle instead of headless/web-app. `dsh-sdk-app` (`packages/bundle/sdk-app/README.md`, cited in `docs/plexar/01-surfaces.md` section 9) mounts `dsh-sdk-jsonrpc-server`, uses the same persona-template pattern the plexar bundle already overrides (`system-prompt.personaPrefix`/`personaSuffix`), and exposes `DSH_MAX_TOKENS_AS_SUCCESS` plus default file tools `read`/`write`/`edit`. **This profile does not exist yet in this repo** — it is Gap G1 in section 6.

**Method/notification sequence for one turn, as documented in `01-surfaces.md` section 2:**

1. Client sends `initialize` (`InitializeParams { cwd, provider, model, reasoningEffort?, maxTokens? }`) — for the plexar rig this is `provider: 'plexar'`, `model: PLEXAR_MODEL` (or an explicit override), reasoningEffort/maxTokens per rig limits. Server validates the route via the selected adapter (`llm-pi-ai`'s `plexar` route) and returns `InitializeResult`. `session/prompt` rejects until this completes.
2. Client sends `session/prompt` (`SessionPromptParams { sessionId, contentBlocks }`) — queues one user message, lazily creating the agent+session pair for an unknown `sessionId`. Returns `{ messageId }` immediately on enqueue; there is no per-prompt result.
3. Server emits `session.event` notifications (`SessionEventNotification { sessionId, event: SessionEvent }`) for every durable event in the turn/step sequence documented in `docs/plexar/02-kernel.md` section 1 (`turn/start` … `assistant/message`/`assistant/attempt` … `tool/call`/`tool/result` … `turn/end`), plus `session.status` on `idle`/`running` transitions, plus `subagent.started`/`subagent.finished` if subagents fire.
4. Client eventually sends `shutdown` (idempotent, disposes server-owned agents/adapter fiber/subscriptions to quiescence).

**What Studio must implement itself** (none of this is built into the SDK client or server):

- **Approval channel**: the SDK server does not expose an approval-request notification/response pair in the method table (`01-surfaces.md` section 2) — approval flows through `ctx.approval` inside the harness process (`docs/plexar/03-tools-and-capabilities.md` section 2.4). Studio embedding via SDK stdio must wire a real `ctx.approval` provider (a Cordis plugin registered in the `plexar-sdk` profile, not something the wire protocol carries), because "an absent/unanswerable approval channel becomes an automatic deny" (`docs/plexar/02-kernel.md` section 1 Plexar notes).
- **Event rendering**: Studio must render `session.event`/`assistant-stream` frames into UI itself; the SDK protocol carries only durable `SessionEvent` replay via `session.event` and no DSH-specific presentation data (this is explicitly an ACP limitation too, but SDK has even less structure — no cards/plans/todos concept on the wire at all).
- **Session resume**: the SDK JSON-RPC server has "no per-session close or prompt-cancel method" and SDK-created agents "remain live until process shutdown" (`docs/plexar/01-surfaces.md` section 7, Cannot/does not). Studio must manage session lifecycle itself — there is no resume call on this surface; only headless `--session-id` (own profile) and ACP `session/resume` support resume as documented calls.
- **Isolation between concurrent Studio users/tabs**: the SDK server "notifies for every session in the runtime context, not just ones Studio created" — Studio must implement its own session-tree scoping client-side, filtering on `subagent.started` lineage as both official SDKs already do (`docs/plexar/02-kernel.md` section 1 Plexar notes).

**What is unknown/untested**: whether `plexar-sdk` as specified above actually composes cleanly (no profile of this shape exists in the repo today — see Gap G1); whether the rig's `llm-pi-ai` route validates correctly under SDK's `initialize` provider/model validation path (only exercised via headless `plexar` profile so far); ACP as an alternative has not been evaluated against the rig at all (no `plexar-acp` profile exists either).

**Teardown ladder for the embedded subprocess**: `docs/plexar/01-surfaces.md` section 5 documents the TypeScript SDK client's teardown expectation — `close()` (or `await using`) is required to reap the child process, and `docs/plexar/02-kernel.md`'s Plexar notes state the documented ladder as "stdin EOF -> SIGTERM -> SIGKILL." Studio's process supervisor must implement this same ladder around the `plexar-sdk` subprocess: closing stdin first, escalating to SIGTERM if the process does not exit, and only using SIGKILL as a last resort, to avoid leaving an orphaned harness process holding an open rig connection. Because the SDK server's `shutdown` method is memoized/idempotent (`docs/plexar/01-surfaces.md` section 2), Studio may call it defensively on any teardown path without risk of a double-shutdown error.

**Multi-session concurrency inside one subprocess**: `session/prompt` lazily creates the agent+session pair for an unknown `sessionId` (`docs/plexar/01-surfaces.md` section 2), so a single `plexar-sdk` subprocess can host multiple concurrent sessions without Studio spawning a new process per conversation. This is attractive for resource use but directly collides with the isolation gap above (G5) — every session in that one process shares the same `PLEXAR_HARNESS_KEY` credential and the same `ctx.approval` provider instance, so Studio's session-scoping logic is also the boundary between two users' conversations if the subprocess is ever shared across users. The safer default until G5 is resolved is one `plexar-sdk` subprocess per authenticated Studio user, not one shared subprocess for the whole product.

## 4. plexar-chat relationship

**`plexar-chat` is the public conversational product and stays the owner of document (PDF/Excel/HTML) code.** Per `<workspace>\plexar-chat\CLAUDE.md`: "Not Studio with the tools removed... Studio is a multi-session developer multiplexer that runs a CLI against a PTY; Chat is a hosted product with a different trust model, a different user, and a different threat surface. They share a provider, not a codebase." `chat/office/` (listed, not read, per this worker's instructions) contains modules `_chart.py`, `_colour.py`, `_model.py`, `_pivot.py`, `_runs.py`, `_template.py`, `_xml.py`, plus subdirectories `excel/`, `html/`, `pdf/`, `plaintext/`, `powerpoint/`, `word/` — "document readers and writers — docx/xlsx/pptx/pdf/html, `_chart.py` (T81). Hand-written binary parsers; every bound in them was corpus-validated (T84)" (`<workspace>\plexar-chat\CLAUDE.md`, Structure section).

The harness has no native model-facing PDF/Office capability of its own — confirmed above (capability matrix "PDF/Office" row, `docs/plexar/03-tools-and-capabilities.md` section 6: `office-to-pdf` is host-only, no model-facing tool or Session event).

**The shape: an MCP stdio server wrapping `chat/office`; the harness mounts it via the mcp config row per `03`/`04`.**

- The harness consumes `plexar-chat`'s document code as an ordinary `@deepseek-ai/dsh-mcp-client` config row — same shape documented in `docs/plexar/03-tools-and-capabilities.md` section 3.1: `transport: stdio`, `command`/`args`/`env`/`cwd` pointing at a new small MCP-protocol server process that imports `chat/office`'s Python readers/writers and exposes them as MCP tools.
- Tool names would arrive server-qualified: `mcp__<serverName>__<rawName>` (`docs/plexar/03-tools-and-capabilities.md` section 3.2) — e.g. `mcp__office__read_docx` if the server is registered `serverName: office`.
- This is not yet built anywhere in this repo or `plexar-chat` — it is Gap G2 in section 6.

**What NOT to do:**

- **Do not port Python into the harness.** `chat/office`'s parsers are "hand-written binary parsers; every bound in them was corpus-validated" (`<workspace>\plexar-chat\CLAUDE.md`) — duplicating that logic in the harness (TypeScript/Node) would fork a validated implementation and lose corpus coverage. The MCP boundary is the reuse mechanism, not a rewrite.
- **Do not expose the harness to strangers.** `<workspace>\plexar-chat\CLAUDE.md`'s invariant: Chat is the hosted, multi-tenant, stranger-facing product; the harness (Studio-embedded or headless-on-the-rig) has no multi-tenant trust model of its own (capability matrix row above, "Multi-tenant: Absent... single-tenant per subprocess"). `plexar-chat`'s own `upstream/` package is "the ONLY package that speaks to the rig" and Chat "never authenticates anyone" itself (INVARIANT-BORROWED) — the harness must not become a second, less-audited path to the rig or to document content that bypasses Chat's per-`sub` R2 scoping (INVARIANT-OWNSCOPE, INVARIANT-SUBKEYED, both in `<workspace>\plexar-chat\CLAUDE.md`).

## 5. Rig-lane orchestration

`<workspace>\plexar-vllm\docs\01-contracts.md` section 10h documents three optional orchestration-correlation request headers, verified by `grep 'X-Plexar'`:

| Header | Column recorded | Accepted format |
|---|---|---|
| `X-Plexar-Orch-Run` | `orch_run_id` | `^[A-Za-z0-9._:-]{1,128}$` |
| `X-Plexar-Orch-Node` | `orch_node_id` | `^[A-Za-z0-9._:-]{1,128}$` |
| `X-Plexar-Brief-Sha256` | `orch_brief_sha256` | exactly 64 hex characters, case-insensitive |

"All three are OPTIONAL and a consumer that never sends them is unaffected... Nothing about routing, admission, clamping, priority or the response changes; these are recorded and otherwise inert." The brief itself is never stored, only its hash: "THE BRIEF IS NEVER STORED — ONLY ITS HASH, AND THAT IS THE POINT" (same section). An agent on the rig's live registry is keyed as the `(orch_run_id, orch_node_id)` pair (`<workspace>\plexar-vllm\docs\01-contracts.md` section 10l).

**Is there a per-request header config on `llm-pi-ai`? Checked `02-kernel.md`, `04-configuration-and-plugins.md`, and `packages/llm/llm-pi-ai/README.md` directly.** The only header mechanism documented is `PiAiProviderProfile.headers?: Record<string,string>` — a **static, per-route** dict of headers, set once in `cordis.patch.yml` config and applied to every request on that route (`docs/plexar/04-configuration-and-plugins.md` section 4; confirmed in `packages/llm/llm-pi-ai/README.md`: "`headers` can carry a credential the redactor never sees — profile resolution rejects names and values Fetch cannot represent, but the dict remains plain strings; store credentials as `apiKeyEnv` references"). No per-request or per-call header injection point is documented anywhere in the read set — `GenerateOptions` (the per-call request shape referenced in `02-kernel.md` section 5) is not shown to carry an arbitrary-headers field, and `packages/llm/llm-pi-ai/README.md`'s full "Known Limitations" list (quoted verbatim in `docs/plexar/02-kernel.md` section 5) has no header-related per-request entry.

**Consequence: a harness worker cannot set `X-Plexar-Orch-Run`/`X-Plexar-Orch-Node`/`X-Plexar-Brief-Sha256` per turn or per subagent today.** The static `headers` field could carry a *fixed* value for an entire profile/process lifetime (e.g. one `orch_node_id` baked into a `plexar-sdk` profile's patch for that worker instance), but it cannot vary per turn, per session, or per subagent the way the rig's correlation model (`(orch_run_id, orch_node_id)` pair per live agent) implies it should. **Mark this UNTESTED and UNSUPPORTED as a dynamic per-call mechanism** — confirming whether `llm-pi-ai` has an undocumented per-request header hook would require reading its source directly, which is outside this worker's read list (`README.md` only).

## 6. Gap list, prioritized P0-P3

| # | Priority | What | Why (doc/section) | Size | Kind |
|---|---|---|---|---|---|
| G1 | P0 | No `plexar-sdk` profile exists | Studio embedding (section 3) requires `dsh-base + dsh-sdk-app + @plexar/dsh-plexar`; only `plexar` (headless) and `plexar-web` exist today (`packages/bundle/plexar/README.md`) | S | Config — new profile + small patch overlay, same shape as the existing `plexar`/`plexar-web` profiles |
| G2 | P0 | No MCP server wraps `chat/office` | Harness has zero native PDF/Office capability (`docs/plexar/03-tools-and-capabilities.md` section 6); `plexar-chat`'s document code is the only validated implementation (section 4 above) | M | Build — new small MCP stdio server process in/around `plexar-chat`, plus one `dsh-mcp-client` config row in the harness profile |
| G3 | P0 | No approval channel implementation for a stdio-embedded Studio session | SDK server has no wire-level approval notification; an unanswered approval auto-denies (`docs/plexar/02-kernel.md` section 1 Plexar notes; `docs/plexar/03-tools-and-capabilities.md` section 2.4) | M | Build — a Cordis plugin implementing `ctx.approval`, mounted in `plexar-sdk`, bridged to Studio's own UI over some Studio-owned channel (not the SDK wire) |
| G4 | P1 | No dynamic per-turn `X-Plexar-Orch-*` header propagation | `llm-pi-ai`'s only documented header mechanism is static per-route `headers` (section 5 above) | M (needs upstream source read to confirm feasibility; could be L if a fork edit is required) | Untested — needs investigation beyond this worker's read list before sizing further; likely a plugin/adapter-level fork edit if no hook exists |
| G5 | P1 | No session isolation/scoping implemented client-side for multi-user Studio embedding | SDK server notifies for every session in the runtime context, not just caller-created ones (`docs/plexar/02-kernel.md` section 1 Plexar notes) | M | Build — Studio-side filtering logic, following the pattern both official SDKs already use (filter on `subagent.started` lineage) |
| G6 | P1 | Rig key scope is `guest`/models `*` with no narrower restriction | `packages/bundle/plexar/README.md` Gotchas: key `key_9dfcca42cccd49db` scope `guest`, models `*` | S | Config — rig-side key scoping (`plexar-vllm` console), not a harness change |
| G7 | P2 | No `acp` profile evaluated against the rig | Capability matrix row "Resume sessions" / "Structured event stream" — ACP untested; only headless is proven | M | Config/build — create `plexar-acp` analogous to G1, then test |
| G8 | P2 | Windows pwsh sandbox parity unverified | `docs/plexar/03-tools-and-capabilities.md` section 2.2: pwsh tool description "omits the '[sandbox: file access denied under MODE mode]' marker language that bash's tool description carries" — parity must be confirmed per deployment | S | Verification-only task, no build; may surface a real gap once checked |
| G9 | P3 | No MCP resource-scoping control on the `mcp-resources` row | `docs/plexar/04-configuration-and-plugins.md` section 4 and section 7 Cannot/does not: `mcp-resources` "does not expose a documented `config:` schema" | S | None available today short of a fork edit or upstream feature; low priority since no MCP server is mounted yet anyway (G2 comes first) |
| G10 | P3 | No cron/external scheduling for a Studio reminder feature | `docs/plexar/03-tools-and-capabilities.md` section 7: Schedule is "Session-local delivery only — no external notification channel or cold-session scheduler" | M | Build, external to the harness — an outside scheduler layered on top, not a harness change |

### 6.1 Gap detail

**G1 — no `plexar-sdk` profile.** The concrete steps, following the pattern in `packages/bundle/plexar/README.md`'s "Install (once)" section: create the profile with `pnpm dsh --profile plexar-sdk --from-default-profile sdk --help` (analogous to the existing `--from-default-profile headless` invocation for the `plexar` profile), then link the existing `packages/bundle/plexar` bundle into it with `pnpm dsh plugin --profile plexar-sdk add link:<abs path>/packages/bundle/plexar`. Because the plexar patch is already written generically against row ids that exist in both `dsh-headless` and `dsh-sdk-app` (`llm-pi-ai`, `agent-default-model`, `system-prompt`, the DeepSeek-disable rows), no changes to `cordis.patch.yml` itself should be required — the risk is entirely in verifying that `dsh-sdk-app` declares the same row ids the patch targets. If a row id differs (e.g. `dsh-sdk-app`'s persona row uses a different id than `dsh-headless`'s), the patch's id-targeted overrides would silently no-op rather than error (per the general patch-grammar behavior noted in `04-configuration-and-plugins.md` section 2: "a patch naming a nonexistent entry prints a stderr warning" — it does not fail boot), so this must be checked with `--dump-config` after composing, not assumed.

**G2 — no MCP server wraps `chat/office`.** This is two deliverables: (a) a thin Python MCP stdio server (new file, likely under `plexar-chat` since it already owns the office code and its Python environment) that imports `chat/office`'s existing readers/writers and exposes each capability (read docx, write xlsx, render chart, etc.) as an MCP tool per the Model Context Protocol's tool-definition shape; (b) one `@deepseek-ai/dsh-mcp-client` config row added to whichever Plexar profile needs it (most plausibly `plexar-sdk` for Studio, and optionally `plexar`/`plexar-web`), following the exact YAML shape in `docs/plexar/03-tools-and-capabilities.md` section 3.1. The MCP boundary also gives this integration the reconnect/backoff and 60-second SDK-owned discovery timeout documented in that section — no custom retry logic needs to be written on the harness side.

**G3 — no approval channel implementation.** The concrete shape: a small Cordis plugin (new package, e.g. `@plexar/dsh-approval-studio-bridge`) that implements the `ctx.approval` Service Provider role (`docs/plexar/03-tools-and-capabilities.md` section 2.4's `ApprovalPolicy`/`ApprovalOutcome` types) and forwards each `ask` request to Studio over a side channel Studio controls — not the SDK JSON-RPC wire, since that wire has no approval method (section 3 above). The plugin would be mounted in the `plexar-sdk` profile's own `cordis.patch.yml` (an `insert:` row, per the patch grammar in `04-configuration-and-plugins.md` section 3), not in the shared `packages/bundle/plexar` patch, since this behavior is Studio-embedding-specific and should not affect the `plexar`/`plexar-web` profiles.

**G4 — no dynamic per-turn orchestration headers.** Before sizing a fork edit, the next investigative step is reading `packages/llm/llm-pi-ai/src/` directly (outside this worker's read list, which was limited to the package `README.md`) to check whether the adapter's internal request-building code has any per-call header injection point not surfaced in the README's documented `Config` fields. If none exists, the smallest viable fork edit would extend `PiAiProviderProfile` (or a sibling per-request options type) with an optional headers-by-callback field the harness's tool/subagent layer could populate per turn — this would need to thread through from wherever `orch_run_id`/`orch_node_id` become known (likely the SDK's `initialize` params or a new Studio-supplied field) down to the actual HTTP request `llm-pi-ai` issues.

**G5 — session isolation for multi-user embedding.** The reference implementation pattern already exists: "both official SDKs already do" this filtering by watching `subagent.started` notifications for lineage (`docs/plexar/02-kernel.md` section 1 Plexar notes). Studio's equivalent would track, per Studio-visible conversation, the root `sessionId` it created via `session/prompt`, then filter every incoming `session.event`/`session.status`/`subagent.*` notification to only those whose `sessionId` (or ancestor `parentSessionId` via `subagent.started`) matches a session Studio owns, discarding the rest client-side.

**G6 — rig key scope.** Purely a `plexar-vllm` console action: mint a narrower-scoped key (e.g. restricted to the specific `Qwen/Qwen3.6-35B-A3B` model id rather than `*`) and update `PLEXAR_HARNESS_KEY` in the environment(s) that need it. No `plexar-harness` code or config changes.

## 7. Cross-reference map (which doc answers which question)

This table is a lookup aid — given a question, which of the six documents (and section) has the answer, so a reader does not have to re-derive it.

| Question | Answer lives in |
|---|---|
| "What tools does the plexar rig session have available?" | `06` section 1.1 (which rows are on/off) + `03` section 1 (the full tool table) |
| "How do I add a new MCP server to a Plexar profile?" | `03` section 3.1 (config shape) + `04` section 3 (patch grammar for adding a new row via `insert:`) |
| "What happens if the model calls an unknown tool?" | `02` section 3 ("Unknown and throwing tools both become structured errors") |
| "How does session resume work for headless vs. SDK vs. ACP?" | `01` sections 3, 7 (headless `--session-id`), section 2 note 7 (SDK: no resume), section 4 (ACP `session/resume`) |
| "Is anything sent to DeepSeek or elsewhere off-box?" | `05` section 3 (telemetry) + `06` section 1.1/section 8 (confirms the plexar bundle's specific disables) |
| "What does a Studio developer need to build vs. what's free?" | `06` section 3 ("What Studio must implement itself") |
| "Why can't I rewrite tool-call arguments in a hook?" | `03` section 5.1/5.4 (hooks) + `02` section 3 ("Arguments cannot be rewritten") |
| "What's the exact turn/step event sequence?" | `02` section 1 |
| "How do I route to a different model or rig endpoint?" | `04` section 4 (`llm-pi-ai` config fields) + `06` section 1.1 (the plexar row) + `04` section 7 Plexar notes |
| "What's not built yet that Studio needs?" | `06` section 6 (gap list) |

## 8. Risks

- **Upstream is developer preview with promised breaking changes.** `SAFETY.md` (cited in `docs/plexar/05-persistence-ops-and-quality.md` section 6): "experimental developer-preview software" that "has not undergone a security audit and must not be treated as secure or production-ready." Session format itself is pre-stable: `latestFinalizedVersion: 4`, `latestReleasedVersion: 3` (`docs/plexar/05-persistence-ops-and-quality.md` section 1.4) — a future breaking change to `SessionEventMap` or the SDK wire protocol is explicitly anticipated by the project's own versioning discipline (`CLAUDE.md`: "Public APIs are pre-stable; update every consumer").
- **The two fork-touching lines**: `CLAUDE.md`'s build-order note names `tsc -b tsconfig.host.json` then a Client-lib phase consuming `tsc -b tsconfig.client.json` (`docs/plexar/01-surfaces.md` section 14; `docs/plexar/05-persistence-ops-and-quality.md` section 5 "Build layout"). These two tsconfig refs are the build's face-split mechanism; `packages/client/ui-brand-plexar/src/client/index.ts` (the Plexar sidebar brand slot filler, `packages/client/ui-brand-plexar/src/index.ts` node half) is new Plexar code that must be correctly wired into whichever of these two programs' package inclusion list it belongs to — a rebase risk if upstream restructures either tsconfig. (This worker did not locate a second, more specific reference beyond these two build-phase tsconfigs within its read list; flag for the framework team to confirm exact file paths if a narrower citation is needed.)
- **Windows parity gaps from `03`**: read-only sandbox mode "reports partial enforcement for ambient ACL gaps" on the Windows ACL runner (`docs/plexar/03-tools-and-capabilities.md` section 2.1); pwsh sandbox-denial marker parity with bash is explicitly unconfirmed (section 2.2, also G8 above).
- **Anything that phones home**: none by default in this bundle, per direct verification in `docs/plexar/05-persistence-ops-and-quality.md` section 3 — `session-telemetry-otel` explicitly `disabled: true` in `packages/bundle/plexar/cordis.patch.yml`, `product-telemetry-otel` not composed into either `base` or `plexar` bundle at all. This is a config-row disable, not a code-level removal, so it must be re-verified any time the plexar bundle patch is touched (same section's Plexar notes, first bullet) — the underlying `dsh-session-telemetry-otel` package still ships and could be re-enabled by a future edit.

## 9. Cannot / does not

Collected from the current-state analysis above, plus the upstream Cannot/does not sections this digest does not restate:

- The plexar bundle **cannot** route web search — `tool-web` is configured `search: false` and `web-search-deepseek` is disabled; no search provider is composed.
- The plexar bundle **cannot** offer runtime plugin install/enable/disable — `plugin-manager` and `tool-plugin-manager` are both disabled.
- The plexar bundle **cannot** run the Ralph loop — `tool-ralph` is disabled.
- The plexar bundle **cannot** onboard a DeepSeek-cloud credential from the Web UI — `ui-settings-models.credentialOnboarding` is `false`.
- The harness, as composed today, **cannot** read or write PDF/Excel/HTML documents on the model's behalf — no MCP server or native tool provides this (G2).
- A harness worker **cannot** currently attach dynamic per-turn `X-Plexar-Orch-Run`/`X-Plexar-Orch-Node`/`X-Plexar-Brief-Sha256` headers to rig requests — only a static per-route header set is documented (section 5, G4).
- The SDK JSON-RPC surface **cannot** resume a session, close a single session, or cancel a single prompt — these methods do not exist on that wire (`docs/plexar/01-surfaces.md` section 7).
- No profile in this repo today **can** serve Studio over stdio — `plexar-sdk` does not exist yet (G1).
- The rig key currently minted (`key_9dfcca42cccd49db`) **cannot** be scoped narrower than `guest`/models `*` without a rig-side console change (G6) — this is a `plexar-vllm` concern, not a harness one.
- The `mcp-resources` row **cannot** be tuned via `config:` at all today (`docs/plexar/04-configuration-and-plugins.md` section 4/7) — scoping which MCP resources a session sees is not available as a patch-grammar-level control (G9).
- The Schedule capability **cannot** deliver a reminder while its originating session is closed — "Session-local delivery only — no external notification channel or cold-session scheduler" (`docs/plexar/03-tools-and-capabilities.md` section 7) — so it cannot back a Studio "remind me later" feature that must survive a session close (G10).

## 10. Appendix — environment variables this bundle reads

For quick reference, every environment variable the plexar bundle or its cited siblings read, consolidated from sections above:

| Variable | Consumed by | Default if unset | Source |
|---|---|---|---|
| `PLEXAR_HARNESS_KEY` | `llm-pi-ai` route `plexar`, via `apiKeyEnv` | none (rig requires it off-loopback) | `packages/bundle/plexar/cordis.patch.yml`, section 1.3 above |
| `PLEXAR_RIG_URL` | `llm-pi-ai` route `plexar`, `baseURL` | `https://llm.plexar.tech` | `packages/bundle/plexar/cordis.patch.yml` |
| `PLEXAR_MODEL` | `llm-pi-ai` route `plexar` model id, and `agent-default-model.model` | `Qwen/Qwen3.6-35B-A3B` | `packages/bundle/plexar/cordis.patch.yml` |
| `DSH_HOME` | Harness home root for all profiles (not plexar-specific) | `~/.dsh` | `docs/plexar/05-persistence-ops-and-quality.md` section 2 |
| `DSH_PERMISSION_MODE` | `sandbox-policy.mode` and the `approval.policy` expression (not plexar-specific, but inherited unmodified) | `workspace-write` (sandbox), which maps to `ask` (approval) unless `danger-full-access` | `docs/plexar/04-configuration-and-plugins.md` section 3 |
| `PLEXAR_API_KEY` | The rig gateway's own auth (`plexar-vllm`, not the harness) — distinct from `PLEXAR_HARNESS_KEY`, do not confuse the two | none | `<workspace>\plexar-vllm\docs\01-contracts.md` section 8 |

`PLEXAR_HARNESS_KEY` and `PLEXAR_API_KEY` are easy to conflate and name two different credentials at two different layers: `PLEXAR_HARNESS_KEY` is the bearer key one harness worker presents to the rig's gateway; `PLEXAR_API_KEY` (`<workspace>\plexar-vllm\docs\01-contracts.md` section 8) is the rig gateway's own control-plane auth, resolved via `plexar.config.resolve_api_key()` with `env` (`PLEXAR_API_KEY`) taking precedence over a `stored` value in `~/.plexar/secrets.json`. A harness worker never needs to set `PLEXAR_API_KEY` directly — that is an operator-side rig configuration variable, not something a `cordis.patch.yml` row references.

## 11. Glossary of Plexar-specific terms used above

Terms that are not upstream `dsh` vocabulary (upstream terms are defined in `01`-`05` and not repeated here):

| Term | Meaning |
|---|---|
| the rig | Plexar's self-hosted vLLM/Qwen inference box, reached via `PLEXAR_RIG_URL` (default `https://llm.plexar.tech`) |
| `plexar` (route) | The `llm-pi-ai` provider route name the plexar bundle registers for the rig — distinct from `plexar` (profile) and `plexar-harness` (this repo) |
| `plexar` (profile) | The headless `dsh` profile (`base + headless + plexar` bundle) |
| `plexar-web` | The interactive web `dsh` profile (`base + web-app + plexar` bundle) |
| `plexar-sdk` | The proposed (not yet built) SDK-stdio `dsh` profile for Studio embedding — Gap G1 |
| Plexar Studio | The developer-facing multiplexer product that would embed this harness over stdio |
| `plexar-chat` | The separate, public-facing conversational product repository; owns document (PDF/Excel/HTML) tooling |
| `plexar-vllm` | The separate repository/service that manages the rig's containers and exposes the OpenAI-compatible gateway plus its own control-plane API |
| rig bearer key | `PLEXAR_HARNESS_KEY` — the credential a harness worker presents to the rig's inference gateway (distinct from `PLEXAR_API_KEY`, the rig's own control-plane auth) |

## Plexar notes

- The single highest-leverage next step for Studio embedding is standing up `plexar-sdk` (G1) — it is config-only (a new profile directory plus the same small patch-overlay pattern `plexar`/`plexar-web` already use), not a fork edit, and unblocks testing the entire SDK method/notification sequence in section 3 against the real rig.
- The `X-Plexar-Orch-*` correlation headers (section 5) are the rig's own mechanism for "how many agents are running right now" (`<workspace>\plexar-vllm\docs\01-contracts.md` section 10l) — if Plexar wants per-subagent visibility on the rig's live registry, this needs either an upstream `llm-pi-ai` feature request (per-request headers) or a small fork-level adapter change; do not assume it is achievable purely by config today (G4).
- `plexar-chat`'s `chat/office` code is the validated asset; the harness-side integration work is entirely on the MCP-server wrapper (G2) and the one `dsh-mcp-client` config row — no document-parsing logic belongs in this repo.
- The bundle's `headers`/`apiKeyEnv` split (static config, per-request credential resolution) means rotating `PLEXAR_HARNESS_KEY` needs no harness restart — useful for any long-running Studio-embedded session, but it also means the key's scope (`guest`, models `*`) is a standing exposure until G6 is addressed on the rig side, independent of anything the harness does.
- Telemetry is confirmed off by default in this bundle (section 8), so Studio gets zero automatic usage signal from the harness — any product analytics Studio wants must come from Studio's own instrumentation, not from `ctx.productTelemetry` or `ctx.sessionTelemetry`, both of which are unwired here.
- The capability matrix (section 2) should be re-run whenever the plexar bundle patch changes — several "untested" rows (MCP, hooks, LSP, scheduling, ACP) are untested specifically because no profile in this repo currently composes them alongside the `plexar` model route; standing up G1/G7 will convert several "untested" cells to "yes"/"no" with real evidence.
- Given "Multi-tenant: Absent" and "Auth: none on stdio" in the capability matrix, any path from `plexar-chat` (public, multi-tenant) to the harness (single-tenant, no wire auth) must go through Chat's own `upstream/` boundary and never let a Chat user reach a raw harness stdio pipe directly — this is the same boundary already enforced by `<workspace>\plexar-chat\CLAUDE.md`'s "not Studio with the tools removed" distinction.
