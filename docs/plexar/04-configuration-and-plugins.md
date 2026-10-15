# Configuration and Plugins

How the dsh plugin tree is composed at boot, how a profile's layers stack, the patch grammar that edits a layer without editing its source, how the ten config rows the Plexar rig cares about are shaped, how to write a new plugin, and where a value lives (settings vs. credentials vs. env). Written for the Plexar framework team and the Plexar Studio team, neither of which has seen this codebase before.

## 1. Cordis in one page

Everything in dsh -- the model adapter, the tool registry, the session log, the agent loop itself -- is a **Cordis plugin**. There is no privileged core to patch; you extend dsh by mounting a plugin beside the others (`docs/architecture.md`).

- **A plugin** is a function `apply(ctx)`, an object `{ apply(ctx) {} }`, or a `Service` subclass. Cordis calls it with a **context** (`ctx`), the object through which the plugin registers everything it contributes (`docs/cordis-primer.md`, `docs/cordis-tutorial/01-first-plugin.md`).
- **A context is a repository of services.** A service claims a stable `ctx.<key>` (`ctx.tools`, `ctx.llm`, `ctx.sessions`); other plugins find it by key rather than importing a concrete implementation (`docs/cordis-tutorial/03-services.md`).
- **`inject`** declares service dependency: a plugin naming required services (`export const inject = ['tools']`) is held `PENDING` until every named service exists. Load order in the config file does not matter -- dependencies decide when a plugin starts (`docs/cordis-tutorial/03-services.md`). If a required service later disappears (unloaded, hot-replaced), every dependent plugin unloads too, and reloads when the service returns.
- **Events** are typed via TypeScript declaration merging (`interface Events { 'ns/action'(...): T }`) and dispatched as one of five modes (`docs/cordis-primer.md#dispatch-modes`, `docs/cordis-tutorial/04-events.md`):

  | Mode | Call | Awaited | Order | Returns |
  |---|---|---|---|---|
  | `emit` | `ctx.emit(name, ...args)` | No | registration order | No |
  | `waterfall` | `ctx.waterfall(name, ...args, next)` | No | registration order, around-middleware | Yes |
  | `parallel` | `await ctx.parallel(name, ...args)` | Yes | concurrent | No |
  | `serial` | `await ctx.serial(name, ...args)` | Yes | registration order, first non-null/false/undefined wins | Yes |
  | `bail` | `ctx.bail(name, ...args)` | No | registration order, sync version of serial | Yes |

  Waterfall listeners receive `(...args, next)`. Calling `next()` delegates to the next listener (possibly transforming what comes back); returning without `next()` is a deliberate short-circuit (the veto). A listener that only observes or annotates **must** call `next()` -- forgetting it silently swallows downstream behavior. This is a standing repository rule (`docs/cordis-primer.md#cordis-waterfall-semantics`, `CLAUDE.md`).
- **Registrations are reversible effects.** `ctx.effect()`, `ctx.on()`, `ctx.plugin()`, and harness registries such as `ctx.tools.register(...)` all return disposers that Cordis unwinds automatically when the owning plugin unloads, including on hot reload (`docs/cordis-tutorial/02-lifecycle-and-effects.md`). Every loaded plugin instance owns a **fiber** moving through `PENDING -> LOADING -> ACTIVE -> UNLOADING -> DISPOSED` (or `FAILED`). A plugin sitting silent and doing nothing is very often `PENDING` on a missing service -- this is the single most common "why isn't my plugin loading" answer (`docs/cordis-tutorial/06-composition-and-hmr.md`).
- **Config** is schema-validated before `apply` runs; bad config fails the load loudly with a precise error rather than starting the plugin half-configured (`docs/cordis-tutorial/05-config.md`).

## 2. Profile = bundles + `cordis.patch.yml` layers

A running `dsh` is a plugin tree composed at boot from ordered layers (`docs/architecture.md#profiles-and-bundles`).

- **A bundle** is a distribution format for Cordis config rows and the code they mount, declared in `package.json` under `dsh.bundle`, so whatever it inserts stays patchable by the layers above it.
- **A profile** is a named composition stored in the Harness home (`$DSH_HOME/profiles/<name>`). It lists the bundles it stacks (`package.json`'s `dsh.profile.bundles`, an ordered list) plus the user's own `cordis.patch.yml`. Shipped templates: `web`, `headless`, `sdk`, `sdk-minimal`, `acp`.

**Exact precedence order** (`docs/architecture.md#profiles-and-bundles`): layers apply to an empty entry list in this order --

1. each bundle in the profile's listed order (`dsh.bundle.patch` file(s), concatenated in bundle-list order),
2. the profile's own `cordis.patch.yml`,
3. the home-level `cordis.patch.yml`,
4. any `--patch` overlay passed on the command line.

A patch targets a row **by id** and either replaces its whole config or inserts new rows; **the last write wins per row** (`packages/bundle/base/cordis.patch.yml` header comment, `packages/bundle/plexar/README.md`). `packages/boot/app-boot/README.md` reiterates: "A user patch replaces the whole matched config -- an id-targeted patch does not deep-merge, so a profile override restates the bundle fields it keeps."

**`$DSH_HOME` layout** (from `packages/boot/app-boot/README.md`):

- `$DSH_HOME/profiles/<name>/` -- one directory per profile, holding the profile's `package.json` (bundle list) and its `cordis.patch.yml`.
- `$DSH_HOME/.env` -- home-level environment layer (below the invoking directory's `.env`, itself below the inherited process environment). `PATH`, `DSH_*`, `XDG_*`-style variables are rejected from `.env` files -- export them instead. The four proxy variables (`HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, `NO_PROXY`) are accepted only from the Harness-home file.
- `$DSH_HOME/cordis.patch.yml` -- the home-level tweak layer, applied after every bundle layer and after the per-profile patch. A patch naming a nonexistent entry prints a stderr warning; an empty or comments-only file **fails boot** -- disable the layer with `[]` instead.
- `$DSH_HOME/sessions`, `$DSH_HOME/storages`, `$DSH_HOME/.credentials.yaml`, `$DSH_HOME/.anonymous-user-id` -- referenced from `packages/bundle/base/cordis.patch.yml` via `dshHomePath(...)` and similar helpers.

**The `--patch` overlay** is an additional ordered patch file (or files) passed at the CLI, applied after the home-level patch -- the highest-precedence layer short of editing the profile itself. `packages/bundle/plexar/README.md`'s Web UI note uses a profile patch to disable rows that hard-inject the DeepSeek account service, as an example of this mechanism.

**`--dump-config`**: `dsh --profile <name> --dump-config` prints the exact composed entry list as loadable YAML, with `!!js` expressions verbatim, grouped under comments naming each source file and which patch layers changed each row (`docs/architecture.md`, `packages/boot/app-boot/README.md#previewing-the-effective-configuration`). Patches that match no row are reported with their layer label; a missing, unparsable, or invalid config fails the dump. Any row it prints can be replaced by a patch of your own. No byte-stability guarantee is made across package versions (`packages/boot/app-boot/README.md`, "Open: YAML config dump stability").

## 3. Patch grammar

A `cordis.patch.yml` file is a YAML list. Each entry is one of:

- **id-targeted override** -- an object carrying `id:` plus the fields to change. Whole-`config` replacement, not merge: restate every field you keep. Example, from `packages/bundle/plexar/cordis.patch.yml`:

  ```yaml
  - id: agent-default-model
    config:
      provider: plexar
      model: !!js process.env.PLEXAR_MODEL ?? 'qwen3.8-27b'
  ```

- **`disabled`** -- turns a row off without deleting the entry; flip it back and the plugin (and everything `PENDING` on its services) loads again (`docs/cordis-tutorial/06-composition-and-hmr.md`). Example, same file:

  ```yaml
  - id: llm-deepseek
    disabled: true
  - id: plugin-manager
    disabled: true
  ```

- **`insert`** -- adds brand-new rows rather than overriding existing ones. `packages/bundle/base/cordis.patch.yml` is itself one giant `insert:` block applied over the empty profile root (its header comment: "Applies as ONE insert over the empty profile root"):

  ```yaml
  - insert:
      - id: llm
        name: '@deepseek-ai/dsh-llm'
      - id: agent-default-model
        name: '@deepseek-ai/dsh-agent-default-model'
        config:
          provider: deepseek-official
          model: deepseek-flash
  ```

- **`!!js` expressions** -- evaluate JavaScript at load time, valid only inside a `config:` block and an entry's `disabled:` field (never `!js`, and never elsewhere in the row -- `name`, `id`, `inject` stay static). `config` values are interpolated once, against that plugin's own `ctx`, after its declared injections have activated; `disabled` is re-evaluated against the loader context at **every** mount decision, so a row can gate itself on platform or environment (`docs/cordis-primer.md#loader-configuration`, `docs/cordis-tutorial/05-config.md`). Examples from `packages/bundle/plexar/cordis.patch.yml`:

  ```yaml
  - id: llm-pi-ai
    config:
      providers:
        plexar:
          baseURL: !!js (process.env.PLEXAR_RIG_URL ?? 'https://llm.plexar.tech') + '/v1'
          models:
            - id: !!js process.env.PLEXAR_MODEL ?? 'qwen3.8-27b'
  ```

  and from `packages/bundle/base/cordis.patch.yml`:

  ```yaml
  - id: bash-sandbox
    disabled: !!js process.platform === 'win32'
  - id: approval
    config:
      policy: !!js "(process.env.DSH_PERMISSION_MODE ?? 'workspace-write') === 'danger-full-access' ? 'never' : 'ask'"
  ```

`packages/bundle/plexar/cordis.patch.yml` end to end is worth reading as the canonical small patch: it re-routes the model (`llm-pi-ai`, `agent-default-model`), rewrites the persona (`system-prompt`), disables every DeepSeek-cloud row (`llm-deepseek`, `deepseek-llm-api-extensions`, `plugin-package-inventory-deepseek`, `session-log-deepseek`, `deepseek-account`, `web-search-deepseek`, `session-telemetry-otel`), and trims marketplace/ralph/websearch surface -- 76 lines total, "every line here is an id-targeted override or a disable against rows [base and headless] already declare... Trim = compose."

## 4. Config rows: the ten plugins

Extracted from `docs/config-catalog.md` (4279 lines, generated from source; verified against runtime Schemastery schemas). Field names and defaults exactly as declared.

### `llm-pi-ai` (`@deepseek-ai/dsh-llm-pi-ai`) -- requires `llm`

Mounts dormant: zero routes until a `providers` dict is non-empty (a settings section, or a patch row, supplies it).

| Field | Type | Default | Notes |
|---|---|---|---|
| `providers` | `Volatile<Record<string, PiAiProviderProfile>>` | `{}` | Keyed by provider route name; the dict key *is* the route. |

`PiAiProviderProfile` (per route): `apiKeyEnv?: string` (credential reference resolved per request via `ctx.credentials`), `displayName?: string`, `api?: string` (wire protocol, e.g. `openai-completions`), `baseURL?: string`, `models?: PiAiModelProfile[]`, `modelOverrides?: Record<string, PiAiModelOverride>`, `compat?: PiAiCompatProfile`, `defaultContextWindow?: number` (default 262,144), `defaultMaxTokens?: number` (default 32,768), `defaultInput?: PiAiModality[]` (default `[text]`), `headers?: Record<string,string>`, `reasoning?: ModelThinkingLevel`, `thinkingBudgets?: ThinkingBudgets`, `cacheRetention?: CacheRetention`, `transport?: Transport`, `timeoutMs?: number`, `websocketConnectTimeoutMs?: number`, `streamIdleTimeoutMs?: number`, `maxRequestImageBytes?: number`, `requestImagePixelBudget?: number`, `requestImageMaxBytes?: number`, `retryPolicy?: RetryPolicyConfig` (default: normal mode, five retries).

`PiAiModelProfile` (per model): `id: string`, `name?`, `contextWindow?`, `maxTokens?`, `input?: PiAiModality[]`, plus reasoning-effort fields.

### `agent-default-model` (`@deepseek-ai/dsh-agent-default-model`)

| Field | Type | Notes |
|---|---|---|
| `provider` | `Volatile<string>` | Registered provider route. |
| `model` | `Volatile<string>` | Provider-owned model id. |
| `reasoningEffort` | `Volatile<string \| undefined>` | Omission follows the provider default. |

No shipped default object -- base sets `provider: deepseek-official`, `model: deepseek-flash`; the Plexar bundle overrides to `provider: plexar`, `model: !!js process.env.PLEXAR_MODEL ?? 'qwen3.8-27b'`.

### `sandbox-policy` (`@deepseek-ai/dsh-sandbox-policy`) -- requires `sessionProjections`

| Field | Type | Default |
|---|---|---|
| `mode` | `SandboxMode?` | `read-only` (fail-safe) |
| `workspaceRoot` | `string?` | `process.cwd()` |

Base sets `mode: !!js process.env.DSH_PERMISSION_MODE ?? 'workspace-write'`, `workspaceRoot: !!js process.cwd()`. This is the one shared policy home -- the sandbox *runner* choice is a separate `ctx.sandbox` provider config, not here.

### `system-prompt` (`@deepseek-ai/dsh-system-prompt`)

| Field | Type | Default |
|---|---|---|
| `includeHarnessIdentity` | `boolean?` | `true` |
| `includeRuntimeContext` | `boolean?` | `true` |
| `personaPrefix` | `string?` | -- (base sets `''`; a scoped `deployment:persona-prefix` section shadows it) |
| `personaSuffix` | `string?` | empty |
| `toolOrder` | `string[]?` | lexicographic if omitted; must include `TOOL_ORDER_REST` exactly once |

`{{variable}}` references in prefix/suffix are strict. The Plexar bundle sets both: `personaPrefix: "You are Plexar, a coding agent running on a self-hosted {{model}} model..."`, `personaSuffix: "Your working directory is {{cwd}}."`.

### `tools` (`@deepseek-ai/dsh-tools`) -- requires `systemPrompt`

| Field | Type | Default | Notes |
|---|---|---|---|
| `mode` | `ToolPresentationMode?` (`'native' \| 'ptc' \| 'both'`) | `native` | `ptc` sends only `run_code` + generated SDK prompt; requires `ctx.ptcRuntime`. |
| `maxParallelSubCalls` | `number?` | `10` | Concurrency cap for `run_code` sub-calls; must be a positive integer. |

### `mcp` (`@deepseek-ai/dsh-mcp-resources`, mounted as `id: mcp-resources` in the base bundle) -- requires `tools`

This row has **no `config:` block** in `docs/config-catalog.md` -- no dedicated Config section exists for it there (it appears only in the service-listing note, `docs/config-catalog.md:4178`). It is a service provider mounted with default (implicit) config, contributing MCP resources into `ctx.tools`. (`@deepseek-ai/dsh-mcp-client`, a related but distinct package, does declare fields -- see `docs/config-catalog.md:1935` -- but is not the row the base/Plexar bundles mount.)

### `skill` (`@deepseek-ai/dsh-skill`)

| Field | Type | Notes |
|---|---|---|
| `collectCacheMaxEntries` | `number?` | Maximum completed cwd/provider catalogs kept in memory. |

(`skill-filesystem`, the concrete provider mounted by base, has its own much larger config -- `providerName`, `includeDefaultRoots`, `dshHome`, `agentsHome`, `customSkillDirs`, `watch`, `watchUsePolling`, `watchStabilityThresholdMs`, `watchPollIntervalMs`, `watchMaxProjects`, `watchFollowSymlinks`, `bundledSkillDir` -- but the ten-plugin list names `skill`, the registry.)

### `compaction-basic` (`@deepseek-ai/dsh-compaction-basic`) -- requires `llm`, `tokenMeter`, `sessions`

| Field | Type | Default |
|---|---|---|
| `modelPolicies` | `ModelCompactPolicyConfig[]?` | -- (duplicate targets fail plugin load) |
| `auto` | `boolean?` | `true` |
| `thresholdRatio` | `number?` | `0.8` |
| `headroomTokens` | `number?` | `65536` |
| `retainRatio` | `number?` | `0.16` |
| `retainTokens` | `number?` | -- (mutually exclusive with `retainRatio`) |
| `summarizationProvider` | `string?` | inherits conversation target |
| `summarizationModel` | `string?` | inherits conversation target |
| `maxTokens` | `number?` | resolved `headroomTokens` |
| `compactionRetries` | `number?` | `1` |
| `maxOverflowRetries` | `number?` | `1` |

`ModelCompactPolicyConfig` extends the above with required `provider: string` and `model: string` for an exact-target override.

### `subagent` (`@deepseek-ai/dsh-subagent`)

| Field | Type | Default |
|---|---|---|
| `maxActiveSubagents` | `Volatile<number>` | `8` |
| `maxDepth` | `Volatile<number>` | `1` |

Distinct from `subagent-spawn-in-process` / `subagent-fork-in-process` (provider mounts) and `tool-subagent` / `tool-subagent-fork` (the model-facing tool rows), each configured separately in the base bundle.

### `session-persistence-jsonl` (`@deepseek-ai/dsh-session-persistence-jsonl`)

| Field | Type | Default |
|---|---|---|
| `root` | `string` | **required, no default** -- a `process.cwd()` default would scatter session files as cwd changes |
| `compression` | `JsonlCompression?` (`'zstd' \| 'none'`) | checksummed Zstandard frames |

Base sets `root: !!js dshHomePath('sessions')`.

## 5. Writing a plugin

A plugin that ships browser UI has two independently-loaded halves, declared in its own `package.json` `dsh` field:

- **Node half** (`dsh.bundle`) -- the Cordis plugin that runs in the Host process. Points at a `cordis.patch.yml` (for a bundle) or is a plain module a profile row names directly.
- **Client half** (`dsh.client`) -- declared with `platform: 'web'`, optional `inject` edges, optional `immediately`, and exported at `exports["./client"]` in `package.json`. It is scanned by `dsh-client-modules` independently of the Node half and materializes in the browser as a lazy-CJS module (`docs/subsystems/client-modules.md`).

`packages/client/ui-brand-plexar/src/index.ts` is the minimal example of a Node half that exists only to give the browser half a Loader seat:

```ts
/** Plexar browser-brand plugin, node half: an empty Loader seat; the browser half ships via exports["./client"]. */
export function apply(): void {}
```

-- an empty `apply()`; all real content ships through `exports["./client"]`, not shown here (outside this worker's read list).

**Build gotchas recorded in `packages/bundle/plexar/README.md`** (measured 2026-09-22):

- **Node >= 22.19 or 24 required.** The CLI entry guards on `import.meta.main`; older Node exits 0 silently with no output.
- **Source mode needs the repo tsconfig.** `pnpm dsh` resolves `@deepseek-ai/*` to `src/` through tsconfig paths. Running from another cwd requires `TSX_TSCONFIG_PATH=<repo>/tsconfig.json` and the absolute tsx loader path (`node --import file:///<repo>/node_modules/tsx/dist/esm/index.mjs <repo>/apps/cli/src/bin.ts --profile plexar "<task>"`).
- **`typert-loader` warns "1 entry did not activate"** in source mode because `lib/typert.host.js` is unbuilt -- harmless for headless runs, goes away with a built `lib/`.
- **Rig key.** Off-loopback, the rig requires a bearer (`PLEXAR_HARNESS_KEY`).
- **WireGuard.** The work VPN hijacks `the LAN subnet`; if the rig times out, drop the tunnel.

Installing a bundle as a plugin author (`packages/bundle/plexar/README.md`):

```sh
pnpm dsh --profile plexar --from-default-profile headless --help   # creates $DSH_HOME/profiles/plexar
pnpm dsh plugin --profile plexar add link:<abs path>/packages/bundle/plexar
```

The repo-wide plugin conventions (`packages/CLAUDE.md`) that any new plugin must follow: service packages default-export their service class; function plugins named-export `name` / `inject` / `Config` / `apply` with **no default export** -- mixing the two forms makes the Loader silently discard the function plugin's namespace. Optional services use `ctx.get(name)`, never a bare `ctx.<name>` property read, since the property proxy is topology-sensitive.

## 6. Settings vs. credentials vs. env

Three distinct value-storage seams, each with different precedence and write paths:

- **Settings** (`docs/subsystems/settings.md`, `@deepseek-ai/dsh-settings`) project **volatile Config fields** from active profile entries into editable forms, keyed by profile entry id (`ns`). `ctx.settings.describe()` reads schemas + live values; `update()` merges, `replace()` resets-then-sets, `mutate()` addresses individual paths without restating redacted secrets. Every write validates the complete Config and refuses stale revisions (optimistic concurrency via `expectedRevision`). Settings writes ultimately persist through Cordis patches via the configuration editor (`packages/boot/config-editor`) -- i.e., settings-page edits *are* patch-layer writes, just through a friendlier API than hand-editing `cordis.patch.yml`.
- **Credentials** (`docs/subsystems/credentials.md`, `@deepseek-ai/dsh-credentials`) keep secrets **out of configuration entirely**: a `CredentialRef` is a POSIX-style environment-variable *name* (not a value), stored in config/settings; a `CredentialProvider` (e.g. `dsh-credentials-local`) resolves that name to an actual value. Consumers (model adapters) `resolve(ref)` **once per operation, never cached** -- this is the hot-update mechanism: rotate a credential and the very next request picks it up with no restart. An empty stored value is absent everywhere (seam-wide rule). `describe(ref)` answers configuration surfaces without ever exposing the value. The local provider's source layers, in order: `env` (inherited process environment, read-only -- a write here is rejected because it would appear to succeed while resolution kept returning the shadowing value), `file` (the managed `$DSH_HOME/.credentials.yaml`), `project-env`, `user-env`.
- **Env** (`.env` files, `packages/boot/app-boot/README.md`) supplies ordinary process environment layers, loaded before Cordis config: invoking-directory `.env` outranks Harness-home `.env`, both sit below the inherited environment. Boot-deciding variables (`PATH`, `DSH_*`, `XDG_*`) are rejected from `.env` files and must be exported instead. The four proxy variables are accepted only from the Harness-home `.env`. `!!js process.env.X` inside a patch's `config:` reads this layer directly at load time -- this is how the Plexar bundle picks up `PLEXAR_HARNESS_KEY`, `PLEXAR_RIG_URL`, `PLEXAR_MODEL`.

Precedence for one logical value, high to low: `--patch` overlay > home `cordis.patch.yml` > profile `cordis.patch.yml` > bundle layers > schema default -- orthogonal to this is the credential seam, which never lives in that stack at all; a `CredentialRef` is just a name, resolved independently at request time through whichever provider is mounted.

## 7. Cannot / does not

- A patch **cannot deep-merge** a targeted row's config -- restating the fields you keep is mandatory; there is no partial-field patch grammar for an id-targeted override (only `insert` adds net-new rows).
- `!!js` **cannot** appear anywhere in a patch entry except inside `config:` values and the `disabled:` field; `name`, `id`, and `inject` are always literal, never expressions.
- An empty or comments-only `cordis.patch.yml` **does not** silently no-op -- it fails boot. Use `[]` to disable a layer instead.
- `mcp-resources` as mounted by the base/Plexar bundles **does not** expose a documented `config:` schema in the generated catalog -- there is nothing to tune on that row beyond enabling/disabling it.
- Relinking a profile package (`dsh plugin add link:...` pointed at new bytes) **does not** take effect without a process restart -- Node caches real paths.
- `session-persistence-jsonl`'s `root` **has no default** and **cannot** be omitted; there is deliberately no `process.cwd()` fallback because a subprocess or `bash` call could change cwd mid-session.
- The plugin manager **cannot** disable its own management components, change another profile, or edit an agent preset's composition (`packages/boot/plugin-manager/README.md`).
- A credential reference supplied by the live process environment **cannot** be written through `set()` -- the provider reports `writable: false` and a write is rejected outright rather than appearing to succeed while the shadowing value keeps winning.

## Plexar notes

- **Routing to the self-hosted rig is exactly one bundle patch, not a fork.** `packages/bundle/plexar/cordis.patch.yml` proves the whole pattern in 76 lines: add an `llm-pi-ai` provider route (`providers.plexar`, `api: openai-completions`, `baseURL` from `PLEXAR_RIG_URL`), point `agent-default-model` at it, and disable every DeepSeek-cloud row. No upstream file is touched -- this is the template for any future rig or model swap.
- **`llm-pi-ai` mounts dormant until `providers` is non-empty** -- this is a real Cordis-native "off by default, on the moment config supplies it" mechanism (the settings-driven posture the base bundle's comments describe for the Web Models page), worth reusing for any Plexar-Studio-driven provider toggle rather than reinventing an enable flag.
- **The rig's bearer key is env + credential-ref, not a patch literal.** `PLEXAR_HARNESS_KEY` flows in via `apiKeyEnv: PLEXAR_HARNESS_KEY` and is resolved per-request through `ctx.credentials`, never baked into `cordis.patch.yml` -- rotating it needs no restart, which matters for a long-running Studio-embedded session.
- **Precedence gives Studio a safe place to override the rig URL without touching the bundle**: a `--patch` overlay (or the profile's own `cordis.patch.yml`) beats the bundle layer, so Studio can point a given profile at a different rig instance (dev vs. prod Qwen box) purely from the profile directory, no bundle edit.
- **Embedding over stdio is an `acp` or `sdk` profile, and both are just more bundle layers** -- `dsh --profile sdk` / `dsh --profile acp` compose the same way (`base` + a mode bundle + optional patches); a Studio embedding does not need a new application entry point, only a profile + patch stack, per the "Application launch" rule that forbids bypassing `dsh` (`docs/architecture.md#application-launch`, `CLAUDE.md`).
- **`system-prompt.personaPrefix`/`personaSuffix` is the whole "who is this agent" surface** and it is entirely patch-driven (`{{model}}`, `{{cwd}}` interpolation) -- Studio can brand/re-persona a Plexar session per profile without code.
- **Watch for `mcp-resources` having no tunable config** -- if Studio needs to scope which MCP resources a Plexar session sees, that control is not exposed as a `config:` field on this row today; it would need to come from whatever registers into `ctx.tools`/`ctx.mcp*` upstream of this plugin (outside this worker's read list).
- **`--dump-config` is the debugging entry point for "why did my patch not apply"** -- always check it first (it shows every row's winning source layer) before assuming a bug in the patch grammar itself.
