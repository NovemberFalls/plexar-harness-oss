# The Agent Kernel

Audience: the Plexar framework team and the Plexar Studio team. Neither has seen this codebase (a fork of deepseek-ai/dsh, "dsh") before. This digest covers the agent kernel -- the spine that runs one turn of an agent from queued prompt to committed session history. It is derived entirely from the files named in the owning card; every claim traces to one of them.

Primary sources read: `docs/architecture.md`, `docs/agent-lifecycle.md`, `docs/tool-execution-pipeline.md`, `docs/event-producer-consumer.md`, `docs/subsystems/core.md`, `docs/subsystems/session.md`, `docs/subsystems/system-prompt.md`, `docs/subsystems/tools.md`, `docs/subsystems/scope.md`, `docs/subsystems/llm-streaming.md`, `docs/subsystems/compaction.md`, `docs/subsystems/subagent.md`, `docs/subsystems/goal.md`, `docs/subsystems/plan.md`, `docs/subsystems/conversation.md`, `docs/subsystems/user-questions.md`, `packages/core/agent-loop/README.md`, `packages/subagent/subagent/README.md`, `packages/llm/llm-pi-ai/README.md`, `docs/cordis-primer.md`.

## 1. Turn/step model -- the exact event order

A step is one model request plus the tools it calls. A turn is zero or more steps: it opens before its first input is claimed and closes once nothing is owed (`docs/architecture.md`). The canonical sequence, verbatim in shape from `docs/architecture.md` ("Turn flow"):

```
turn/start
  claim next-step input plus one queued message
  assemble prompt sections + tool schemas; project runtime context
  -> agent/pre-step                   reject | enter(messages, startsRequestSeries?)
     reject, or a first enter rewritten empty -> close the turn with no step
     step/start
     agent/request -> prepareCall (cancellation commits neither system nor users)
     reconcile system/message using the prepared call capability
     append entered messages as user/message; log request/header and request/context as needed
     derive and freeze model history from the log
     stream the bound prepared call -> llm/stream -> agent/assistant-stream start
       agent/assistant-stream chunk*
       assistant/message | assistant/attempt -> agent/assistant-stream end
     tool/call* -> tools/pre-execute -> tools/execute -> tools/post-execute -> tool/result*
     step/end
     tools owe another request, or next-step input arrived -> claim -> next step
  -> agent/turn-stopping
turn/end
```

turn/*, step/*, system/message, user/message, assistant/message, assistant/attempt, and tool/* are durable session events; everything else is a live extension point. agent/pre-step, agent/request, llm/stream, and the three tools/* events are waterfalls -- listeners must call next() to delegate; agent/turn-stopping is serial and has no next() (docs/architecture.md).

The equivalent sequence diagram in docs/agent-lifecycle.md names the same phases with the participants User, Agent, Driver, Hooks, Prompt (ctx.systemPrompt), LLM (ctx.llm), Tools (ctx.tools), Session, SDK. Key facts it adds:

- assistant/message records every successful provider call, including content-less and max-tokens finishes, and embeds the exact compact timed stream. A failed/retried/cancelled/stream-error attempt that reaches settlement without a surface message records as assistant/attempt instead. Live agent/assistant-stream chunk frames are transient; a hard process loss before settlement leaves no durable attempt stream.
- dsh-compaction-basic hooks agent/pre-step for pressure and agent/request-error for canonical context overflow; recovery runs within the open step and retries only when pruning/summarization advances the surface replacement generation.
- The returned agent/pre-step decision is authoritative; wrapping listeners must preserve downstream messages and startsRequestSeries unless replacement is intentional.
- "SDK users that need replayable transcript data should consume session/event; agent/* is the live coordination API for queue/status, prompt interception, request construction, steering, continuation, and errors" (docs/agent-lifecycle.md).

## 2. Durable SessionEvent kinds vs live agent/* events vs capability seams

| Layer | What it is | Examples | Consumed for |
|---|---|---|---|
| Durable SessionEvent (SessionEventMap) | Append-only, replayable log; model history is derived from it | turn/start, turn/end, step/start, step/end, user/message, developer/message, system/message, assistant/message, assistant/attempt, tool/call, tool/result, request/header, request/context, session/end-seed (core, 13 variants) plus plugin-merged log-only events (compaction/start, compaction/summary, compaction/end, goal/change, plan/mode, subagent/descriptor, subagent/catalog, hook/invoked, hook/result, image/offload, ...) | Replay, fork, resume, persistence, transcript reconstruction |
| Live agent/* events (Cordis-dispatched, process-local) | Coordination/interception API on the live Agent; not directly durable | agent/pre-step (waterfall), agent/request (waterfall), agent/request-error (waterfall), agent/turn-stopping (serial), agent/status, agent/assistant-stream, agent/inbox/*, agent/created (serial), agent/disposed, agent/error | Queue/status, prompt interception, request construction, steering, continuation, error recovery |
| Capability seams (ctx.<service>) | Swappable services with Service Definition / Provider / Consumer roles | ctx.llm (LLM adapters), ctx.tools (tool registry + pipeline), ctx.systemPrompt (prompt assembly), ctx.compaction, ctx.subagents, ctx.goals, ctx.planMode, ctx.userQuestions, ctx.sessions | Where new behavior plugs in without touching the loop |

Source: docs/subsystems/session.md (SessionEventMap), docs/event-producer-consumer.md (producer/listener matrix for every declared event, generated from the TypeScript program), docs/architecture.md ("Capability seams": "a seam is a swappable capability with three roles: a Service Definition declaring the interface, a Service Provider implementing it, and a Consumer using it").

A capability seam is complete only with all three roles present; one role alone is not a seam (docs/architecture.md, "Capability seams" section). Compaction, subagents, tools, and bash are documented seam examples.

Rule that ties layers together: "Model-visible means logged." Anything reaching a model request must be reconstructable from the session log; a new model-visible input requires a session event (docs/architecture.md).

## 3. Tool execution pipeline

Pipeline order, from docs/tool-execution-pipeline.md:

```
model tool-call block
  -> Session event: tool/call (logged before execution)
  -> tools/pre-execute waterfall (hooks, permission, sandbox)   -> allow | deny | ask | cancel
       ask -> ctx.approval one-shot prompt (absent/unanswerable -> deny)
  -> registered monotonic guards (deny-only; identity protected)
  -> tools/execute waterfall (around-dispatch: timeout, retry, metrics)
  -> registered tool execute() body
       (tool-fs mutations only) fs/write-intent | fs/edit-intent waterfall
       tool-owned session events: todo/write, fs/observed, hook/invoked, hook/result, tool/ptc-dispatch
  -> ToolDefinition.projectContent (execution-prepared content before post-execute)
  -> tools/post-execute waterfall (accept, block, replace, add context)
  -> registry outer normalization (pipeline/result snapshot throws become isError)
  -> ToolDefinition.finalizeContent (last content-only invariant; synchronous, must not throw)
  -> tools/result synchronous notification (frozen, authoritative outcome)
  -> Session event: tool/result (single model-facing outcome)
  -> presentResult(args, result) UI card
```

Decision types (from docs/subsystems/tools.md):

- PreToolDecision = { kind: 'allow' } | { kind: 'deny'; reason; info? } | { kind: 'cancel' } | { kind: 'ask'; reason? }
- PostToolDecision = { kind: 'accept'; content?/value?; additionalContexts? } | { kind: 'block'; feedback; additionalContexts? }
- ToolGuard = (execution) => string | undefined -- a monotonic guard run after every tools/pre-execute listener and before the body; it can only deny (returning a reason) or abstain (undefined); it can never re-allow a call another guard denied.

Approval flow: ask runs only after ctx.approval returns allowed-once; a missing approval channel/service or an agent-less request becomes a denial. Content replacement in post-execute is presentation policy, not confidentiality policy -- a listener that must hide the programmatic value blocks or replaces it instead. tools/result observers cannot transform the frozen outcome; observer failures are contained. Unknown and throwing tools both become structured errors (ToolNotFoundError -> UNKNOWN_TOOL), so a bad call fails without ending the turn (docs/subsystems/tools.md).

Execution scheduling: ctx.tools.executionMode(exec) classifies each pending call as { kind: 'parallel' } or { kind: 'exclusive' } via the tool's own isConcurrencySafe(args) -- only an exact true opts into parallel; any other outcome (including a throw) is exclusive. dsh-agent-loop forms exclusive barriers and a bounded rolling parallel pool from this classification, capped by config maxParallelToolCalls (default 10) (packages/core/agent-loop/README.md).

PTC (program-tool-calling / run_code) mode: sub-calls carry the parent's opaque token, log tool/ptc-dispatch, return denials as binding rejections, and omit additionalContexts to preserve call/result adjacency; under mode: 'ptc' only calls with a parent token may execute a native tool name -- a model-direct call is denied as UNKNOWN_TOOL before the policy pipeline (docs/subsystems/tools.md).

## 4. System prompt assembly

Assembly runs a cooperative waterfall over four contribution kinds registered on ctx.systemPrompt (docs/subsystems/system-prompt.md):

| Contribution | Registered via | Notes |
|---|---|---|
| PromptSection | ctx.systemPrompt.section(section) | { name, order, text: string or (context) => string, interpolate?, complete? }. Sorts ascending by order, then code-unit name. text may reference {{variable}}s interpolated by renderPrompt unless interpolate: false. complete: true marks the section as the whole prompt -- assembly still runs the waterfall (so tools/contexts/variables resolve) but then restores this section as the sole result; more than one effective complete section fails assembly. |
| PromptContext (dynamic) | ctx.systemPrompt.context(context) | Cache-safe counterpart, materialized as a durable user-role snapshot rather than prompt text, logged only when changed or when compaction removed it. |
| Tool-schema provider | ctx.systemPrompt.tools(provider) | Returns ToolProviderResult { schemas, knownNames? } -- the model-visible tool set for the current assembly. |
| Prompt variable | ctx.systemPrompt.variable(name, provider) | Name must match [a-z][a-z0-9_]*; referenced via {{name}} in section text. |

Assembly call: ctx.systemPrompt.assemble(context: AssembleContext = {}) -- merge-extensible AssembleContext carries scope?: ScopeKey (which registrations participate) and signal?: AbortSignal. dsh-agent extends it with a live agent field, and assembleContextFor(agent, signal) sets both together.

{{model}}/{{cwd}} templating: PromptSection.text supports {{variable}} interpolation resolved at assembly time. The agent-loop README states the loop "supplies provider, model, and cwd variable values but no additional fixed prose" as part of what the model sees for every step (packages/core/agent-loop/README.md, Model Experience section). Rendering happens through renderPrompt, and the committed text becomes a system/message surface node -- appended as surface node 0 on the first step, then either replaced in place or (on an in-history route in a continuing series) appended after cached history (docs/subsystems/system-prompt.md; docs/subsystems/session.md).

personaPrefix/personaSuffix: the package exports PERSONA_PREFIX_SECTION (name deployment:persona-prefix, order name DEPLOYMENT_PERSONA_PREFIX) and PERSONA_SUFFIX_SECTION (name deployment:persona-suffix, order name DEPLOYMENT_PERSONA_SUFFIX) -- the slots shared by global deployment configuration and scoped (e.g. per-subagent) contributions. docs/subsystems/core.md confirms: "An agent-scoped deployment:persona-prefix prompt section may shadow the global default persona"; subagents may register a scoped persona that "SHADOWS the deployment's persona for this child alone -- same template semantics as the deployment persona (strict {{...}} interpolation against the registered variables)" (docs/subsystems/subagent.md).

The system-prompt/assemble waterfall is scope-filtered: scoped listeners see only their own scope's assemblies. A registered complete section is restored after the waterfall runs, so listeners cannot add to or replace that scope's final prompt (docs/subsystems/system-prompt.md).

## 5. LLM adapter seam -- llm-pi-ai

ctx.llm (LlmRuntime, package dsh-llm) is the provider-neutral adapter registry and streaming API (docs/subsystems/llm-streaming.md). @deepseek-ai/dsh-llm-pi-ai (packages/llm/llm-pi-ai/README.md) is the multi-provider adapter built on the pi-ai library.

API kinds / compat fields (from the llm-pi-ai README config table and prose):

- api config field selects wire protocol for a hand-declared route: observed values include openai-completions, openai-responses, anthropic-messages.
- compat config object: "Wire-compatibility switches for unrecognized endpoints" -- which role carries the system prompt, which field caps output, how a thinking level travels, configurable per route and per model. Named sub-fields seen: compat.thinkingFormat (e.g. deepseek), thinkingTokenBudgetField (self-hosted Chat Completions reasoning-budget parameter, with template arg $var: thinking.budget), vllmPriority (integer scheduler priority when the server enables priority scheduling), supportsMaxOutputTokens: false (for openai-responses gateways, to omit max_output_tokens; ignored by Azure/Codex transports).
- Other route fields: apiKeyEnv (credential reference resolved per request through the harness credential seam; omission defers to pi-ai ambient discovery), displayName, baseURL, models (replaces the route's catalog wholesale), modelOverrides (reshapes individual installed-catalog models without replacing the rest -- refused if set beside models, on a hand-declared route, or naming an undescribed model), defaultContextWindow (default 262,144), defaultMaxTokens (default 32,768).

Reasoning efforts: reasoningEfforts declares a model's selectable thinking levels -- each key is a level selectors offer, its value the wire spelling dispatch sends (e.g. max: ultra renames a level for a gateway with its own vocabulary). Omitting the field keeps the installed catalog entry's capability; false declares a non-reasoning model. Example from the README:

reasoningEfforts:
  off:
  high: high

The core reasoning-id type is ReasoningEffortId = Branded<'ReasoningEffortId'>; each adapter owns the ordered set, display names, and optional deployment default via LlmModelReasoningInfo { efforts, defaultEffort? } (docs/subsystems/llm-streaming.md).

retryPolicy: per-profile field; omission uses "normal mode with five retries." Example:

retryPolicy:
  mode: normal
  maxRetries: 3

The core type ResolvedRetryPolicy (docs/subsystems/llm-streaming.md) resolves to an immutable discriminated union: mode: 'normal' carries finite maxRetries, retryableCodes, required initialDelayMs/maxDelayMs/jitterRatio; mode: 'always' carries the same backoff fields with no finite maximum. Retry is provider-owned, executed by the sibling package dsh-llm-retry, not an SDK retry -- "pi-ai SDK retries stay disabled so durable agent steps and llm/retry events own every visible attempt, and direct ctx.llm.stream() calls remain single-attempt" (packages/llm/llm-pi-ai/README.md, Known Limitations).

Image budgets (per-route fields, llm-pi-ai config table):

| Field | Default | Meaning |
|---|---|---|
| requestImagePixelBudget | 4,194,304 (2048x2048) | Total-pixel budget for each deterministic request image |
| requestImageMaxBytes | 1 MiB | Encoded-byte target per request image before base64 expansion |
| maxRequestImageBytes | 20 MiB | Aggregate base64 image-payload bound; exceeding it fails the request with IMAGE_OFFLOAD_REQUIRED |

IMAGE_OFFLOAD_REQUIRED triggers dsh-compaction-image-offload to record the selected occurrences in an image/offload event and retry the step (packages/llm/llm-pi-ai/README.md, Model Experience; core failure code documented on LlmFailure.offloadImages in docs/subsystems/llm-streaming.md).

Known limitations -- VERBATIM from packages/llm/llm-pi-ai/README.md ("Known Limitations and Deferred Work"):

- "maxRequestImageBytes counts base64 image payload only -- text, tools, descriptors, and JSON structure ride outside the bound, so it must sit below the gateway's request-body cap with headroom."
- "A sign-in lives only in the process that started it -- an authorization attempt is not durable, so reloading the page mid-login abandons it and the human starts over. Signing out is deleteRecord on the stored record, which forgets it locally without telling the issuer."
- "Provider-native discovery answers through this plugin's ambient context -- a route naming no credential defers to the catalog provider's own resolution, which asks for environment values (AZURE_OPENAI_API_KEY, AWS_PROFILE, and each provider's own set) and for local credential files. Both questions are answered here: the credential seam is consulted before the process environment, and file existence is checked against the host process's filesystem with ~ expanded. What it cannot do is read a credential file's contents -- a provider that parses ~/.aws/credentials itself does so directly, outside the seam."
- "Reset restores inherited configuration -- resetting a route supplied by a lower profile layer restores that route."
- "Complete Config replacement can remove inherited dictionary entries -- a field reset instead restores its inherited value."
- "headers can carry a credential the redactor never sees -- profile resolution rejects names and values Fetch cannot represent, but the dict remains plain strings; store credentials as apiKeyEnv references."
- "Discovery does not change configured models -- adopt discovery results explicitly into the route configuration."
- "Anthropic discovery reads at most 1,000 models -- the request uses the API's maximum page size but does not traverse has_more; entries beyond the first page must be added by hand."
- "One wire protocol per route -- a mixed-protocol catalog route cannot host a model of the other protocol; splitting the provider across two route keys is the workaround."
- "A modality declaration is not verified -- a model declaring image its gateway does not serve is refused by the provider after prompt admission. The durable image remains in history and the same misdeclared model can fail again; switching to a text-only model remains possible because the shared LLM runtime projects image references into stable text for that request."
- "An unauthenticated route depends on its protocol -- a route naming no credential resolves as configured-but-keyless, but pi-ai's OpenAI-compatible implementation still requires an API key or an Authorization header, so a keyless local server needs a placeholder credential referenced by apiKeyEnv or an Authorization entry in headers."
- "GenerateOptions.stop is unsupported -- pi-ai's common stream options cannot guarantee stop-sequence behavior across providers."
- "Only a leading in-history system message becomes pi-ai's systemPrompt -- pi-ai has one system slot, so a later system message, or a leading one when GenerateOptions.system is also set, folds into a user message at its position; provider-specific placement of the prompt follows pi-ai rather than a harness-owned wire override. Images in system or assistant history, including the leading system message, fail with UNSUPPORTED_CONTENT on both conversion paths."
- "Provider HTTP status is unavailable -- pi-ai error events do not expose a stable HTTP status across providers."
- "Retry policy is provider-owned, not an SDK retry -- pi-ai SDK retries stay disabled so durable agent steps and llm/retry events own every visible attempt, and direct ctx.llm.stream() calls remain single-attempt."
- "Streamed tool-call arguments are parsed once, when the call ends -- the installed pi-ai carries patches/@earendil-works__pi-ai@0.85.1.patch, which removes the per-delta re-parse of the whole accumulated argument JSON in every stream adapter (upstream earendil-works/pi#9265); unpatched, a multi-megabyte argument stream costs O(n^2) CPU on the event loop and stalls every session in the process. Until toolcall_end, a pi-ai partial's tool-call arguments stays {}; this adapter reads only the delta strings and the finalized arguments. Re-apply or retire the patch on every pi-ai upgrade."

Failure codes raised by llm-pi-ai (README "Failures and recovery"): INVALID_CREDENTIAL, MISSING_CREDENTIAL, UNKNOWN_MODEL, QUOTA (distinguished from transient RATE_LIMIT), UNSUPPORTED_OPTION (for stop), UNSTORABLE_PROVIDER_ID (hand-declared route keys outside the record grammar cannot be signed into).

## 6. Compaction and context window handling

Compaction is a capability seam, not part of the agent-loop spine (docs/subsystems/compaction.md): Service Definition dsh-compaction (ctx.compaction), Service Provider dsh-compaction-basic (a sibling backend could replace it), human Consumer dsh-command-compact.

Three merge-extensible, log-only SessionEventMap additions (not SurfaceEventTypes -- they don't join the model-visible surface directly):

| Event | Payload highlights | Role |
|---|---|---|
| compaction/start | { turn } (turn number, or null for a standalone manual attempt) | Acquires the durable lock |
| compaction/summary | { summary, rawOutput?, llmStreamCall?, shadowedRange, shadowedSeqs, shadowedTokenCount, provider, model, maxTokens?, usage? } | The safe summary projection and shadowed-node accounting |
| compaction/end | { turn, error? } | Releases the lock |

The summary itself rides on an ordinary user/message event with surfaceOp: { op: 'replace', startSeq, endSeq } -- the only surface mutation compaction performs.

Triggers: CompactionTrigger = 'pressure' | 'context-overflow'. ctx.compaction.compactIfNeeded(agent, trigger, signal) runs automatic policy; compactNow(agent, signal) does one useful idle-session reduction even below pressure (agent maintenance between turns); compactRegion(start, end, agent, signal?) forcibly compacts an explicit inclusive surface range, requiring both edges tool-call/result balanced.

Pressure compaction runs at the agent/pre-step waterfall before request derivation; failed-request recovery runs through agent/request-error after the failed step closes, and returns a retry action only when the surface replacement generation actually advanced. Optional ctx.toolResultPruner runs first (deterministic head/middle/tail pruning of oversized tool results) before range selection and remeasurement through the singleton ctx.tokenMeter. dsh-compaction-basic owns thresholds, retained-tail policy, overflow caps, and failure handling -- not documented as generic seam behavior.

Image offload (compaction-image-offload) is a related, separate mechanism: image/offload event selects exact depth-first image occurrences in a message to drop from later requests, replacing them with placeholder text; it preserves node/message identity and carries no surfaceOp.

Manual compaction failure codes (ManualCompactionErrorCode): busy | cancelled | changed | summary | commit | persistence.

## 7. Subagents

Subagent delegation is one optional capability with multiple coexisting named providers registered on ctx.subagents (docs/subsystems/subagent.md; packages/subagent/subagent/README.md). Two shapes:

- One-shot (SubagentRun): "one disposable foreground delegation with one result." SubagentRuntime.start(name, request) validates requested SubagentCapabilities (agentOptions, outputSchema, depthLimit, toolFilter, persona) against the named provider before dispatching to SubagentProvider.start(); an unsupported capability request is rejected loudly rather than silently ignored.
- Continuable (background, durable): "one durable child Session with at most one process-local Activation." startContinuable() reserves the child id, asks the provider for a ContinuableCreateSpec (only whether to seed with parent history), creates the child Agent, and submits the initial prompt. The continuation manager -- not the provider -- owns identity, composition, prompt delivery, cold resume, ownership, and disposal for continuable children.

Fork vs spawn (in-process backends, docs/subsystems/subagent.md "In-process backends" section): the fork backend passes a balanced completed-turn prefix of the parent's log (inheritsParentContext: true) via CreateAgentOptions.seed; spawn starts a fresh child with no seed (inheritsParentContext: false). Both create an ordinary one-shot agent through parent.ctx.

Control tools: the model-facing Consumers are dsh-tool-subagent (per-provider delegation tool) and dsh-tool-subagent-control (the optional global send_message, interrupt_agent, and list_agents controls) (docs/subsystems/subagent.md). SubagentRuntime.sendMessage() is the sole model-authored message operation between adjacent agents -- direct parent to direct continuable child only; siblings, ancestors beyond one edge, and self-targets are rejected. Delivery routes by Activation state: running -> steer nearest step; waiting -> wake and steer; no Activation -> cold-resume then steer.

SubagentRuntime.interrupt(targetSessionId, authority) is the one public stop: fire-and-return Agent.cancel(cause, { keepInbox: true }), preserving unclaimed pending inbox work and published descendants.

Delegation depth: durable SessionHeader.delegationDepth plus merge-extensible AgentOptions.subagentDepth; absence means depth zero; the seam (not the loop) owns both fields.

Capacity: maxActiveSubagents (default 8) bounds live continuable children sharing one uninterrupted parent-link pool; at capacity, creation/cold-resume rejects ACTIVATION_LIMIT_REACHED (browser: subagent/delivery-unavailable).

Terminal result (SubagentResult): { output, structured?, diagnostic?, stopReason }. SubagentStopReasonMap (merge-extensible): completed | aborted | error | max-tokens | refusal.

## 8. Goal / plan / todo / user-questions

Goal (docs/subsystems/goal.md, ctx.goals, package dsh-goal) -- same-session continuation objective. GoalPhase = 'active' | 'paused' | 'blocked' | 'complete'. Every mutation is a durable goal/change event (full-snapshot or clear tombstone); GoalRef { id, revision } is the compare-and-set identity -- mutation requires the expected current revision. Activation (whether a continuation consumer may start another round) is process-local, separate from durable phase. Service methods: get, disarm, create, edit, pause, resume, complete, block, clear.

Plan mode (docs/subsystems/plan.md, ctx.planMode, package dsh-plan-mode) -- "logged per-agent collaboration state... Plan mode is soft guidance." A log-only plan/mode { active: boolean } session event; contributes the plan:policy prompt section (order 50) while active, and registers the exit_plan_mode tool and /plan command. Explicitly not enforcement: "Sandbox mode and approval policy enforce restrictions independently; neither reads or writes plan state." Selections are pending until the next accepted in-turn pre-step appends them.

Todo: not among the read subsystem docs; referenced only as tool-todo/todo/write (a tool-owned session event seen in docs/subsystems/tools.md's pipeline diagram: todo/write is emitted by a tool body as one of the "tool-owned session events" alongside fs/observed, hook/invoked, hook/result, tool/ptc-dispatch). No further detail is in-scope from the read set.

User questions (docs/subsystems/user-questions.md, ctx.userQuestions, package dsh-user-questions) -- provider-neutral seam for asking a human before the agent continues. AskUserQuestionRequest carries questions: AskUserQuestionItem[] (id, question, detail?, header?, options?, multiSelect?, intent?). AskUserQuestionIntent currently has one tag, plan-review ({ kind: 'plan-review', approve, callId? }) -- used by exit_plan_mode's review flow. ctx.userQuestions.ask(request) dispatches the user-questions/request waterfall (scope-filtered) and throws UserQuestionError codes ASK_ABORTED, CALLER_NOT_LIVE, DELEGATED_CALLER (human interaction is valid only for the exact live runtime root -- an owned/delegated child has no human answerer and would block forever).

## 9. Cannot / does not

- Waterfall listeners that don't call next() short-circuit the chain -- this is by design for single-decision events, but a cooperative listener that forgets next() silently drops downstream listeners (docs/cordis-primer.md).
- agent/turn-stopping has no next() -- it is serial, not a waterfall; a listener objects by calling agent.steer(), not by returning a value (docs/architecture.md).
- The agent/request waterfall cannot mutate messages -- "Model-visible content must use logged channels; this waterfall cannot mutate messages" (docs/subsystems/core.md, agent/request JSDoc).
- tools/pre-execute cannot rewrite call arguments -- "Arguments cannot be rewritten because history, audit, UI, and execution must agree" (docs/subsystems/tools.md).
- A ToolGuard cannot re-allow a call another guard denied -- "guards have no allow result, listener ordering cannot turn a denial back into permission" (docs/subsystems/tools.md).
- tools/post-execute cannot replace both content and value in the same decision -- "Post-policy may replace either content or value, never both" (docs/subsystems/tools.md).
- A registered complete system-prompt section cannot be extended by later waterfall listeners -- it is restored as the sole prompt section after system-prompt/assemble runs (docs/subsystems/system-prompt.md).
- llm-pi-ai does not support GenerateOptions.stop -- rejected with UNSUPPORTED_OPTION because pi-ai's common streaming UI cannot guarantee it across providers (packages/llm/llm-pi-ai/README.md).
- llm-pi-ai supports only one system message slot -- a later or duplicate system message folds into a user message instead of being sent as a second system turn (packages/llm/llm-pi-ai/README.md).
- llm-pi-ai cannot mix wire protocols on one route -- one wire protocol per route; a mixed-protocol catalog route cannot host both (packages/llm/llm-pi-ai/README.md).
- llm-pi-ai does not expose provider HTTP status -- "pi-ai error events do not expose a stable HTTP status across providers" (packages/llm/llm-pi-ai/README.md).
- llm-pi-ai sign-in state is not durable across process restarts -- reloading mid-login abandons the attempt (packages/llm/llm-pi-ai/README.md).
- Continuable subagents are process-local -- "the Activation inbox and ownership graph do not coordinate two harness processes; concurrent access to one persistence store needs a durable mailbox and cross-process lease protocol" (packages/subagent/subagent/README.md, Known Limitations).
- ACP subagent children remain one-shot -- "an ACP run has no local child session in the parent's session corpus, and remote providers need an Activation ownership contract before they can support continuable children" (packages/subagent/subagent/README.md).
- Subagent messaging is adjacent-only -- no sibling, multi-hop-ancestor, or self-targeted messaging; a direct parent must stay live for child-to-parent delivery, since there is no durable parent mailbox (packages/subagent/subagent/README.md).
- A crash can lose an accepted-but-unlogged subagent message -- "the lost message is not replayed automatically" (packages/subagent/subagent/README.md).
- Plan mode enforces nothing -- it is soft guidance only; sandbox mode and approval policy are the actual enforcement points and are configured independently (docs/subsystems/plan.md).
- A plan-mode selection made after a turn's final accepted pre-step can be lost -- "remains process-local and is lost if the process exits before another accepted in-turn pre-step" (docs/subsystems/plan.md).
- ctx.userQuestions.ask() cannot be used by a delegated/owned agent -- only the exact live runtime root may ask a human; a delegated child would block forever, so this is explicitly rejected (DELEGATED_CALLER) rather than allowed to hang (docs/subsystems/user-questions.md).
- Config-declared agents (agents: list in dsh-agent-loop) have no per-agent persona field or setup hook -- they use the deployment persona; scoped persona/tool composition needs the programmatic ctx.agents.create()/resume() path (packages/core/agent-loop/README.md, Known Limitations).
- dsh-agent-loop has no built-in turn budget -- a runaway tool/steering loop must be bounded by an external policy hooking agent/turn-stopping or similar (packages/core/agent-loop/README.md).
- Tool-call parallelism classification is unary -- "calls whose safety depends on comparing siblings or resources must remain exclusive" (packages/core/agent-loop/README.md).

## Plexar notes

- Routing to a self-hosted vLLM/Qwen rig via llm-pi-ai: a self-hosted OpenAI-compatible server is a hand-declared route (api: openai-completions, baseURL pointing at the rig, models: [...]) rather than an installed-catalog entry, since pi-ai's installed catalog won't know a custom Qwen deployment. thinkingTokenBudgetField and vllmPriority are specifically called out as vLLM-facing compat switches, which is directly relevant if the rig runs vLLM.
- Because the route is keyless/self-hosted, the "An unauthenticated route depends on its protocol" limitation applies: vLLM's OpenAI-compatible server may still require some Authorization header/API key placeholder even with no real auth, so a dummy apiKeyEnv or headers entry may be needed to avoid request rejection.
- maxRequestImageBytes/requestImagePixelBudget matter for any multimodal Qwen-VL routing -- Plexar should size these against the rig's actual context window and image handling rather than trusting pi-ai defaults tuned for hosted providers.
- Reasoning-effort mapping (reasoningEfforts) is the mechanism to expose Qwen's thinking-mode toggles (or vLLM's reasoning-budget parameter) as harness-native ReasoningEffortIds, decoupling Plexar Studio's effort selector from vLLM's own parameter names.
- Embedding in Studio over stdio: the kernel's coordination surface is deliberately split into durable SessionEvents (replay-safe, what an SDK should consume for transcript reconstruction) versus live agent/* events (process-local coordination: status, inbox, streaming). A stdio-embedded Studio client should follow "SDK users that need replayable transcript data should consume session/event; agent/* is the live coordination API" verbatim -- i.e., use session/event/SessionEvent replay for anything Studio must survive a reconnect, and only trust agent/assistant-stream for live token-by-token UI.
- The agent-loop package registers itself as the sole AgentFactory on ctx.agents -- Studio embedding should go through ctx.agents.create()/resume() and the public Agent handle, never import dsh-agent-loop internals directly, since "consumers never import this package" is a stated design invariant.
- Tool approval (tools/pre-execute -> ask -> ctx.approval) is the natural interception point for Studio to insert an interactive approval UI over stdio; if Studio's transport can't answer synchronously, an absent/unanswerable approval channel becomes an automatic deny -- Studio must wire a real approval provider, not assume best-effort.
- User-question seam (ctx.userQuestions.ask) is the other Studio-facing interception point for blocking human input; note it only works for the runtime root agent -- a subagent spawned inside a Plexar pipeline cannot itself ask Studio a question.
- Subagent continuable-child process-locality means a Plexar Studio session that embeds the kernel via stdio in one process cannot durably hand off a running continuable subagent to a second Studio process without building a cross-process lease/mailbox layer that does not exist yet.
