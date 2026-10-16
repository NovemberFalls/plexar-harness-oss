# Plexar Harness

Plexar Harness is a coding agent for your own models. It runs in a terminal, in a desktop window, or embedded in an editor over ACP, and talks to any OpenAI-compatible endpoint: the hosted Plexar models, or a server you run yourself (vLLM, llama.cpp, Ollama, LM Studio).

Website: [harness.plexar.tech](https://harness.plexar.tech)

## Download (Windows)

**[PlexarHarness_0.4.6_x64-setup.exe](https://downloads.plexar.tech/harness/windows/PlexarHarness_0.4.6_x64-setup.exe)** — one installer, no prerequisites. It bundles Node, installs the desktop app, puts the `plexar-harness` command on your `PATH`, and updates itself when a new release is published.

The installer is not Authenticode-signed yet, so Windows SmartScreen shows "Windows protected your PC" the first time. Choose **More info**, then **Run anyway**.

On macOS and Linux, run from source (below).

## Use it

```sh
plexar-harness                # interactive session in the current folder
plexar-harness "fix the failing test"
plexar-harness -p "task"      # one turn, print the answer, exit
plexar-harness -c             # resume the newest session here
plexar-harness web            # browser UI
plexar-harness eval           # score the model on the built-in task suite
```

Sign in with `plexar-harness login` to use the hosted Plexar models, or skip sign-in and point it at your own server:

```sh
export PLEXAR_BYO_BASE_URL=http://localhost:8000/v1
export PLEXAR_BYO_MODEL=Qwen/Qwen3-32B
export PLEXAR_BYO_API_KEY=...   # only if your server needs one
plexar-harness
```

Full command reference: [docs/plexar/08-cli.md](docs/plexar/08-cli.md).

## What it does

- **Small-model friendly.** A lean default tool set, and invalid tool calls get the tool's schema back so the model can correct itself. `PLEXAR_TOOL_PROFILE=full` restores every tool.
- **Ask before it runs.** Shell commands need approval unless you choose full access, and file tools ask before touching anything outside the workspace in every mode.
- **Measurable.** `plexar-harness eval` runs real tasks in throwaway folders and logs the score, so you can compare models and settings over time.
- **Visible.** `--timings` shows where startup time goes; every turn reports time to first token and tokens per second.
- **Durable sessions.** Every session is a log on disk; resume it from the terminal, the desktop app, the browser UI or Plexar Studio.
- **Browser Bridge.** A Chrome extension that lets the agent read and drive a browser tab you choose.

## Run from source

Requires Node `^22.19 || >=24` and pnpm.

```sh
git clone https://github.com/NovemberFalls/plexar-harness-oss.git
cd plexar-harness-oss
pnpm install
pnpm run build
powershell -File packages/bundle/plexar/profiles/install.ps1   # Windows: profiles + PATH
plexar-harness
```

On macOS and Linux, run the launcher directly: `packages/bundle/plexar/cli/plexar-harness`.

## Documentation

- [docs/plexar/](docs/plexar/00-README.md): how Plexar Harness is put together, its configuration and plugins, the Studio API.
- [packages/bundle/plexar/README.md](packages/bundle/plexar/README.md): the Plexar bundle, its plugins and settings.

## Built on DeepSeek Harness

Plexar Harness is a fork of [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) (`dsh`), the open-source, everything-is-a-plugin agent harness by [DeepSeek AI](https://deepseek.com), built on [Cordis](https://github.com/cordiverse/cordis). The agent loop, plugin architecture and most of the code in this repository are their work, released under the MIT license. Thank you to the DeepSeek team.

Plexar's additions live in `packages/bundle/plexar/` (one plugin bundle composed over the upstream profiles), `apps/plexar-desktop/`, `apps/plexar-browser-extension/` and `docs/plexar/`. The rest follows upstream; see the [upstream README](https://github.com/deepseek-ai/deepseek-harness#readme) and its [documentation](https://deepseek-harness.github.io/deepseek-harness/) for the harness itself. Read the [safety notice](SAFETY.md) before running it.

## License

MIT. See [LICENSE](LICENSE) for DeepSeek's copyright and Plexar's.
