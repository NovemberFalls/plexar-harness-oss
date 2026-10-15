# 07 — Studio API contract (v3)

The pinned wire between Plexar Studio (`<workspace>\plexar-studio`) and the Plexar Harness.
Every behavior below was observed against the live rig on 2026-09-22.

Wire fingerprint: `6531d90f466fa00c`

The fingerprint hashes the upstream ACP surface: its request handlers, config option ids, permission
option ids and the pinned `@agentclientprotocol/sdk` version. `check_api_drift.py` recomputes it. If it
moves, the upstream wire changed: re-read `packages/acp/acp/src`, update this doc and the client, then re-pin.

**v3 (2026-09-23)** adds the launcher (`plexar-harness acp`), distinct pre-ACP failure exits and `HarnessError.exit_code`/`reason`; the wire is unchanged from v2. **v2 replaced v1.** v1 spoke the SDK JSON-RPC surface, which cannot list, resume, cancel or close a session.
v2 speaks ACP to the `plexar-acp` profile, which can, so Studio houses harness sessions the way it houses
Claude Code and Codex sessions.

## Files

| File | Role |
|---|---|
| `packages/bundle/plexar/studio/plexar_harness_client.py` | The client Studio vendors. Stdlib only. `HarnessRuntime` is the whole API. |
| `packages/bundle/plexar/studio/check_api_drift.py` | Drift gate. Exit 0 in sync, 1 on drift. |
| `packages/bundle/plexar/cli/acp-launch.mjs` | The launcher's `acp` subcommand: pre-ACP checks, profile creation, then the profile over stdio. |
| `packages/bundle/plexar/studio/fake_rig.py` | Fake OpenAI-compatible rig for rigless CI. |
| `packages/bundle/plexar/profiles/install.ps1` | Creates or refreshes all four Plexar profiles. |
| `packages/bundle/plexar/profiles/plexar-acp.patch.yml` | Points the `acp` row at the `plexar` route. |
| `packages/acp/acp/src/index.ts` | Upstream ACP server: the source of truth. |
| `packages/acp/acp/README.md` | Upstream ACP reference. |

## Launch (v3)

Studio starts the harness through the `plexar-harness` launcher, from any working directory, with no tsx loader or `TSX_TSCONFIG_PATH`:

```
node <launcher dir>/plexar-harness.mjs acp        # what HarnessRuntime.command() runs
plexar-harness acp                                # the same, from a shell
plexar-harness acp --no-preflight                 # skip the rig check (or PLEXAR_HARNESS_PREFLIGHT=0)
```

`HarnessRuntime.command()` finds `plexar-harness` on `PATH` and runs its `.mjs` with the same Node, so no `.cmd` shim sits between Studio and the process. Without the launcher it falls back to the source launch under `harness_root` (development only).

**Before ACP starts**, the launcher checks, in order. Each failure writes one stderr line `plexar-harness: error <code>: <sentence>` and exits with its own code. `HarnessError.exit_code` and `HarnessError.reason` carry them to Studio.

| Exit | `reason` | Cause |
|---|---|---|
| 10 | `node_too_old` | Node older than 22.19 (the harness itself would exit 0 silently) |
| 11 | `key_missing` | `PLEXAR_HARNESS_KEY` not set |
| 12 | `profile_install_failed` | `plexar-acp` was absent and could not be created |
| 13 | `key_rejected` | The rig answered 401/403 to the key |
| 14 | `rig_unreachable` | The rig did not answer within 8 s |

After the checks, failures surface on the wire: a rig error during a turn is a JSON-RPC `-32603` on `session/prompt` whose message carries the rig's text (401, `engine_unavailable` while the model loads, `Connection error.`). `initialize` and `session/new` do not contact the rig.

**Profile:** the launcher creates `plexar-acp` on first run (same steps as `profiles/install.ps1`), under `DSH_HOME` or `~/.dsh`. Each OS user gets their own.

**Install on a machine:** clone the private `NovemberFalls/plexar-harness`, install Node 22.19+ and pnpm, run `pnpm install`, then `powershell -File packages/bundle/plexar/profiles/install.ps1` (puts the launcher on the user `PATH`). There is no npm package or zip yet.

**Keys:** the only credential Studio passes is `PLEXAR_HARNESS_KEY` in the child environment, one per user. The launch environment wins over every other source (the harness's stored-credentials file, the project `.env`, the harness-home `.env`; `packages/credentials/credentials-local/README.md`), so a key Studio sets cannot be shadowed. When Studio does not set it, a key from those files is used, so Studio should always set it explicitly. Keys are minted on the rig by its owner (`ssh` to the rig, rig console); a self-service "request a key" page in the plexar-llm dashboard is harness work item 11, not built.

**Rig address:** the default is `https://llm.plexar.tech` (public). `PLEXAR_RIG_URL` overrides it; the LAN address `http://<rig-lan-address>:8760` only answers on the owner's LAN.

**Effort is per model.** `reasoning_effort` is built from the currently selected model (`packages/acp/acp/src/model-control.ts`): its choices are that model's declared efforts, and the option is omitted entirely for a model that declares no reasoning. After `set_config_option` changes `model`, read the `configOptions` in its reply (the full new list) and redraw the effort picker from it; a later `config_option_update` notification carries the same list when the provider catalog changes. Today the `plexar` provider declares one chat model, `qwen3.8-27b`, with efforts `off` and `high` plus "Provider default" (value `""`).

**CI without a rig:** `packages/bundle/plexar/studio/fake_rig.py` is a stdlib OpenAI-compatible server that answers every chat with `PLEXAR_OK` (or `FAKE_REPLY`) and rejects the key `rejected` with 401. Run it, then start the runtime with `PLEXAR_RIG_URL=http://127.0.0.1:<port>` and any key: the full harness runs, and `key_rejected` / `rig_unreachable` can be exercised on purpose.

## Process model

- **One runtime per workspace.** `HarnessRuntime(workspace).start()` runs `plexar-harness acp` (see Launch) with `cwd` = the workspace.
- **Sessions outlive the runtime.** `stop()` ends the process; every session stays on disk and a later runtime resumes it.
- **Env:** `PLEXAR_HARNESS_KEY` is required. `PLEXAR_MODEL`, `PLEXAR_RIG_URL` and `DSH_PERMISSION_MODE` are optional.
- **Framing:** newline-delimited JSON-RPC 2.0 on stdio. Stdout is frames only; stderr is diagnostics.
- **Storage:** `%USERPROFILE%\.dsh\sessions\<encoded cwd>\<sessionId>\session.v4.jsonl.zstd`, an append-only compressed log.

## Studio lifecycle ↔ client ↔ wire

| Studio action | Client call | Wire |
|---|---|---|
| Start harness for a workspace | `start()` | spawn, then `initialize` (protocol version 1) |
| New chat | `new_session()` | `session/new` → `sessionId`, `configOptions` |
| Session list | `list_sessions()` | `session/list`, newest first, filtered to the workspace, paged by `cursor` |
| Reopen a chat | `resume_session(id)` | `session/resume` → `configOptions`; history restored, not replayed |
| Send a message | `prompt(id, text)` or `prompt_async(...)` | `session/prompt` → `stopReason` |
| Stop generating | `cancel(id)` | `session/cancel` notification; the prompt returns `cancelled` |
| Pick model | `set_model(id, model)` | `session/set_config_option` with `configId` `model` |
| Pick effort | `set_effort(id, "off"\|"high")` | `session/set_config_option` with `configId` `reasoning_effort` |
| Close a chat | `close_session(id)` | `session/close`; it stays resumable |
| Tool approval | `on_permission` callback | agent → client `session/request_permission`; answer `allow-once` or `reject-once` |
| Stop harness | `stop()` | close stdin; bounded shutdown flushes every session |

### Streamed output

`session/update` notifications arrive for every session in the runtime; filter by `session_id`.
`Update.kind` is the ACP `sessionUpdate` value. Kinds, with whether a live run has shown them:

| Kind | Carries |
|---|---|
| `agent_message_chunk` | Answer text, `content.text`. `text_of()` joins them. Observed. |
| `agent_thought_chunk` | Reasoning text, `content.text`, keyed by `messageId`. Observed at effort `high` (2026-09-22). |
| `tool_call`, `tool_call_update` | Tool name, arguments, status and output for tool cards. Observed. |
| `usage_update` | Context usage. Observed. |
| `config_option_update` | Model or effort changed. Documented upstream; not yet observed. |

## Measured on 2026-09-22

| Scenario | Result |
|---|---|
| New session, effort off, one-line prompt | `end_turn`, answer `PLEXAR_OK` |
| Close, stop, new runtime, list | Stopped session listed |
| Resume, ask about the earlier turn | Answer `ZEBRA-42`: memory survived the restart |
| Long prompt, cancel after 6 seconds | `stopReason` `cancelled` |
| Skills catalog | All seven `orch-*` skills in `packages/bundle/plexar/skills/` visible to the model |
| `DSH_PERMISSION_MODE=read-only`, ask for a file write | One approval prompt; answered `allow-once`; file written |

## Approvals

Approval prompts reach Studio only when the sandbox needs to escalate. Under the default
`workspace-write`, in-workspace edits and commands run without asking, and a `git push --dry-run`
ran unprompted in testing. Under `read-only` every write asks. Studio chooses the mode per runtime
through `DSH_PERMISSION_MODE`. The client's default answer is `reject-once`, so a Studio that has not
wired a prompt fails closed.

## What Studio must build

1. **A third session kind, `plexar-harness`,** beside `claude-code` and `codex`. It is not a PTY.
2. **One `HarnessRuntime` per open workspace,** started on first use and stopped on workspace close.
3. **The session list from `list_sessions()`,** merged with Studio's own labels (see below).
4. **Rendering from `session/update`:** thought, answer, tool cards, usage.
5. **An approval dialog** behind `on_permission`, plus a mode picker for `DSH_PERMISSION_MODE`.
6. **Model and effort pickers** fed from each session's `configOptions`.

## Cannot / does not (v2)

- **No titles or rename on this wire.** List rows carry only `sessionId` and `cwd`. The harness stores titles in the session log, but ACP exposes none. Studio keeps its own label per `sessionId` until a Plexar plugin adds it.
- **Live sessions are not listed.** `session/list` returns persisted, inactive sessions. Studio already knows which sessions its runtime has open.
- **No delete, fork, or load.** Upstream rejects them.
- **One prompt in flight per session.** Queue in Studio, or cancel first.
- **Slash commands ride `session/prompt`.** A prompt that is exactly one text block starting with `/` and naming a registered harness command (`/permission`, `/compact`, `/goal`, `/feedback`, `/rename <title>`, ...) runs that command instead of a model turn. The result arrives as one `agent_message_chunk` and the prompt returns `end_turn`. Unregistered `/...` text goes to the model unchanged. Plexar change to `packages/acp/acp/src/session.ts` (`runCommand`), 2026-09-23.
- **Permissions are per session.** `/permission` lists presets; `/permission read-only|workspace-write|danger-full-access` switches the current session in place, recorded in its log. `DSH_PERMISSION_MODE` only sets the default for new sessions.

## Keeping it current

1. After every `git merge upstream/master`, run `python packages/bundle/plexar/studio/check_api_drift.py`.
2. On drift the output names what moved: a handler, a config option, a permission id, the ACP SDK version, or the fingerprint.
3. Update the client and this doc together, bump `CONTRACT_VERSION` if Studio must change, re-pin with `--print-fingerprint`.
4. Re-run the smoke: `python packages/bundle/plexar/studio/plexar_harness_client.py <workspace>`.

## Plexar notes

- The rig route, key and model come from the bundle and profile; Studio never sends credentials over this wire.
- Effort levels `off` and `high` map to vLLM's Qwen `enable_thinking` switch through `thinkingFormat: qwen-chat-template`.
- The orch skills ship in `packages/bundle/plexar/skills/`; new in-house skills go there as `<name>/SKILL.md`.
