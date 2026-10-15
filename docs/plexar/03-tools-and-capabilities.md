# 03 — Tools and Capabilities: what the agent can DO

Audience: Plexar framework team and Plexar Studio team. Scope: every model-facing tool DSH ships, the sandbox/approval system that gates them, MCP, Skills, Hooks, LSP, jobs/schedule/workflow/PTC, web/browser/computer use, and what plainly does not exist yet.

Everything below traces to a file under this repo. Generated catalogs (`docs/tool-catalog.md`, per-subsystem `Cordis API` sections) are verified fresh by `pnpm run doc-sync`, so tool names and schemas are exact as of the current tree.

## 1. Full tool table

Source: `docs/tool-catalog.md` (tool package map, lines 16-47) plus each package's `Cordis API`/README for sandbox and default-enablement facts.

| Tool name(s) | Package | What it does | Sandbox / approval class | Enabled by default in base? |
|---|---|---|---|---|
| `plugin_manager` | `@deepseek-ai/dsh-plugin-manager` | List/enable/disable plugins and bundles, install/remove bundles for the current profile | Requires `danger-full-access` or approval for every call | Yes (core management tool) |
| `list_mcp_resource_templates`, `list_mcp_resources`, `read_mcp_resource` | `@deepseek-ai/dsh-mcp-resources` | Discover/read MCP server resources | Ordinary tool pipeline; no filesystem effect | Yes when any MCP client is configured |
| `stagehand_act`, `stagehand_extract`, `stagehand_navigate`, `stagehand_observe`, `stagehand_screenshot`, `stagehand_tabs` | `@deepseek-ai/dsh-experimental-browser-use-stagehand-native` | Natural-language browser control via Stagehand | Experimental; opt-in provider registration | No, experimental, explicit activation |
| `ask_user_question` | `@deepseek-ai/dsh-tool-ask-user` | Ask the user a question and pause for the answer | Pauses on ctx.userQuestions; no sandbox effect | Yes |
| `run_code` | `@deepseek-ai/dsh-tools` | Execute a TypeScript program (PTC mode) against declared tool bindings | sandbox_permissions param can request workspace-write/danger-full-access, gated by approval | Yes under mode ptc/both |
| `exit_plan_mode` | `@deepseek-ai/dsh-plan-mode` | Present a plan and, on approval, leave plan mode | No sandbox effect; user-questions seam | Yes when plan mode composed |
| `bash` | `@deepseek-ai/dsh-tool-bash` | Execute a bash command in a fresh shell; run_in_background for jobs | Sandbox-confined per session mode; approval required to widen | Yes (POSIX default) |
| `present` | `@deepseek-ai/dsh-tool-present` | Declare existing files as final deliverables | No new sandbox effect (files must already exist) | Yes |
| `pwsh` | `@deepseek-ai/dsh-tool-pwsh` | Execute a PowerShell command in a fresh process; run_in_background for jobs | Same executor seam as bash, minus sandbox controls | Yes (Windows default) |
| `cordis_inspect_list`, `cordis_inspect_query` | `@deepseek-ai/dsh-tool-cordis` | Read-only runtime introspection (Creator mode) | Read-only; no mutation | No, Creator/extensions mode only |
| `bash` (persistent) | `@deepseek-ai/dsh-tool-bash-persistent` | Persistent PTY bash shell; state persists across calls | Terminal seam | No, composition choice |
| `pwsh` (persistent) | `@deepseek-ai/dsh-tool-pwsh-persistent` | Windows counterpart of persistent bash | Terminal seam | No, composition choice |
| `str_replace_editor` | `@deepseek-ai/dsh-tool-str-replace-editor` | Reference-tool-compatible view/create/str_replace/insert file editor | Filesystem seam; no read-before-write policy baked in | No, alternative to edit/read/write |
| `edit`, `read`, `read_image`, `write` | `@deepseek-ai/dsh-tool-fs` | Read/write/edit UTF-8 text files; read images | Filesystem seam; dsh-fs-observation-policy enforces read-before-write/edit when loaded | Yes |
| `glob`, `grep` | `@deepseek-ai/dsh-tool-fs-search` | Find files by glob; search contents via ripgrep | Foreground-only subprocess calls, never background jobs | Yes |
| `terminal_close`, `terminal_list`, `terminal_open`, `terminal_read`, `terminal_send`, `terminal_signal` | `@deepseek-ai/dsh-tool-terminal` | Create/manage persistent PTY terminal sessions | Opt-in; run_in_background sends register with ctx.jobs | No, opt-in |
| `create_goal`, `get_goal`, `update_goal` | `@deepseek-ai/dsh-tool-goal` | Create/track/update a persisted same-session completion goal | Requires direct-human root authority for create/edit/pause/resume | No, opt-in Goal plugin |
| `schedule_create`, `schedule_delete`, `schedule_list` | `@deepseek-ai/dsh-schedule` | Session-local reminders that return as later conversation turns | No sandbox effect; requires live root Agent scope | No, opt-in Schedule plugin |
| `lsp` | `@deepseek-ai/dsh-tool-lsp` | Query a language server: goToDefinition, findReferences, goToImplementation, hover | No sandbox effect; requires a registered provider or returns LSP_UNAVAILABLE | No, opt-in |
| `ralph` | `@deepseek-ai/dsh-tool-ralph` | Run a foreground fresh-agent Ralph loop toward one immutable objective | Fixed workflow; spawns fresh children each round | No, opt-in |
| `skill` | `@deepseek-ai/dsh-tool-skill` | Load full instructions for a named skill | No sandbox effect | Yes when dsh-skill composed |
| `session_event_read`, `session_event_search`, `session_event_trace`, `session_search`, `session_trace` | `@deepseek-ai/dsh-tool-session-query` | Read-only browsing/search/trace over session history | No sandbox effect; authorized from calling agent session | No, opt-in |
| `list_subagent_models`, `subagent` (aliases: subagent, subagent_fork) | `@deepseek-ai/dsh-tool-subagent` | Discover LLM routes for subagents; delegate a self-contained task to a subagent | run_in_background registers with ctx.jobs | Yes |
| `interrupt_agent`, `list_agents`, `send_message` | `@deepseek-ai/dsh-tool-subagent-control` | Control/steer continuable background subagents | No sandbox effect | Yes alongside dsh-tool-subagent |
| `job_kill`, `job_list`, `job_output` | `@deepseek-ai/dsh-tool-jobs` | List/read/kill any background job (bash, pwsh, terminal sends, subagents) | No sandbox effect; kind-agnostic controller | Yes when any background-capable tool is composed |
| `interrupt_agent`, `list_agents`, `send_message`, `spawn_teammate`, `team_task_create`, `team_task_get`, `team_task_list`, `team_task_update`, `wait_agent` | `@deepseek-ai/dsh-experimental-tool-agent-team` | Multi-agent Team coordination: durable teammates, shared task board | Scoped to implicit Team Leads and durable teammates | No, shipped dsh-base bundle keeps this package disabled; explicit opt-in profile patch required, and it disables the legacy subagent-control names when enabled |
| `todo_write` | `@deepseek-ai/dsh-tool-todo` | Write/replace the session's todo checklist | Session-owned state only | Yes |
| `workflow` | `@deepseek-ai/dsh-tool-workflow` | Run a model-written orchestration script that starts subagents (PTC-executed) | Runs under the calling Session's file policy via dsh-workflow-ptc | No, opt-in |
| `load_workspace_dependencies` | `@deepseek-ai/dsh-tool-workspace-dependencies` | Workspace dependency loading | No sandbox effect | No, opt-in |
| `web_fetch`, `web_search` | `@deepseek-ai/dsh-tool-web` | Fetch a URL / run a web search through a configured provider | Fetch exposed in every sandbox/approval mode without per-call confirmation by shipped presets | Yes when a provider is registered |

MCP-bridged tools are not in this table: each configured MCP server contributes tools named mcp__serverName__rawName at runtime (`packages/mcp/mcp-client/README.md`); see section 3.

## 2. Sandbox modes and approval

Source: `docs/subsystems/sandbox.md`, `docs/subsystems/approval.md`, `docs/subsystems/permission-presets.md`, `docs/subsystems/shell.md`.

### 2.1 Exact SandboxMode values

```
type SandboxMode = 'read-only' | 'workspace-write' | 'danger-full-access'
```

- read-only: backend denies writes. POSIX runners additionally grant the /dev/null sink shells require. The Windows ACL runner grants no explicit writable root and reports partial enforcement for ambient ACL gaps.
- workspace-write: writes permitted under the workspace root and the backend's promised temp area.
- danger-full-access: confinement bypassed entirely; the consumer spawns its original argv and never calls ctx.sandbox. Only read-only and workspace-write are ever sent to a sandbox provider.

Enforcement completeness is reported separately as 'full' | 'partial'. Older Landlock kernel ABIs and the Windows ACL runner's hard-link/unconfined-read/AppContainer-ACL boundaries are the documented partial cases.

### 2.2 Backends (Windows/pwsh vs POSIX)

Per `packages/sandbox/sandbox/src/index.ts` (via `docs/subsystems/sandbox.md`): dsh-sandbox-local supplies Linux bwrap/Landlock, macOS Seatbelt, and a Windows ACL restricted-token backend. Each backend has its own denial-signature dialect (EROFS under bwrap read-only binds, EACCES under Landlock, EPERM under Seatbelt); consumers match exactly the selected backend's denialSignatures, never a cross-backend union.

Critically: dsh-tool-pwsh mirrors dsh-tool-bash call-for-call minus sandbox controls (`docs/tool-catalog.md` line 26 and `docs/subsystems/shell.md`) — the PowerShell tool description does not document a sandbox-denial marker the way bash does, and the shell seam doc states pwsh "mirrors the bash tool call-for-call minus sandbox controls." Each pwsh/persistent-pwsh call runs in a fresh process (no persistent PTY for the one-shot tool), with native C:\ paths and $env:NAME variables, versus bash's POSIX paths and bash -c semantics. dsh-bash-sandbox and dsh-pwsh-sandbox both consume the dsh-sandbox seam per the sandbox subsystem's package map, but the model-facing pwsh tool description omits the "[sandbox: file access denied under MODE mode]" marker language that bash's tool description carries — confirm sandbox parity for pwsh against the exact deployment composition before relying on it.

### 2.3 Widening mid-call

The bash tool description states: commands may run under a file sandbox; a blocked file operation is reported as "[sandbox: file access denied under MODE mode]". A model can request a wider one-shot retry via run_code's sandbox_permissions (workspace-write | danger-full-access) plus justification; ctx.approval must grant that exact call before it executes (`docs/subsystems/shell.md`).

### 2.4 Approval

Source: `docs/subsystems/approval.md`.

- ApprovalOutcome = allowed-once | rejected | cancelled | unavailable — fail-closed: only allowed-once grants; every other value (including a missing/throwing/non-conforming answerer) denies.
- ApprovalPolicy = ask | never — ask delegates to composed answerers (falling through to unavailable with none composed); never deterministically rejects every ask without dispatching any answerer, enforced inside the service before waterfall dispatch (a later-registered answerer cannot bypass it).
- Approval requests deliberately omit tool arguments — they reference an already-streamed callId instead, so a UI never renders a second, possibly drifted copy of the call.

### 2.5 Permission presets

Source: `docs/subsystems/permission-presets.md`.

ctx.permissionPresets bundles sandbox/mode + approval/policy into named presets a client offers as one selector. Default configured table:

| Preset | Sandbox | Approval |
|---|---|---|
| workspace-write | workspace-write | ask |
| danger-full-access | danger-full-access | never |
| custom (reserved, derived-only) | - | - |
| auto (reserved for the Auto review integration) | danger-full-access | never |

## 3. MCP

Source: `docs/subsystems/mcp.md`, `packages/mcp/mcp-client/README.md`.

### 3.1 Server config shape

One @deepseek-ai/dsh-mcp-client plugin entry per server:

```yaml
- id: mcp-github
  name: '@deepseek-ai/dsh-mcp-client'
  config:
    serverName: github
    transport: stdio
    command: npx
    args: ['-y', '@modelcontextprotocol/server-github']
    env:
      GITHUB_TOKEN: !!js process.env.GITHUB_TOKEN

- id: mcp-web
  name: '@deepseek-ai/dsh-mcp-client'
  config:
    serverName: web
    transport: streamable-http
    url: http://localhost:3000/mcp
    headers:
      Authorization: !!js Bearer token expression
```

Accepted fields (`packages/mcp/mcp-client/README.md`): transport (required, stdio or streamable-http), serverName (required, [A-Za-z0-9_-]{1,32}, unique per scope), command/args/env/cwd (stdio), url/headers (streamable-http), toolCallTimeoutMs (default 60,000), maxInstructionBytes (default 32,768), failOnStartupError (default false), reconnect.enabled (default true), reconnect.initialDelayMs (default 500, doubling), reconnect.maxDelayMs (default 30,000), reconnect.maxAttempts (default 10).

### 3.2 stdio vs http

- stdio: spawns a local process; a temporary probe process negotiates before the serving process starts; child env starts from scrubbedParentEnv() (drops names matching KEY|PASSWORD|SECRET|TOKEN and ambient DSH_ names) then merges configured env on top.
- streamable-http: connects to a service URL with optional headers; reconnect ownership is explicitly called out as an open design question (the SDK owns per-request retry).

Tool names are server-qualified and stable: mcp__serverName__rawName (identical shape to Claude Code/Codex). No server is enabled by default; an empty caller scope adds no MCP tools or prompt text.

### 3.3 Resources

dsh-mcp-resources supplies three shared tools (list_mcp_resource_templates, list_mcp_resources, read_mcp_resource) once per composition, regardless of how many MCP clients are configured — these are not per-server tools. Resource providers are connection-owned; the first provider in a scope enables the shared tools, and removing the last removes them. MCP resource subscriptions and prompt templates are unsupported.

## 4. Skills

Source: `docs/subsystems/skills.md`, `packages/skill/skill/README.md`.

### 4.1 Format

- Directory bundle: name/SKILL.md
- Flat file: name.md
- Names are kebab-case: matching ^[a-z0-9]+(-[a-z0-9]+)*$
- Nested recursive SKILL.md discovery is not supported.
- Frontmatter keys read exactly: disable-model-invocation, user-invocable (both default true when omitted, i.e. a skill is model- and user-invocable by default).

### 4.2 Discovery roots (rank order, lower wins ties within a layer)

| Rank | Source | Root |
|---|---|---|
| 100 | project-dsh | projectRoot/.dsh/skills |
| 200 | project-agents | projectRoot/.agents/skills |
| 300 | custom | Config.customSkillDirs |
| 400 | user-dsh | dshHome/skills |
| 500 | user-agents | agentsHome/skills |
| 600 | bundled | Config.bundledSkillDir when configured |

Project root = nearest ancestor containing .git, else the cwd. The registry is host+per-scope layered (same shape as the tools registry): the nearest layer wins a duplicate name outright; rank only decides duplicates within one layer.

### 4.3 SKILL.md / model-facing catalog compatibility

- The model session catalog is injected as a durable user-role system-reminder at the first agent/pre-step, listing only name and normalized/XML-escaped description (never body, path, source, or provider).
- The skill tool validates the kebab-case name, checks isModelInvocable, rereads the full definition for the calling agent's cwd, and returns skill_content, skill_resources, skill_instructions blocks.
- An invocation policy on every skill independently gates model vs. user surfaces (modelInvocable/userInvocable — all four combinations preserved).

## 5. Hooks

Source: `packages/hooks/hook-protocol/README.md`, `packages/hooks/hooks-claude-code/README.md`, `packages/hooks/hooks-codex/README.md`.

### 5.1 Shared protocol (dsh-hook-protocol)

Only command hooks ({ type: command, command, timeout }) run; http, mcp_tool, prompt, and agent handlers are parsed and skipped with a warning. A hook can:

- Block with exit code 2 (stderr becomes the model-visible reason).
- Ask for confirmation (Claude Code bridge only; Codex bridge has no ask/allow — only deny).
- Attach context returned as extra text the model sees next turn.
- Request run stop ({"continue": false}) — recorded but has no run-level effect (folded into MergedHookOutcome.stop but no hard-halt primitive exists yet).
- Fail non-blockingly — any exit code other than 2 (including an unstartable command) is logged, non-blocking.

Merge precedence across matched hooks: deny greater than ask greater than allow, most-restrictive wins, continue:false is sticky first-wins, context accumulates in hook order.

### 5.2 Claude Code bridge event to extension point mapping

| Claude Code hook | Harness extension point | What it can do |
|---|---|---|
| SessionStart | agent/created (awaited init) | attach context |
| UserPromptSubmit | agent/pre-step waterfall | block prompt, attach context |
| PreToolUse | tools/pre-execute waterfall | block (deny) or ask |
| PostToolUse | tools/post-execute waterfall | block with feedback, attach context |
| Stop | agent/turn-stopping serial listener | force another step (steer()) |
| SubagentStart | subagent/start emit | attach context to a live in-process child only |
| SubagentStop | subagent/end emit | observe only, cannot block or add context |

Only 7 of Claude Code's 30 current hook events are supported; the other 23 (Setup, InstructionsLoaded, UserPromptExpansion, MessageDisplay, PermissionRequest, PostToolUseFailure, PostToolBatch, PermissionDenied, Notification, TaskCreated, TaskCompleted, StopFailure, TeammateIdle, ConfigChange, CwdChanged, FileChanged, WorktreeCreate, WorktreeRemove, PreCompact, PostCompact, SessionEnd, Elicitation, ElicitationResult) are dropped before group parsing.

### 5.3 Codex bridge

5 supported events: SessionStart, UserPromptSubmit, PreToolUse (block-only, no allow/ask), PostToolUse, Stop. 5 of Codex's 10 current events are unsupported: PermissionRequest, PreCompact, PostCompact, SubagentStart, SubagentStop. Only synchronous command hooks run; async:true or non-command hooks are skipped with a warning. Codex matchers are always unanchored regexes (vs. Claude Code's literal-or-regex mode).

### 5.4 Both bridges share

- Config read once at process startup from a configPath; no live reload.
- Hooks run serially in config order (reference tools run concurrently — a documented divergence, order-independent-by-fold so outcome parity holds).
- transcript_path is always empty/null — the persistence seam exposes no artifact paths and the default Zstandard-compressed session log is not hook-readable.
- updatedInput/updatedToolOutput rewrite is parsed but never honored.

## 6. Experimental capabilities and their status

| Capability | Package(s) | Status per upstream |
|---|---|---|
| Browser use | dsh-browser-use + experimental-browser-use-{playwright-mcp, chrome-devtools-mcp, stagehand-native} | Experimental public npm packages, require explicit activation. Shared service registers only a provider name (no common operation methods); one provider slot only, second registration always fails. |
| Computer use | dsh-computer-use + experimental-computer-use-cua-driver-{mcp,native} | Experimental, explicit activation; single-provider-slot design identical to browser use. |
| Agent Team | dsh-experimental-agent-team, dsh-experimental-tool-agent-team, dsh-experimental-client-ui-agent-team | Disabled in the shipped dsh-base bundle. A documented Agent Teams profile patch enables the 9-tool team surface while disabling the legacy subagent-control tool names (interrupt_agent/list_agents/send_message move ownership). |
| Office to PDF | `packages/document/office-to-pdf` | Not model-facing at all — creates no model-facing tool or Session event. Host-only LibreOffice-kit conversion consumed by preview UI / Remote render(). |
| run_code / PTC mode | dsh-tools, dsh-ptc-runtime, dsh-ptc-runtime-node, dsh-experimental-ptc-runtime-python | Node PTC runtime is the shipped provider; Python PTC runtime is explicitly under packages/experimental/. |

## 7. Cannot / does not

Collected "does not / unsupported" statements traced to source, by area:

Sandbox
- No timeout exists (or can exist) on file IO (read/write/edit): a local syscall is best-effort-abortable at most, so no timeoutMs param is offered there (unlike bash, web_fetch, and subprocess-backed glob/grep).
- Sandbox modes govern file effects only — network and process visibility are explicitly outside this vocabulary.

MCP
- No prompt templates, no human-input elicitation, no task-based execution extension, no resource subscriptions.
- A tool requiring the task-based execution extension throws at call time rather than bridging.
- No product setting forces a specific protocol revision; negotiation follows the SDK's supported set only.

Skills
- No recursive SKILL.md discovery.
- Registry has no TTL; invalidation is entirely provider-driven (a provider must call its own invalidate()).
- Duplicate resolution is first-wins with no API to inspect shadowed definitions.

Hooks
- No run-level halt: continue:false is recorded but never stops the run.
- Only command-type hooks execute; http/mcp_tool/prompt/agent handler types are always skipped.
- updatedInput/updatedToolOutput/updatedMCPToolOutput are parsed, logged, warned — never applied.
- transcript_path is always empty (Claude Code bridge) or null (Codex bridge) — hook scripts cannot read the session transcript.
- No per-session hook-config discovery, no live config reload, no stop-loop guard.

LSP
- Exactly four operations only (goToDefinition, findReferences, goToImplementation, hover) — a closed union; no symbols query, no call hierarchy.
- No provider registered results in an LSP_UNAVAILABLE structured error, not a schema change.

Jobs
- JobRegistry.start refuses work when no attached controller serves the spec's owner — a producer cannot start work its owner cannot collect or stop.
- Ring retention is bounded; reads below the retained window return lossy:true, never an error, and never recover the dropped bytes (a spill file, when kept, is the only recovery path).

Schedule
- Session-local delivery only — no external notification channel or cold-session scheduler; a reminder only fires while the original session is live.
- No calendar/Cron expression support; every_seconds is fixed-rate only, minimum 300 seconds.
- Best-effort at-least-once, not exactly-once, delivery (a narrow crash window after admission but before durable dispatch can repeat a reminder).

Workflow
- One engine implementation per context — no named-provider registry; a second engine replaces rather than coexists with the first.
- The PTC engine has no overall elapsed deadline — cancellation is immediate abort, not a graceful timeout.

PTC runtime
- Binding arguments/resolutions must be lossless JSON; a non-cloneable value is a descriptive error, not silent corruption.
- No seam-level byte cap on a single binding resolution — providers own their own transport caps.

Web
- Fetch is limited to two normalized body kinds (html, text) — a closed union; no PDF/binary extraction at this seam.
- SSRF protections (public-address pinning, per-redirect re-validation) prevent reaching non-public destinations, but explicitly do not stop a model from sending data to a public URL.
- File sandbox presets do not govern web network access — web_fetch is exposed in every sandbox/approval mode without per-call confirmation by shipped presets; a deployment needing gated fetch must add its own tools/pre-execute policy.

Attachments / images
- MCP: only PNG/JPEG/WebP/GIF images project durably; audio and embedded resources stay execution-local with diagnostic text only, never entering model context.
- Local backend: max 20 images / 200 MiB per message, 20 MiB / 64M pixels / 8192px per source image, before independent normalization (2048px long edge, 4 MiB default cap).

## Plexar notes

- Routing to self-hosted vLLM/Qwen via llm-pi-ai. `docs/capability-seams.md` shows pkg_llm_pi_ai feeding svc_llm alongside pkg_llm_deepseek and pkg_llm_replay — ctx.llm is a swappable adapter registry, and tool schemas (this whole document) are provider-independent: none of the tool definitions above change when the backing model swaps to a self-hosted Qwen route through llm-pi-ai. Tool availability is a composition/config question, not a model-routing question.
- run_code (PTC mode) is the highest-leverage integration point for a Plexar/vLLM rig, since sub-tool calls inside a PTC program re-enter the full guarded pipeline (approval, sandbox, jobs) with the same per-call enforcement as top-level tool calls — a self-hosted route gains no weaker guarantees by being called from inside a PTC script.
- Sandbox parity gap on Windows/pwsh is a real integration risk for a Studio embedding that expects uniform sandbox-denial behavior across bash and pwsh — verify the exact deployment's pwsh sandbox enforcement before promising sandboxed command execution to Studio users on Windows.
- Embedding in Studio over stdio should use the MCP client (dsh-mcp-client, stdio transport), not a bespoke bridge — it gets tool naming stability (mcp__serverName__rawName), reconnect/backoff, and the shared resource-tools/prompt-instructions machinery for free, at the cost of the documented limits in section 3 (no prompt templates, no resource subscriptions, 60s SDK-owned discovery timeout with no separate DSH-level timeout knob).
- Hooks are a compatibility shim, not a Studio integration surface. Both bridges are explicitly a compatibility adapter, not a power tool for reusing existing Claude Code/Codex hooks.json; a native Cordis plugin on the same extension points (agent/pre-step, tools/pre-execute, tools/post-execute, agent/turn-stopping) gives Studio the full harness API with none of the bridges' partial-support gaps (section 5.4).
- Agent Team and browser/computer use are pre-GA and off by default — any Studio feature depending on multi-agent coordination or desktop/browser control needs an explicit profile patch (Agent Team disables the legacy interrupt_agent/list_agents/send_message ownership when enabled) and should be treated as unstable in customer-facing flows.
- Skills are the natural place to encode Plexar/Studio-specific playbooks (how to call the self-hosted rig, how to format a Studio deliverable) without touching harness code — project-dsh/project-agents roots (.dsh/skills, .agents/skills) rank above user/bundled roots, so per-repo skills reliably win.
- Schedule's session-local-only delivery means a Studio reminder feature cannot rely on it for anything that must fire while the user's session is closed — it needs an external scheduler layered on top, not this subsystem.
- web_fetch's no-sandbox-gating default is worth flagging to Studio product: unlike file writes, outbound network calls to public URLs are not covered by sandbox/approval presets at all, so any "do not let the agent exfiltrate data" requirement needs a custom tools/pre-execute listener.
