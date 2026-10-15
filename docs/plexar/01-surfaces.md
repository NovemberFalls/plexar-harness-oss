# Surfaces -- every way a program or person drives the harness

Audience: Plexar framework team and Plexar Studio team. This inventories every entry point into `dsh` (the harness launcher, forked here from `deepseek-ai/deepseek-harness`), what each is for, and its exact wire/CLI contract. All claims trace to files opened directly; see citations inline.

## 1. Surface table

| Surface | What it's for | How it starts | Transport | Auth |
|---|---|---|---|---|
| Web (`dsh web`) | Interactive multi-turn browser GUI | `dsh web` / `dsh --profile web` boots `dsh-host-webserver` + `dsh-host-frontend-static` fallback | `node:http`, loopback (`127.0.0.1`) by default; `0.0.0.0` requires explicit opt-in and `dsh web` itself rejects `--host 0.0.0.0` (`apps/cli/README.md`) | Connection plugin supplies Host/Origin checks + browser-session token auth for every Host API route and stream (`docs/subsystems/web-server.md`) |
| Headless (`dsh --profile headless`) | One-shot scripted/CI task, prints final answer, exits | `dsh --profile headless "task"` (task from arg or stdin) | Process stdio; stdout = answer or `--json` NDJSON event stream, stderr = `dsh: reasoning:` deltas and diagnostics | None -- local process invocation |
| SDK (`dsh --profile sdk`, JSON-RPC stdio) | Out-of-process programs (TS/Python SDK clients) drive agent sessions | `dsh --profile sdk` (auto-launched by SDK clients as a subprocess) | Newline-delimited JSON-RPC over stdio; stdout carries only protocol frames | None on the wire -- trust is the parent process that spawned the subprocess |
| sdk-minimal (`dsh --profile sdk-minimal`) | Minimal standalone coding-agent tree for SDK clients that need a small explicit runtime | `dsh --profile sdk-minimal` (same `dsh-sdk-jsonrpc-server`/`dsh-sdk-app` startup provider, different composed tree) | Same as SDK: JSON-RPC stdio | None -- same as SDK |
| ACP (`dsh --profile acp`) | Standard Agent Client Protocol automation: out-of-process subagents, test runners, scripted controllers | `pnpm dsh --profile acp` / `dsh --profile acp` | JSON-RPC stdio (ACP v1); stdout reserved for ACP frames | `authenticate` always succeeds immediately -- "the server requires no authentication" (`packages/acp/acp/README.md`) |
| Webhook | Turn authenticated external deliveries (e.g. GitHub) into ordinary Sessions | Provider adapter (e.g. `dsh-webhook-github`) registers a route on an injected `WebServer`; `ctx.webhookRuntime` dispatches matching rules | HTTP POST to the adapter's registered route, normally on an isolated second `WebServer` | Provider adapter owns authentication (e.g. GitHub signature verification of the untouched JSON body) before parsing (`docs/subsystems/webhook.md`) |
| CLI flags (`dsh` launcher) | Select and boot a profile, inspect/dump config, manage plugins | `dsh <name>` / `dsh --profile <name>` / `dsh plugin ...` | Local process argv | None -- local invocation |

## 2. Complete JSON-RPC method + notification inventory (SDK server)

Source of truth, read directly: `packages/sdk/server/src/server.ts` (dispatcher `handleRequest`) and `packages/sdk/protocol/src/types.ts` (`HarnessSdkRequestMap` / `HarnessSdkNotificationMap`).

### Requests (client -> server)

| Method | Params | Result | Notes |
|---|---|---|---|
| `initialize` | `InitializeParams { cwd, provider, model, reasoningEffort?, maxTokens? }` | `InitializeResult { serverInfo: { name: 'deepseek-harness-sdk-runtime', version } }` | Runtime-readiness boundary; waits for the Loader tree to settle. Validates the provider/model route via the selected adapter; mounts the `deepseek-official` DeepSeek adapter as the only automatic fallback for an unowned provider. `session/prompt` rejects until this completes. |
| `session/prompt` | `SessionPromptParams { sessionId, contentBlocks: SdkPromptContentBlock[] }` | `SessionPromptResult { messageId }` | Queues one user message; lazily creates the agent+session pair for an unknown `sessionId`. Returns immediately on enqueue -- no per-prompt result or assistant-message correlation. Requires prior `initialize`. |
| `shutdown` | `undefined` | `Record<string, never>` (`{}`) | Disposes server-owned agents, adapter fiber, and subscriptions to quiescence; the surrounding root context is disposed by the app bin, not this call itself, per the package README (`packages/sdk/server/README.md`). Idempotent via a memoized shutdown task. |

Any other method name throws `unknown DeepSeek Harness SDK runtime method: <method>` (`packages/sdk/server/src/server.ts`, line 257).

### Notifications (server -> client)

| Notification | Payload | Emitted when |
|---|---|---|
| `session.event` | `SessionEventNotification { sessionId, event: SessionEvent }` | On every `session/event` Cordis event, for every session in the runtime context -- not only SDK-created ones. |
| `session.status` | `SessionStatusNotification { sessionId, status: 'idle' or 'running' }` | On every `agent/status` Cordis event (whole-agent lifecycle transition). |
| `subagent.started` | `SubagentStartedNotification { parentSessionId, childSessionId }` | On `session/created` when the new session's header has a `parentSession`. |
| `subagent.finished` | `SubagentFinishedNotification { provider, agentId, parentSessionId, childSessionId, status, stopReason, lastAssistantMessage? }` | On `subagent/end`, but only when the service-snapshotted lifecycle `local` flag is true -- remote/out-of-process subagent runs are never reported this way. `status` is deployment-mapped: `completed` -> `ok`; `max-tokens` -> `ok` only if `maxTokensAsSuccess` config is `true`; anything else -> `error`. |

Config: `maxTokensAsSuccess` (default `false`) -- "Report max-token turn/subagent termination as a successful SDK result" (`packages/sdk/server/README.md`).

## 3. Headless `--json` event stream and exit codes

Source: `packages/bundle/headless/README.md`.

Default (non-JSON) mode: reasoning deltas stream to stderr under a `dsh: reasoning:` heading; final answer prints to stdout; a failure prints `dsh: <code>: <message>` to stderr.

`--json` mode replaces the stdout final-text line with a newline-delimited JSON event stream. Stream shape:

- Opens with a `session` event carrying the session identity used for the run.
- Middle events: `status`, `text`, `thinking`, `tool_call`, `tool_result` -- `text`/`thinking` are projected from committed assistant messages (arrive per commit, not per token; a retried/discarded attempt never reaches the stream).
- Closes with a `final` event carrying the same lossless answer as default mode, not capped.
- Every other string/object key is capped at 8 KiB and flagged `truncated`; one full event line (incl. newline) is capped at 32 KiB -- an over-long event keeps scalars, drops structured fields, and at the extreme reduces to `{ type, truncated }`; payloads nested 64+ levels deep are cut at that depth.
- Empty tool-argument string projects as `{}`; JSON-non-round-trippable arguments (e.g. `1e400`) keep raw text instead of `null`.
- A runner failure outside a turn writes an `error` event and ends the stream with no `final` event (plus the `dsh:` stderr line). A profile whose own plugins fail to load exits before the runner mounts (only loader stderr diagnostics, no JSON event at all).
- A turn that fails in-turn still ends with a `final` event (often empty) and no `error` event -- so exit code + the `turn_end` reason, not stream shape alone, is the failure signal.
- Every usage error (including commander's own grammar rejections) also writes an `error` event to stdout in `--json` mode before exit.

Exit codes: 0 = completed final `turn/end`; 1 = any other outcome -- aborted, error, or no turn in the owned interval; also 1 for a direct driver failure (e.g. bad `--session-id`) or a whitespace-only/blank task.

Config fields (`packages/bundle/headless/README.md`): `task` (default: stdin), `sessionId` (default: `session-<uuid>`; an unknown id fails adoption), `json` (default `false`).

## 4. ACP: protocol version and capabilities

Source: `packages/acp/acp/README.md`.

- Protocol: standard ACP (agentclientprotocol.com) -- "Stable ACP v1 plus `session/list`, `session/resume`, `session/close`, and Streamable HTTP MCP support."
- `authenticate` always succeeds immediately; no authentication required.
- Config: `provider` (no default), `model` (no default) -- every session created by this server uses these; `sessionListPageSize` (default `100`).
- Capabilities table (verbatim from source):

| Call | What you get |
|---|---|
| `initialize` | ACP v1 + `session/list`, `session/resume`, `session/close`, Streamable HTTP MCP; image prompts only when attachment store + exact route support them |
| `session/new` | Fresh persistent agent; absolute workspace + stdio/HTTP MCP servers validated before publication |
| `session/list` | Deterministic newest-first pages of persisted, resumable root sessions; optional absolute `cwd` filter |
| `session/resume` | Persisted inactive session, canonical workspace re-verified; log restored without replaying old updates |
| `session/close` | Quiescent cancellation, update draining, descendant disposal, persistence flush |
| `session/set_config_option` | Serialized update to advertised `model`/`reasoning_effort` |
| `session/prompt` | One prompt in flight per session; text, resource links, supported images |
| `session/cancel` / `$/cancel_request` | Prompt-owned cancellation; unknown session ids are no-ops |
| `session/update` | Committed assistant messages/thoughts, generic tool lifecycle, config changes, context usage |
| `session/request_permission` | One-shot allow/reject permission prompt |

Unsupported / explicitly rejected: `session/load`, deletion, fork, additional directories, SSE or ACP-transport MCP, modes, commands, plans, terminals, client filesystem operations, elicitation (Cannot/does not detail in section 7).

## 5. SDK client entry points with minimal worked examples

### TypeScript SDK client (`@deepseek-ai/dsh-sdk-client`, `packages/sdk/client/README.md`)

Two layers: `DeepSeekHarness` (owned runs, high-level) over `HarnessClient` (protocol-level: `start()`, `initialize()`, `prompt()`, `request()`, `close()`, `subscribe()`).

```ts
import { DeepSeekHarness } from '@deepseek-ai/dsh-sdk-client'
import { ReasoningEffortId } from '@deepseek-ai/dsh-llm'

await using harness = new DeepSeekHarness({
  profile: 'sdk',
  patches: ['./automation.cordis.yml'],
  provider: 'deepseek-official',
  model: 'deepseek-v4-flash',
  reasoningEffort: ReasoningEffortId('max'),
  maxTokens: 49_152,
})
const result = await harness.run('say hi')
console.log(result.finalResponse)
```

`run()` returns `RunResult { sessionId, finalResponse, events, notifications }`; `finalResponse` is the last committed root-session assistant text in the run's owned interval, not necessarily attributable solely to that prompt. `close()` (or `await using`) is required to reap the child process.

### Python SDK (`deepseek-harness-sdk`, `python/sdk/README.md`)

No separate app entrypoint -- launches the bundled `dsh` CLI with `--profile sdk`. `DSH_HOME` (or `dsh_home`) is mandatory; the SDK never auto-discovers `~/.dsh`.

```py
from deepseek_harness import DeepSeekHarness

with DeepSeekHarness(
    dsh_home="/absolute/path/to/isolated-dsh-home",
    cwd="/absolute/path/to/workspace",
    provider="deepseek-official",
    model="deepseek-v4-flash",
    reasoning_effort="max",
    max_tokens=49_152,
) as harness:
    result = harness.run("Say hi.", session_id="example-001")

print(result.final_response)
```

`Session.run()` returns `RunResult(session_id, final_response, finish_reason, events, notifications)`. `finish_reason` is the `kind` of the last root-session `turn/end` (e.g. `completed`, `max-tokens`, `error`); a malformed `turn/end` raises `SdkProtocolError`.

## 6. Web API gateway route inventory

Source: `docs/api-gateway.md`.

The gateway is not a fixed URL list -- routes are generated per business-service method decorated `@Remote`/`@RemoteScope`, then dispatched through one fixed HTTP shape:

- All Remote calls go through `POST /api/<namespace>/<method>` with a JSON body `{ args: {...} }` (Client Remote call: `connection.rpc.call('/api', '<namespace>/<method>', { args }, signal)`).
- The Typert Gateway claims exactly two-segment endpoints under `/api` that have a strict descriptor or active SRC (source-execution) marker; unmatched requests return 404.
- Stream methods (`@Remote({ mode: 'stream' })`) multiplex over `/api/remote.mux` WebSocket (or an in-process carrier); Client-to-Host uplink data flows through the same logical stream via `this.ctx.invocation.uplink()`.
- Binary results (`Uint8Array` fields, nested or array) use a separate documented binary-transfer path, framed by Connection as multipart responses.
- A feature needing a response outside the RPC envelope registers an exact Connection Fetch route instead of a Remote method.
- Layer order: `remotes -> gateway -> connection -> webserver`. `packages/api` own remotes/gateway; `packages/client/connection` and `packages/host/webserver` own Connection/WebServer.
- `dsh-host-webserver` itself (`docs/subsystems/web-server.md`) exposes only: a named exact/prefix route table (one owner per `(kind, path)`), one fallback seat (claimed by the SPA static server in the shipped Web composition), and `webserver/index-inject` for structured head injection. It registers no `/api` routes itself -- that's the Connection/Gateway layer.

## 7. Cannot / does not

- SDK JSON-RPC server (`dsh-sdk-jsonrpc-server`): no per-session close or prompt-cancel method -- SDK-created agents remain live until process shutdown. No per-prompt result -- `messageId` is enqueue-only; correlating an assistant reply to a specific prompt is the caller's job. stdout purity is not enforced/inspected by the plugin itself -- a misconfigured sibling logger can corrupt the channel. Automatic adapter mounting only knows `deepseek-official`; any other unowned provider fails initialization (`packages/sdk/server/README.md`).
- TypeScript SDK client: no bundled-runtime resolution (must resolve same-version `@deepseek-ai/dsh` or a caller-provided `dshBin`). No mid-turn cancel -- abandoning a turn means closing the runtime. Client-to-server notifications and server-to-client requests are defined on the wire but unimplemented on both ends (`packages/sdk/client/README.md`).
- Headless: one task per invocation, no interactive follow-up. No pre-token heartbeat in default mode. `--session-id` adoption refuses a Session recorded under a different cwd, one with no recorded cwd, one that's a subagent/forked session, one under an unmounted preset, or one already live in-process (exclusive ownership). The `--json` stream is a bounded projection, not a lossless log copy (`packages/bundle/headless/README.md`).
- ACP: one primary workspace only -- no additional directories. Raster prompt images only (PNG/JPEG/WebP/GIF) and only with a durable attachment store + image-capable exact route. MCP tools only -- no MCP resources or prompts consumer. No transcript replay or interactive extensions: `session/load`, deletion, fork, modes, commands, plans, terminals, client filesystem operations, and elicitation are all explicitly out of scope (`packages/acp/acp/README.md`).
- Webhook runtime: no queue, retry, deduplication, execution-status tracking, crash replay, or Agent-status listener; it is fire-and-forget -- repeated deliveries can create repeated Sessions, and there is no completion result (`docs/subsystems/webhook.md`).
- Web HTTP server: no TLS, authentication, or Origin policy of its own -- a non-loopback bind (`0.0.0.0`) exposes the server unless the surrounding composition supplies those controls; the shipped `dsh web` command itself refuses `--host 0.0.0.0` (`docs/subsystems/web-server.md`).
- sdk-app / acp-app bundles: a custom profile can omit the SDK/ACP server row entirely, in which case client initialization simply fails -- nothing else answers. Configuration changes require a process restart; HMR is disabled in these bundles (`packages/bundle/sdk-app/README.md`, `packages/bundle/acp-app/README.md`).
- sdk-minimal: intentionally omits settings, managed credentials, telemetry, compaction, filesystem tools, workspace instructions, skills, jobs, and subagents; its shell policy is "danger-full-access" (any path reachable by the process), so it must run only against an isolated workspace (`packages/bundle/sdk-minimal/README.md`).

## Plexar notes

- Routing to a self-hosted vLLM/Qwen rig via llm-pi-ai: model/provider selection is entirely a per-`initialize` (SDK/headless/ACP-config) or per-`session/new`/`session/set_config_option` (ACP) parameter -- `provider` + `model` + optional `reasoningEffort`/`maxTokens`. The Python SDK README states directly: "A custom composition can mount `llm-pi-ai`, configure provider-specific credentials/endpoints there, and select any provider/model present in pi-ai's installed catalog" (`python/sdk/README.md`). The only automatic fallback the SDK server ever mounts unprompted is `deepseek-official`; any `llm-pi-ai`-routed provider must already be registered in the composed profile or `initialize` throws.
- Because provider/model selection happens at the request boundary, a self-hosted vLLM/Qwen route can be exposed as an ordinary named provider in the profile's Cordis composition -- Studio (or any SDK caller) just passes that provider id and model id in `initialize`/`session/new`, no protocol changes needed.
- `maxTokens` is a first-class, validated (`Number.isSafeInteger`, positive) per-request cap inherited by in-process descendants -- useful for bounding a self-hosted model with a smaller context window than the DeepSeek defaults.
- Embedding in Studio over stdio: SDK JSON-RPC (`dsh --profile sdk`) is the natural embed target -- it is process-owned, stdout-pure-by-contract, and has typed TS/Python clients with documented teardown ladders (stdin EOF -> SIGTERM -> SIGKILL). Studio should treat `close()`/`shutdown` as mandatory on every session lifecycle exit to avoid leaking subprocesses.
- ACP is the better fit if Studio wants standard, protocol-level session list/resume/close semantics across restarts, richer permission prompts, and MCP server mounting per session -- but note it exposes no DSH-specific presentation data (cards, plans, todos, terminal views): Studio would need to build its own UI layer entirely from the standard `session/update` stream.
- Neither SDK JSON-RPC nor ACP supports mid-turn cancellation on the wire -- Studio's stop-generation UX must be implemented as closing/restarting the runtime (SDK) or relying on ACP's prompt-scoped `session/cancel` (ACP only cancels the current prompt/autonomous work, not a lower-level model call already in flight).
- The SDK server notifies for every session in the runtime context, not just ones Studio created -- if Studio embeds via SDK JSON-RPC and expects isolation between concurrent users/tabs, it must implement its own session-tree scoping client-side (as both official SDKs already do, filtering on `subagent.started` lineage), not rely on the wire.
- `session.event`/`session.status`/`subagent.*` notifications carry zero authentication or per-connection scoping on the wire -- any embedding must treat the raw JSON-RPC stdio pipe itself as the trust boundary (single-tenant per subprocess), matching how both existing SDK clients already assume ownership of the whole subprocess.

## 8. CLI entry modes and profile composition

Source: `apps/cli/README.md`.

`dsh` is the sole supported Node application launcher; profiles are ordered stacks of plugin-bundle patch layers under the user's own overrides. SDK and ACP are profiles, not separate public bins.

| Command | Purpose |
|---|---|
| `dsh <name>` / `dsh --profile <name>` | Boot the named profile under `$DSH_HOME/profiles/<name>` |
| `dsh --profile <name> --from-default-profile <template>` | Create a new custom profile from a shipped template, then boot it |
| `dsh --profile acp` | Serve automation clients over ACP stdio until disconnect |
| `dsh --profile headless "job"` | Run one fresh persisted session, print the final answer, and exit |
| `dsh --profile sdk` | Serve SDK clients over JSON-RPC stdio until shutdown or disconnect |
| `dsh --profile sdk-minimal` | Serve SDK clients with the standalone minimal agent tree |
| `dsh web` | Boot the Web profile |
| `dsh plugin --profile <name> <pnpm args>` | Manage a profile's plugins by forwarding to pnpm in the profile directory |

The invoking directory is the default workspace root. The `web`, `headless`, `sdk`, `sdk-minimal`, and `acp` profiles auto-initialize on first use from shipped templates; the `desktop` name is reserved for the Electron-owned profile and the CLI rejects boot, config-dump, and plugin-management requests for it.

The launcher parses only its own flags and hands everything after them to the booted profile; the first unrecognized token starts the app's own arguments, e.g. `dsh --profile web --port 8080` (the `--port` belongs to the web app, not the launcher).

A profile directory holds `package.json` (out-of-tree plugin dependencies plus the profile manifest `dsh.profile` with its ordered `bundles` list) and `cordis.patch.yml` (the user's own patch layer). The composed tree layers, in order: each bundle's patch in `dsh.profile.bundles` order, then the profile's `cordis.patch.yml`, then `$DSH_HOME/cordis.patch.yml`, then `--patch` overlays. Bundle names resolve from the dsh installation first (`@deepseek-ai/dsh-base`, `@deepseek-ai/dsh-web-app`, `@deepseek-ai/dsh-headless`, `@deepseek-ai/dsh-sdk-app`, `@deepseek-ai/dsh-sdk-minimal`, `@deepseek-ai/dsh-acp-app`), then the profile's own `node_modules`. `dsh-hmr`, when enabled in YAML, watches the profile manifest and patch files and recomposes through one serialized reload; without HMR, changes apply on restart.

`--dump-default-config` and `--dump-config` inspect the composed tree without booting; `--dump-config-schema` prints JSON Schema for the composed tree's declared plugin config entries and patches.

## 9. Bundle apps backing each stdio surface

The SDK and ACP stdio surfaces are each a `dsh` profile bundle over `dsh-base`, differing only in which protocol server they mount and their default persona/route.

| Bundle | Mounts | Persona | Config highlight |
|---|---|---|---|
| `@deepseek-ai/dsh-sdk-app` (`packages/bundle/sdk-app/README.md`) | `dsh-sdk-jsonrpc-server`, started only after its zero-option command provider accepts the invocation | `You are a coding agent powered by the {{model}} model.` + `Your working directory is {{cwd}}.` suffix | `DSH_MAX_TOKENS_AS_SUCCESS` (unset or `true` reports token-limited completion as accepted; `false` reports it as an error); default file tools `read`/`write`/`edit` (no `str_replace_editor`) |
| `@deepseek-ai/dsh-acp-app` (`packages/bundle/acp-app/README.md`) | `dsh-acp`, started only after its zero-option command provider accepts the invocation | Same persona template as SDK | Shipped row creates sessions with `deepseek-official` and `deepseek-v4-flash`; a later patch can replace that row's complete config |

Both bundles: `dsh --profile <name> --help` writes help and exits without claiming stdin/stdout; stdin EOF binds to the launcher's bounded successful shutdown; stdout is reserved exclusively for newline-delimited protocol frames; session titles are disabled because neither protocol exposes a title surface (deterministic fallback titles are used instead); configuration changes require a process restart because both bundles disable HMR in YAML.

## 10. GitHub webhook adapter detail

`@deepseek-ai/dsh-webhook-github` (`docs/subsystems/webhook.md`) registers an exact route on an injected `WebServer`, resolves its credential reference per request, verifies the untouched `application/json` body before parsing, and returns `202` immediately after dispatching in-memory. Its normalized event guarantees a signed lossless-JSON object; individual rules validate the event-specific fields they consume. The documented deployment pattern mounts this route on an isolated second `WebServer` instance so exposing webhook ingress does not also expose the browser API surface on the same listener.

`WebhookSessionRequest` (the shape a rule's `run()` callback returns to trigger Session creation) requires an absolute `workspacePath`, title, text prompt, agent preset, and permission preset; an optional `model` field names an explicit provider/model route plus output-token cap, and omission snapshots the complete current deployment selection (including reasoning effort) until the first request records its durable header. The runtime resolves or creates the canonical Workspace, creates an Agent whose Session cwd equals the Workspace path, mounts the selected preset before publication, and durably attaches the Session before applying permission, title, and an initial follow-up message tagged `source.kind: "webhook"` carrying the provider, source, delivery, and rule identifiers.

## 11. Web HTTP server route mechanics

Source: `docs/subsystems/web-server.md`. `dsh-host-webserver` (`packages/host/webserver/src/index.ts`) is the browser HTTP carrier for the GUI host: a single `node:http` plugin providing `ctx.webServer`, a named-route registry, optional gzip response compression, index.html transform callbacks, and one fallback handler a plugin may claim. It knows no harness concepts and is not part of the agent loop; another plugin registers every feature route including the `/api` bridge.

Two route kinds: `exact` matches the pathname verbatim; `prefix` matches the path and `path/<anything>`. Match order is fixed: exact table first, then longest matching prefix, then the registered fallback. A duplicate `(kind, path)` registration throws. The shipped Web composition claims the fallback seat with `dsh-host-frontend-static`, the SPA dist server: non-GET/HEAD is 405, traversal outside the dist root is 403, absent or non-file targets are empty 404 responses, and unknown extensions ship as octet-stream.

Config: `host` accepts only `127.0.0.1` (default posture) or `0.0.0.0` (deliberate network exposure); `port` (0 requests an OS-assigned port); `compression` (`none` default, or `gzip`); `compressionLevel` (default 1); `compressionThresholdBytes` (default 1024). The carrier itself owns no TLS, authentication, or Origin policy — a non-loopback bind exposes the server unless the surrounding composition supplies those controls; the shipped `dsh web` command selects loopback and rejects `--host 0.0.0.0`, and its Connection plugin supplies Host/Origin checks plus browser-session authentication for every Host API route and stream.

Key `ctx.webServer` methods (`packages/host/webserver/src/index.ts`): `register(route)` adds one named route and returns its disposer; `registerUpgrade(route)` registers an exact-path HTTP upgrade route (one protocol owner per socket); `registerFallback(handler)` claims the single fallback seat; `tapIndex(transform)` registers a raw-HTML index transform (the escape hatch beyond structured injection rows); `applyIndexTaps(html)` runs registered taps in registration order; `collectIndexInjections()` gathers the structured `IndexInjection` table via one `webserver/index-inject` emit (fresh per call, so subscribers report live state); `renderIndex(html)` renders the structured table first, then raw taps.

`ctx.connection` (`packages/client/connection/src/rpc.ts`) supplies the transport-independent trust layer other routes can reuse: `createSharedFetchHandler(channel)` composes exact Fetch routes plus the shared-channel RPC interceptor; `requestRejection(request)` applies Connection's Host/Origin checks and browser authentication to another Web route; `admit(request)` admits one request against that same policy, returning the operator Peer or a rejection status; `authorizeIndex(request, response)` authenticates one frontend index request, owning a token redirect or 401; `authenticatedUrl(baseUrl)` appends the fresh process token to an ordinary Web application URL for initial login.

## 12. ACP admission, settlement, and teardown detail

Source: `packages/acp/acp/README.md`. Each ACP session permits one in-flight prompt. Admission validates the whole prompt batch, snapshots the selected provider/model/reasoning-effort route, rechecks the exact Agent identity and image capability, persists image attachments, and only then queues the user message — a cancellation that wins the admission race never enqueues a late turn. Once queued, the session pins that same route across every model step of the turn; a concurrent `session/set_config_option` change applies only to the next turn. Settlement precedence is explicit: cancellation, then committed-output failure, then interval-wide Agent failure, then the correlated turn ending.

Each session module owns its Agent handle, MCP mounts, future and turn-pinned model selections, prompt slot, update chain, and memoized close operation. Explicit `session/close`, client disconnect, and Cordis disposal all use the same quiescent teardown: stop new work, cancel prompt admission and Agent activity, drain committed updates, dispose continuable descendants child-first, flush persistence, release the owned Agent scope. A session close leaves persisted state available for `session/list` and `session/resume`; other sessions sharing the Context are untouched.

ACP clients are trusted controllers: stdio MCP entries authorize their absolute commands and environment; HTTP MCP entries authorize their absolute HTTP(S) URLs and headers; any initial connection or discovery failure rolls back the unpublished Agent before it is ever visible to `session/list`.

## 13. sdk-minimal environment and tool surface

Source: `packages/bundle/sdk-minimal/README.md`. `dsh --profile sdk-minimal` supplies a complete, standalone Cordis tree that deliberately excludes `dsh-base`: no Web, settings, managed credentials, telemetry, compaction, filesystem tools, workspace instructions, skills, jobs, or subagents. It mounts exactly one persistent shell stack — Bash on Linux/macOS, or PowerShell on Windows — with a 300-second timeout and one owner-scoped terminal; the other platform's rows stay disabled. Its danger-full-access shell policy lets the shell modify any path available to the process, so it is documented to be used only with an isolated workspace.

Environment variables: `DSH_HOME` (required — the SDK deliberately never discovers `~/.dsh`), `DSH_CONTEXT_WINDOW` (fallback context-window capacity for a model absent from the adapter's advisory catalog), `DSH_SYSTEM_PROMPT` (replaces the default persona `You are a helpful software engineer assistant.`), `DEEPSEEK_API_KEY` (model credential). The SDK initialization request's `model` field is the sole runtime model selection — it overrides environment defaults and works for model ids outside the adapter's advisory catalog. Sessions persist as uncompressed JSONL under `$DSH_HOME/sessions`. With no MCP server configured in the caller's scope, MCP contributes no prompt text or tools and the only advertised tool remains the one platform-selected shell.

## 14. Typert generation pipeline (how `/api` routes come to exist)

Source: `docs/api-gateway.md`. A business service marks methods `@Remote('name')` (calling a Cordis service on the root Host Context) or `@RemoteScope(key)` (resolving an identity to a scoped Context first). Complex Host objects — such as an `Agent` parameter — cross the wire only through a `TypertLookupMap` declaration plus a registered `ctx.typert.lookups` resolution provider; an `Agent` parameter named `agent` produces an `agentId` wire field that the Gateway resolves before invoking the method. Strict analysis requires a Remote to be a public, non-static, non-generic instance method with a concrete implementation; parameters must be required, named simple identifiers with no destructuring, defaults, or rest parameters. A final `signal: AbortSignal` parameter is recorded in the descriptor instead of entering `args`.

The root build runs `build:lib:host`, `build:lib:client`, `build:web` in order: the Host lib phase runs `tsc -b tsconfig.host.json` then a tsdown pass that also runs the Typert generator against the Host `ts.Program`; the Client lib phase then consumes the generated Remote Client declarations. Each contributing package writes `typert.host.js`/`.d.ts` (Host Loader) and `typert.remote-client.js`/`.d.ts` (mountable `TypertRemoteContribution` for `api-remotes`) to its own `lib/` directory. When the Host starts from source (`node --import tsx/esm`), a weaker SRC fallback parses simple parameter names from the live function without running a `ts.Program`; the Client Remote refuses to mount SRC descriptors lacking strict codecs, so its types and runtime codecs always come from the most recently generated build artifacts.

## 15. Headless implementation notes (run flow)

Source: `packages/bundle/headless/README.md`. The runner awaits the complete application (`ctx.get('loader')?.await()`) so composed tools/adapters are not half-mounted before the task starts, reads the shared `agentDefaultModel` selection, resolves the task from config or stdin, then resolves the Agent identity: a fresh `session-<uuid>` by default, or the persisted Session `--session-id` names, adopted through `sessionQuery`. It submits the task as an ordinary user message, waits for quiescence, flushes the Session, and folds the owned interval into the last non-empty `assistant/message` text and final `turn/end` reason. The patch rides over `dsh-base`: it sets the coding persona prefix and a separate cwd suffix on the base `system-prompt` row, disables the shared HMR row, and mounts the startup provider plus the runner. `dsh --profile headless --help` prints help and exits without running anything.

## 16. Webhook shared value types

Source: `docs/subsystems/webhook.md`. `WebhookRuleId`, `WebhookSourceId`, and `WebhookDeliveryId` are opaque strings; a delivery id records only the provider's own identifier — the runtime neither stores nor deduplicates it. `WebhookEventMap` is merge-extensible by provider kind, so an out-of-tree adapter can add a provider without changing the runtime package; `WebhookEventOf<K>` falls back to generic lossless JSON for an unknown provider kind. `VerifiedWebhookDelivery<K>` carries `kind`, configured `source`, provider `deliveryId`, normalized `event`, and a non-negative safe-integer `receivedAt`; the runtime validates, detaches, and freezes the whole value before dispatching it to more than one rule. `dispatch()` snapshots the matching rules, schedules each independently, and returns before any callback settles — throws and rejections are contained per rule, and registration disposal removes a rule before aborting and draining its active calls.
