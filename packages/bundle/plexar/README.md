# @plexar/dsh-plexar

The Plexar coding profile for DeepSeek Harness. One patch file, applied over
`dsh-base` and `dsh-headless`; no upstream file is edited. Trimming means
composing a smaller tree, not deleting code.

## Web UI (interactive)

Profile `plexar-web` = base + web-app + this bundle, plus a profile patch disabling
`account-controller` and `ui-settings-account` (they hard-inject the DeepSeek account
service). Needs a built tree: `pnpm run build` (Node 24). Then `pnpm dsh --profile plexar-web`
opens `http://127.0.0.1:3080`.

## Install (once)

```sh
pnpm dsh --profile plexar --from-default-profile headless --help   # creates $DSH_HOME/profiles/plexar
pnpm dsh plugin --profile plexar add link:<abs path>/packages/bundle/plexar
```

## Run

```sh
export PLEXAR_HARNESS_KEY=<rig bearer key>
pnpm dsh --profile plexar "run the tests"
pnpm dsh --profile plexar --json "summarize this repo" > events.jsonl
```

`PLEXAR_RIG_URL` overrides `https://llm.plexar.tech`; `PLEXAR_MODEL` overrides `Qwen/Qwen3.6-35B-A3B`.

## What is switched off

DeepSeek cloud model + account + web search + telemetry; plugin marketplace;
ralph loop. Everything else in base stays: bash/pwsh sandbox, fs tools,
skills, plan mode, compaction, subagents, MCP, web fetch.

## Plugins

- `plexar-tool-scaffold` (`src/tool-scaffold.ts`): `toolProfile` (`lean` in the bundle row, from `PLEXAR_TOOL_PROFILE`; `full` restores every tool), `leanDeny`, `repairHints`, `schemaHintMaxChars`. Lean hides the subagent, workflow, goal and job tools; repair hints append the parameter schema to invalid-argument errors.
- `plexar-workspace-fence` (`src/workspace-fence.ts`): `enabled`, `outside` (`ask` or `deny`), `extraRoots`, `tools`. File tools outside the session workspace ask or are denied in every permission mode; shell tools are not fenced.

## Bring your own endpoint

`PLEXAR_BYO_BASE_URL` (a full `/v1` base) plus `PLEXAR_BYO_MODEL` selects the `byo` provider and skips Plexar sign-in and the rig. Optional: `PLEXAR_BYO_API_KEY`, `PLEXAR_BYO_CONTEXT` (131072), `PLEXAR_BYO_MAX_TOKENS` (32768). `plexar-auth`, `plexar-models` and `plexar-revocation` are disabled.

```sh
export PLEXAR_BYO_BASE_URL=http://localhost:8080/v1
export PLEXAR_BYO_MODEL=qwen3-27b
plexar-harness -p "list the TODOs in this folder"
```

## Eval and timings

`plexar-harness eval` runs `evals/<id>/task.json` tasks and appends a pass-rate line to `~/.dsh/plexar-evals/<date>.jsonl`; `--timings` shows startup phases and per-turn first-token time and rate. Details: `docs/plexar/08-cli.md`.

## Rebase

`git fetch upstream && git rebase upstream/main` — this bundle lives only in
`packages/bundle/plexar/`, which upstream never touches.

## Updates

In a git checkout, the CLI's launch notice and Settings' `plexarUpdate` Remote (`src/update.ts`)
check `origin` via `git ls-remote`. An installed copy (the Windows installer's runtime, no `.git`)
has no `origin`, so both instead poll the release manifest (`PLEXAR_RELEASE_MANIFEST`, default
`https://downloads.plexar.tech/harness/latest.json`) and compare its `version` against the local
`package.json` version; any failure (offline, non-200, invalid JSON, timeout) means no notice. On
an installed copy, `plexar-harness update` and `apply()` never run git or pnpm — they point at the
desktop app's own updater or `https://harness.plexar.tech` instead.

## Gotchas (measured 2026-09-22)

- **Node ≥ 22.19 or 24.** The CLI entry guards on `import.meta.main`; older Node exits 0
  silently with no output. This box runs 24.19.
- **Source mode needs the repo tsconfig.** `pnpm dsh` resolves `@deepseek-ai/*` to `src/`
  through tsconfig paths. Running from another cwd (your real workspace) requires
  `TSX_TSCONFIG_PATH=<harness-checkout>/tsconfig.json` and the absolute loader:
  `node --import file:///<harness-checkout>/node_modules/tsx/dist/esm/index.mjs <harness-checkout>/apps/cli/src/bin.ts --profile plexar "<task>"`.
- **`typert-loader` warns "1 entry did not activate"** in source mode because `lib/typert.host.js`
  is unbuilt. Harmless for headless runs; goes away with a built `lib/`.
- **Rig key.** Off-loopback the rig requires a bearer. `PLEXAR_HARNESS_KEY` is minted (2026-09-22): rig key `key_9dfcca42cccd49db`, label
  "Plexar Harness", scope guest, models `*`, visible in the plexar-llm console key table.
  Stored in Len's Windows user env; new shells pick it up, existing ones need a restart.
- **WireGuard.** The work VPN hijacks `the LAN subnet`; if the rig times out, drop the tunnel.

## Studio (ACP over stdio, contract v2)

Profile `plexar-acp` = base + acp-app + this bundle, plus `profiles/plexar-acp.patch.yml`.
Create or refresh all four profiles with `powershell -File packages/bundle/plexar/profiles/install.ps1`.
Contract: `docs/plexar/07-studio-api-contract.md`. Client Studio vendors: `studio/plexar_harness_client.py`
(start, stop, list, resume, prompt, cancel, close, model, effort, approvals). After every upstream merge
run `python packages/bundle/plexar/studio/check_api_drift.py`; exit 1 means the wire moved.

## Use my Chrome

The `plexar-browser-playwright` row loads `src/browser-bridge`, which serves the Playwright browser tools either in the person's own Chrome or Edge (through the Plexar Browser Bridge extension, `apps/plexar-browser-extension`) or in a browser window of the agent's own. The model sees the same tools either way.

Config: `connectTimeoutMs` (default 20000; the Plexar row sets 60000 so a person has time to read the approval page and pick a tab) is how long the process's first Session waits for the extension to connect; `extensionIds` (default: the Chrome Web Store id `gnjeciecdiicngbfdancnklpnnmcekll`, then the load-unpacked development id `cnfgenfphpnhddlefhminclbbjdgkbbd`; each 32 letters a-p) lists the extensions in preference order: the first one installed is the one whose connect page is opened and whose `chrome-extension://` origin alone may use the relay's `/extension` path; `headless` (from `PLEXAR_BROWSER_HEADLESS=1`), `chromePath`, and `toolCallTimeoutMs` are optional.

Per Session, while the Settings > Features switch `useMyChrome` is on, the plugin first checks every Chrome and Edge profile under the standard user-data directories for a `Preferences` or `Secure Preferences` file listing one of `extensionIds` under `extensions.settings` (store and load-unpacked installs). Not installed: it opens nothing, does not wait, and launches its own window. Installed: the process shares one relay on 127.0.0.1. The first Session starts it, opens the connect page once, and the extension shows the process as one colored tab group titled after the working directory. Every Session then attaches through its own relay client with its own random token, sees only the tabs it opened (the first connected Session also gets the connect page's tab and tabs the person drags into the group), and closes those tabs when it ends. When the process exits, is killed, or unloads the plugin, the extension closes every tab the agent opened and ungroups the person's own. If the extension disconnects, the next Session opens a new connect page. A miss (not installed, no browser found, or no connection in time) launches the agent's own window, logs one install hint to the person per activation, and is final for the process, so later Sessions open no further connect pages. `plexar-harness -p` sets `PLEXAR_UNATTENDED=1`, which skips the person's browser entirely and runs the agent's own browser headless.

Upstream seams: `mountSessionMcp` in `@deepseek-ai/dsh-experimental-browser-use-runtime/mcp` accepts a per-Session `prepare` that picks the server arguments and a `close`, and `playwrightMcpLaunch` in `@deepseek-ai/dsh-experimental-browser-use-playwright-mcp` builds launch or attach arguments. Both changes are listed in `CONTINUATION.md` under "Upstream lines we touch".

## Skills

`skills/<name>/SKILL.md` bundles mount through the `skill-filesystem` `customSkillDirs` row. The ten
`orch-*` skills are ported from Claude Code with a harness tool map on top; build new ones here.

## Document tools

`cordis.patch.yml`'s `plexar-document-tools` row mounts `python/tools`' `plexar_tools` MCP server
(`python -m plexar_tools.harness_mcp`, chat-DEC-397) over stdio, giving the model `mcp__plexar-doc__*`
read/find/query/convert/extract/create tools that take a file `path` (resolved inside the folder the
harness process started in, which refuses anything outside it; `plexar-workspace-fence` also asks before any `path` or `sources` value outside the session workspace) instead of inline bytes. `PLEXAR_PYTHON` overrides the
interpreter; `failOnStartupError: false` means a machine without a usable Python 3.12+ still starts
Harness, just without these six tools. See [python/tools/README.md](../../../python/tools/README.md).

Known limitations:

- **No Features switch.** Settings > Features turns plugins off by package, and every stdio MCP server in the bundle is the same package (`@deepseek-ai/dsh-mcp-client`), so a switch for these tools would also turn off every other MCP server. To turn off only the document tools, add `- id: plexar-document-tools` with `disabled: true` to the profile's `cordis.patch.yml`. A per-row switch needs the Features catalog to toggle by row id.
- **Python is required.** Until the Windows installer bundles its own Python, the tools need Python 3.12+ on PATH or at `PLEXAR_PYTHON`.
- **One folder per host.** The allowed folder (`PLEXAR_TOOLS_ROOT`) is the host process's working folder when it starts. The CLI starts one host per folder, so this matches the session. In the Web UI and desktop app, one host serves every session, so sessions opened in other folders still resolve paths against the host's starting folder.

## Effort

Qwen declares `off` and `high`, sent as vLLM's `enable_thinking` via `thinkingFormat: qwen-chat-template`.
