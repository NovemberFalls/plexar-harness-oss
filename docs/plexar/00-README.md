# Plexar Harness — documentation

> **Start at `CONTINUATION.md`** in the repo root: full state, decisions, next work and a continuation prompt.

`plexar-harness` is a fork of `deepseek-ai/deepseek-harness` ("dsh") — an all-plugin Cordis agent harness — patched by one small bundle, `packages/bundle/plexar/`, to route model traffic to Plexar's self-hosted vLLM/Qwen rig instead of DeepSeek's cloud, and to embed as a coding agent in Plexar Studio. This directory (`docs/plexar/`) is a from-scratch digest of the upstream harness plus the Plexar-specific integration built on top of it, written for two audiences who have never seen this codebase: the Plexar framework team and the Plexar Studio team.

## The documents

| Doc | One-line purpose | Audience |
|---|---|---|
| [`01-surfaces.md`](01-surfaces.md) | Every entry point into `dsh` — Web, Headless, SDK, ACP, Webhook, CLI — with exact wire/CLI contracts, method/notification tables, and event streams | Both |
| [`02-kernel.md`](02-kernel.md) | The agent kernel: the turn/step model, durable SessionEvent log vs. live `agent/*` events, tool execution pipeline, system-prompt assembly, the `llm-pi-ai` adapter seam, compaction, subagents, goal/plan/todo/user-questions | Framework team |
| [`03-tools-and-capabilities.md`](03-tools-and-capabilities.md) | Every model-facing tool, the sandbox/approval system, MCP, Skills, Hooks, LSP, jobs/schedule/workflow/PTC, web/browser/computer use, and what does not exist yet | Both |
| [`04-configuration-and-plugins.md`](04-configuration-and-plugins.md) | Cordis plugin model, profile/bundle composition and precedence, the `cordis.patch.yml` grammar, the ten config rows Plexar cares about, settings vs. credentials vs. env | Framework team |
| [`05-persistence-ops-and-quality.md`](05-persistence-ops-and-quality.md) | Session log format/durability/crash-recovery, storage/settings/credentials on disk, telemetry (what phones home, and that this bundle disables it), token metering, build/test commands, safety notice and license obligations | Both |
| [`06-plexar-integration-and-gaps.md`](06-plexar-integration-and-gaps.md) | What Plexar has done with the harness: the `plexar` bundle row by row, a capability matrix, the Studio stdio-embedding recipe, the `plexar-chat` document-tooling relationship, rig-lane orchestration headers, and a prioritized gap list | Both |
| `docs/plexar/07-studio-api-contract.md` | Pinned Studio wire (v1): launch, requests, notifications, event shapes, drift check | Studio team |
| [`08-cli.md`](08-cli.md) | The `plexar-harness` terminal client: install, flags, commands, rendering, exit codes | Everyone |
| [`09-session-export.md`](09-session-export.md) | `plexar-harness export`: session transcripts, line format, versioning | Framework team |

Docs `01`–`05` are final and cite only upstream `dsh` files (English-only sources; `.zh.md`/`.i18n.yaml` skipped). Doc `06` is the Plexar-specific synthesis and additionally cites `packages/bundle/plexar/`, `packages/client/ui-brand-plexar/`, and sibling-repo sources (`plexar-vllm`, `plexar-chat`).

## Why a fork, not a wrapper

`dsh` is an all-plugin Cordis tree: "There is no privileged core to patch; you extend dsh by mounting a plugin beside the others" (`docs/architecture.md`, cited in `04-configuration-and-plugins.md` section 1). Plexar exploits this directly: `packages/bundle/plexar/` is one `cordis.patch.yml` file that composes over `dsh-base`/`dsh-headless`/`dsh-web-app` without editing a single upstream file (`06-plexar-integration-and-gaps.md` section 1.1). This is the load-bearing fact for both audiences — the framework team should expect every future Plexar-specific change to land as a new patch row or a new profile, not a fork-wide edit, and the Studio team should expect the harness itself to stay rebasable against upstream (`packages/bundle/plexar/README.md`, "Rebase": "this bundle lives only in `packages/bundle/plexar/`, which upstream never touches").

## Where things live

- **Upstream harness code**: `packages/` (grouped by capability — `core/`, `llm/`, `sandbox/`, `mcp/`, `sdk/`, `acp/`, and more; full group map in `packages/README.md`, cited from `CLAUDE.md`).
- **The Plexar patch**: `packages/bundle/plexar/cordis.patch.yml` (model route, persona, disabled rows) and `packages/bundle/plexar/README.md` (install/run instructions, gotchas).
- **The Plexar browser brand**: `packages/client/ui-brand-plexar/` (Node-half Loader seat plus a Client-half `exports["./client"]` module — `04-configuration-and-plugins.md` section 5).
- **This documentation**: `docs/plexar/` (this directory) — separate from upstream's own `docs/` tree, which `01`–`05` cite extensively but never edit.

## Quickstart

```sh
# Install (once) — creates $DSH_HOME/profiles/plexar and links the bundle
pnpm dsh --profile plexar --from-default-profile headless --help
pnpm dsh plugin --profile plexar add link:<abs path>/packages/bundle/plexar

# Key — bearer key minted by the rig, required off-loopback
export PLEXAR_HARNESS_KEY=<rig bearer key>

# Run headless — one task, prints the final answer, exits
pnpm dsh --profile plexar "run the tests"

# Run web — interactive browser GUI at http://127.0.0.1:3080 (needs a build first)
pnpm run build
pnpm dsh --profile plexar-web
```

`PLEXAR_RIG_URL` overrides the rig base (`https://llm.plexar.tech`); `PLEXAR_MODEL` overrides the served model (`Qwen/Qwen3.6-35B-A3B`). Full gotchas (Node version, source-mode tsconfig, WireGuard conflicts) are in `packages/bundle/plexar/README.md` and repeated in `docs/plexar/04-configuration-and-plugins.md` section 5 and `docs/plexar/06-plexar-integration-and-gaps.md` section 1.4.

## How to read this in an hour

1. **`06-plexar-integration-and-gaps.md`, sections 1–2** (10 min) — the plexar bundle row-by-row and the capability matrix. This is the fastest way to know what already works.
2. **`01-surfaces.md`, sections 1, 2, 8** (10 min) — the surface table, the SDK method/notification inventory, and the CLI profile model. Essential before touching Studio embedding.
3. **`04-configuration-and-plugins.md`, sections 1–3** (10 min) — Cordis in one page, profile/bundle layering, and the patch grammar. Essential before editing any `cordis.patch.yml`.
4. **`06-plexar-integration-and-gaps.md`, sections 3–6** (15 min) — the Studio stdio recipe, the `plexar-chat` relationship, rig-lane headers, and the gap list. This is the actionable plan.
5. **`02-kernel.md`, sections 1–3** (10 min) — turn/step model and tool execution pipeline, for anyone building a new Cordis plugin against these extension points.
6. **`03-tools-and-capabilities.md`, sections 2–3** (5 min) — sandbox/approval and MCP, needed before wiring the `chat/office` MCP server (Gap G2).
7. **`05-persistence-ops-and-quality.md`, sections 3, 6** (5 min) — telemetry (confirms nothing phones home) and the safety notice, for anyone shipping this to a Studio user.
8. **`06-plexar-integration-and-gaps.md`, sections 7–9** (5 min) — risks, Cannot/does not, and Plexar notes, as a final pre-flight check.

Total: roughly 65 minutes of reading covers the whole set at the depth needed to start work confidently in either the framework repo (`plexar-harness`) or the Studio embedding.

## Who should read what

- **Plexar framework team** (people changing or extending the harness itself, writing new Cordis plugins, or reviewing a rebase against upstream `dsh`): read all six in the order above, with extra attention to `02-kernel.md` (extension points) and `04-configuration-and-plugins.md` (patch grammar and precedence).
- **Plexar Studio team** (people embedding the harness as Studio's coding-agent backend, with no plans to modify harness internals): `00` (this doc), `01` sections 1–2, `06` in full, and `03` sections 2–3 for sandbox/approval and MCP context. `02`, `04`, and `05` are reference material to consult when a specific question comes up, not required front-to-back reading.
- **Anyone debugging a live `plexar`/`plexar-web` session**: start at `06-plexar-integration-and-gaps.md` section 1 (current state) and section 8 (Cannot/does not) before filing a bug — many apparent defects are documented upstream limitations, not regressions in the Plexar bundle.

## Conventions used across these docs

- A backticked path (e.g. `` `packages/bundle/plexar/README.md` ``) is always a real, openable file — repo-relative for `plexar-harness` sources, or an absolute Windows path for the two cited sibling repos (`plexar-vllm`, `plexar-chat`).
- "Native" means the upstream harness ships and enables the capability by default or via straightforward config; "experimental" means an upstream package exists but requires explicit opt-in and is marked pre-GA; "absent" means no such capability exists in the read source set.
- A "Cannot / does not" subsection is always a direct upstream or Plexar-specific limitation, never an inferred guess — every such claim traces to a quoted or paraphrased source line.
- Gap identifiers (`G1`, `G2`, …) in `06-plexar-integration-and-gaps.md` section 6 are stable within that document; cite them by id when discussing prioritization across teams.
