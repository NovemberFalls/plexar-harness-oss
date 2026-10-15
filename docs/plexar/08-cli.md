# `plexar-harness` — the terminal client

`plexar-harness` is an interactive terminal client for Plexar Harness, in the style of `claude` and `codex`. It runs the `plexar-acp` profile in the current folder and speaks ACP to it over stdio. That is the same wire and the same sessions that Studio (`07-studio-api-contract.md`) and the Web UI use. A session started in one of them can be resumed in the others.

Source: `packages/bundle/plexar/cli/`. Plain Node ESM; the only runtime dependency is `@napi-rs/keyring`, for the OS credential store.

| File | Role |
|---|---|
| `plexar-harness.mjs` | Entry point: argument parsing, the input loop, slash commands, permission prompts |
| `acp.mjs` | `HarnessRuntime`: spawns the profile and speaks JSON-RPC 2.0, one frame per line, on the child's stdio |
| `auth.mjs` | PKCE sign-in against the rig, `login`/`logout`, and the entitlement gate the launcher runs before starting any Host |
| `credentials.mjs` | `resolveKey()` and the OS credential store entry (service "Plexar Harness", user "default"), shared with the desktop app |
| `render.mjs` | Draws each `session/update` kind; `style` ANSI helpers |
| `logo.mjs` | The launch header (three lines: version; the model as a light-orange badge · effort; folder — the mode lives in the status line) and the attention mark (an exclamation mark in a hexagon, orange gradient) shown only on the folder-trust screen |
| `tui/` | The terminal UI: `term.mjs` palette and escapes, `keys.mjs` raw-mode key router, `composer.mjs` framed input with the `/` menu, `select.mjs` arrow-key choices, `spinner.mjs` animated working line, `phrases.mjs` its 100 status lines, `signin.mjs` the signed-out state machine for in-TUI sign-in |
| `settings.mjs` | Trusted folders and the last permission mode, in `~/.dsh/plexar-harness.json` |
| `plexar-harness.cmd`, `plexar-harness` | Launchers for Windows and POSIX shells |

## Install

1. Install the profiles and put the launcher on your PATH: `powershell -File packages/bundle/plexar/profiles/install.ps1`. The script is idempotent. It adds `packages/bundle/plexar/cli` to the user `Path` once.
2. Open a new terminal, then run `plexar-harness login` to sign in, then `plexar-harness` in any folder. The command is not `plexar`, because that name belongs to the Plexar Framework CLI.

Requirements: Node `^22.19 || >=24`, `pnpm install` done in the checkout. `-p` and `acp` run the entitlement gate before starting and exit 1 with a message when it fails (see "Sign-in" below); the interactive client instead checks it in place and never exits, signing in inside the harness itself. `login`, `logout`, `update`, `--help` and `--version` skip the gate. `PLEXAR_HARNESS_KEY` is a developer fallback used only when the OS credential store holds no key, since a stored real sign-in must never be shadowed by a stale shared key.

## Usage

```
plexar-harness                interactive session in the current folder
plexar-harness "task"         interactive, starting with this prompt
plexar-harness -p "task"      one turn, print the answer, exit
plexar-harness -c             resume the newest session in this folder
plexar-harness --resume <id>  resume a session by id
plexar-harness export <id>    print a session as text (09-session-export.md)
plexar-harness acp            run the ACP profile on stdio for Plexar Studio (07-studio-api-contract.md, "Launch")
plexar-harness update         pull the latest harness, reinstall, rebuild
plexar-harness web            open the browser UI (--port N, --no-open)
plexar-harness login          sign in to Plexar (--no-browser for a pasted code)
plexar-harness logout         sign out and remove the stored key
```

| Flag | Effect |
|---|---|
| `-p`, `--print` | Run one turn without prompting and exit. The prompt comes from the arguments, or from stdin when there are none. Thinking is collapsed. Permission requests are rejected. |
| `-c`, `--continue` | Resume the newest persisted session for this folder. With none, it starts a new one and says so on stderr. |
| `-r`, `--resume <id>` | Resume the given session. |
| `-e`, `--effort <off\|high\|default>` | Set `reasoning_effort` before the first turn. `default` keeps the model's own default effort; a model with no effort levels ignores `-e`. |
| `--model <id>` | Set the session model before the first turn. Matches the option value, its display name, or the bare model id (`qwen3.8-27b`). An unknown model exits 1 and lists the available ids. Automation passes it so its records name the model. |
| `-m`, `--mode <ask\|auto-edit\|full-access>` | Permission mode for the session (see "Permission modes"). Default: the last mode chosen interactively, else `auto-edit`; `-p` defaults to `auto-edit`. |
| `--read-only` | Same as `--mode ask`. |
| `--no-thinking` | Collapse thinking to one `✻ thinking…` line per block. |
| `--cwd <dir>` | Workspace folder. Default: the current folder. |
| `-v`, `--version` | Print the bundle version. |
| `-h`, `--help` | Print usage. |

Environment: `PLEXAR_HARNESS_SETTINGS` overrides the settings file path. `PLEXAR_HARNESS_ROOT` selects the harness checkout that runs the profile. By default it is the checkout containing the client. A checkout runs its built `apps/cli/lib/bin.js` when present (`plexar-harness update` rebuilds it; run `pnpm run build` after editing sources), else the TypeScript sources through tsx, which is slower to start; `PLEXAR_HARNESS_SOURCE=1` forces the sources. `NO_COLOR` disables ANSI styling, which is also off when stdout is not a terminal. The rig variables (`PLEXAR_HARNESS_KEY`, `PLEXAR_RIG_URL`, `PLEXAR_MODEL`) pass through to the harness.

## Launch

On a terminal the client clears the screen, shows an animated `Waking the harness…` line, then draws the header. The first launch in a folder shows the attention mark and asks "Do you trust the files in this folder?" as an arrow-key choice. Yes is saved for that folder and every folder inside it; No exits without starting the harness. `-p` and piped input skip the question.

## Terminal UI

When stdin and stdout are both a terminal, the client runs in raw mode. When either is piped, it uses plain line input with the same commands, which is what scripts and tests exercise.

- **Composer:** a framed input box with the placeholder "Ask Plexar to do anything". Long input wraps inside the box, which grows a row at a time; the sent message is echoed wrapped under `›`.
- **Status line** under the box: `›› <mode> on · shift+tab to cycle · / for commands · ? for shortcuts`.
- **`/` menu:** typing `/` lists client commands, harness commands (`/compact`, `/goal`, `/permission`, `/feedback`) and the Plexar skills, filtered as you type. ↑/↓ select, Tab completes, Enter runs the selection.
- **Choices** (folder trust, tool approvals) are arrow-key menus: ↑/↓ move, Enter confirms, a digit picks directly, `y`/`n` pick the yes-like or no-like option (Allow/Yes/Trust, Reject/No/Deny), Esc cancels (an approval then rejects).
- **Keyboard shortcuts:** `?` on an empty line opens this list in place; any other key closes it.

  | Key | Action |
  |---|---|
  | Enter | Send |
  | Esc | Clear the line; during a turn, stop it |
  | Ctrl+C | Clear the line; during a turn, stop it; twice within 2 s on an empty line, quit |
  | Ctrl+D | Quit (empty line) |
  | Shift+Tab | Cycle ask / auto-edit / full-access |
  | `/` | Command menu; Tab completes |
  | ↑ / ↓ | History, or move in a menu |
  | ← → Home End, Ctrl+A / Ctrl+E | Move the cursor |
  | Ctrl+← / Ctrl+→ (Alt+← / Alt+→, Alt+B / Alt+F) | Jump a word |
  | Ctrl+W, Ctrl+Backspace, Alt+Backspace | Delete the word before the cursor |
  | Ctrl+K / Ctrl+U | Delete to the end / clear the line |
  | Ctrl+L | Clear the screen and redraw the header |
  | Ctrl+= / Ctrl+- (Alt+= / Alt+-) | Expand: redraw the last edit's diff in full and show later diffs in full · Collapse: cap later diffs at 16 rows again. Many terminals keep Ctrl+= / Ctrl+- for font zoom and never pass them on; the Alt keys always work. |
  | `y` `n` `1`–`9` | Answer a prompt |
- **Working line:** while a turn runs, a spinner with an orange shimmer cycles through 100 fantasy status lines ("Fighting the dragon…", "Opening the treasure chest…") every few seconds, with elapsed time. It steps aside whenever the model streams text.
- **Palette:** Plexar orange gradient for the title, accents and the active mode; gunmetal for frames. `NO_COLOR` turns colors off.
- **`!` means permission.** The attention mark and the `!` prompt marker appear only when the user is asked to grant something: folder trust and tool approvals. Other choices use `?`.
- **Not yet:** typing ahead while a turn runs, and multi-line input (a pasted newline submits).

## Permission modes

Plexar follows the Claude Code model: there is no OS sandbox, and shell commands run as the user. Safety comes from asking. `@plexar/dsh-plexar/command-approval` checks each `bash` and `pwsh` call before it runs.

| Mode | Harness preset | Shell commands | File edits (edit/write tools) |
|---|---|---|---|
| `ask` | `read-only` | Ask, unless allowlisted | Ask |
| `auto-edit` | `workspace-write` | Ask, unless allowlisted | Free inside the folder; ask outside it |
| `full-access` | `danger-full-access` | Never ask | Never ask |

A command runs without asking when every part of it (split on `&&`, `||`, `;`, `|`) starts with an allowed prefix and it has no redirection (`<`, `>`) or command substitution. The shipped allowlist is read-only and test commands (`ls`, `cat`, `grep`, `git status`, `git diff`, `git log`, `pytest`, `npm test`, `Get-ChildItem`, …), set in `cordis.patch.yml` under `plexar-command-approval`. `/allow <prefix>` adds a prefix for the current session (in memory; it ends with the process); `/allow` alone lists both. The permission presets load with `shellConfinement: none`, so their sandbox value governs only the edit and write tools.

The prompt shows the current mode (`auto-edit ›`). Shift+Tab cycles modes, and the change applies to the open session before its next turn. `/mode <id>` switches immediately. A switch runs the harness `/permission <preset>` command on the current session, so it takes effect without a restart and is recorded in the session log. `/new` and `/resume` apply the selected mode to the session they open. The choice is saved as the default for later launches.

## Commands

| Command | Effect |
|---|---|
| `/help` | List commands. |
| `/mode [id]` | List modes, or switch the current session to one. |
| `/new` | Start a fresh session in this folder. |
| `/sessions` | List up to 15 resumable sessions, newest first. The open session is not listed, because `session/list` returns inactive sessions only. |
| `/resume <n\|id>` | Resume by list number or session id. |
| `/model [value]` | Show the model and its choices, or set one by value or display name. |
| `/effort [off\|high\|default]` | Show or set reasoning effort. |
| `/thinking [on\|off]` | Show or collapse thinking. With no argument it toggles. |
| `/clear` | Clear the screen and redraw the header. |
| `/exit`, `/quit`, `exit`, `quit` | Quit. A bare `exit` or `quit` line never reaches the model. Ctrl-D also quits. |
| `/login` | Sign in inside the harness: the loopback PKCE flow, in the same terminal ("Sign-in" below). Also runs on Enter with an empty composer while signed out. |
| `/logout` | Revoke the stored key server-side and delete it locally; the client returns to the signed-out state without quitting. |
| `/rename [title]` | Set this session's title (harness command from `@plexar/dsh-plexar/rename`, so Studio and the Web sidebar show it too; a user title is never overwritten by automatic naming). With no title, shows the current one. |
| any other `/name ...` | Sent to the harness. Registered harness commands (`/compact`, `/goal`, `/permission`, `/feedback`, `/rename`) run there and print their result; anything else reaches the model as text. |

Keys: Ctrl-C during a turn sends `session/cancel`, and the turn ends with `cancelled`. At the prompt, Ctrl-C clears the line, and a second press within two seconds quits. Lines typed while a turn runs are queued and run in order.

On exit the client prints `resume with: plexar-harness --resume <id>`. Sessions are stored by the harness at `%USERPROFILE%\.dsh\sessions\` and are never deleted by the client.

## What it draws

| ACP update | Terminal output |
|---|---|
| `agent_thought_chunk` | Dim italic text after `✻`, word-wrapped under a two-column gutter; one `✻ thinking…` line when collapsed |
| `agent_message_chunk` | Answer text after an orange `●`, word-wrapped to the window under a two-column gutter, rendered line by line: headings bold, inline `code` and code fences colored, `**bold**` |
| `tool_call` | `● <tool>(<main argument>)`, taken from `file_path`, `path`, `command`, `pattern`, `query`, `url`, `name` or `skill` |
| `tool_call_update` (completed or failed) | Up to four non-blank output lines under `⎿`, then `… +N lines`. A failed call is drawn in red. A completed `edit` or `write` instead shows `⎿ Updated <file> +A -R` (or `Created`) and a line diff of the file: the file's real line numbers, removed lines on red, added lines on green, two unchanged lines of context around each change, `⋮` between distant changes, and `… N more lines` after 16 rows (Ctrl+= / Alt+= shows it in full). The CLI reads the file when the call starts and again when it completes, so the diff covers the whole change even when an edit replaces text in several places. |
| `usage_update` | Kept for the turn footer |
| any other kind | Not drawn |

Each turn ends with a footer: `<used>/<size> ctx (<pct>%) · <seconds>s`, plus the stop reason when it is not `end_turn`.

Permission requests (`session/request_permission`) list the harness's options by number. Enter picks the first option. The chosen `optionId` is sent back, and an unknown number cancels the request.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Interactive session ended normally, or `-p` finished with `end_turn` |
| `1` | `-p` ended with any other stop reason, a bad flag, or the harness exited or failed to start (the last harness stderr lines are printed) |

## Updates

The client is a git checkout, so an update is a new commit on its branch. Every interactive launch asks `origin` for the branch tip in the background (`git ls-remote`, 5 s timeout) and never waits for it; `-p` never checks. When the tip is a commit the checkout does not contain, `Update available (<commit> on <branch>). Run: plexar-harness update` is printed as soon as the answer arrives, and under the header on later launches until the update is installed. `PLEXAR_HARNESS_UPDATE_CHECK=0` turns the check off. The check uses the user's own git credentials for `origin`; without access to the repository it finds nothing and says nothing.

`plexar-harness update` refuses a checkout with uncommitted changes to tracked files, then runs `git pull --ff-only`, `pnpm install` and the Plexar bundle build, and prints the old and new commit. It exits 1 if any step fails; the checkout is then at whatever commit the pull reached, and running `update` again repeats the remaining steps.

The desktop and Web app check `origin` when the Host starts and then every `checkIntervalMs` (one hour in the shipped profile) and show a notice above Settings in the sidebar only while an update is available, running, failed, or waiting for a restart. The app exposes the same steps to the Web client as the `plexarUpdate` Remote (`status`/`apply`/`restart`) instead of the terminal command. `restart()` exits the Host process with code 75; the Tauri shell respawns it and navigates the open window to its new URL, so a desktop update does not lose the window. `restart()` is refused outside the desktop app.

An installed copy (the Windows installer's runtime: no `.git`) has no `origin` to ask, so both the CLI notice and the `plexarUpdate` Remote instead poll the release manifest (`PLEXAR_RELEASE_MANIFEST`, default `https://downloads.plexar.tech/harness/latest.json`, the same feed the desktop app's Tauri updater already reads) and compare its `version` against the local `packages/bundle/plexar/package.json` version, bounded by the same 5 s timeout. Every failure (offline, non-200, invalid JSON, timeout) means no notice, never an error. The notice names the new version and, on the CLI, points at the desktop app or `https://harness.plexar.tech`; `plexar-harness update` and the Remote's `apply()` do not touch git or pnpm on an installed copy — they print or report that guidance instead and exit or resolve cleanly.

## Sign-in

`plexar-harness login` runs a PKCE (S256) authorization-code flow against the rig (`PLEXAR_RIG_URL`, default `https://llm.plexar.tech`; `07-studio-api-contract.md` §10p): it starts a one-shot loopback listener on `127.0.0.1:<OS-chosen port>/callback` (5-minute timeout), opens the rig's authorize page in the default browser, and on the matching callback exchanges the code for a key (`POST /api/harness/token`), storing it in the OS credential store (service "Plexar Harness", user "default" — the same entry the desktop app reads via its Rust keyring crate). It then calls `GET /api/harness/me` and prints `Signed in as <email>`, plus a reason line when the account is not entitled. `--no-browser` sets `redirect_uri=oob`, prints the authorize URL, and prompts for a pasted code instead of listening on a loopback port. `plexar-harness logout` calls `POST /api/harness/logout` (network errors are ignored) and deletes the stored key; signed in only via `PLEXAR_HARNESS_KEY`, it says that variable must be unset instead.

The gate (`checkGate()` in `auth.mjs`): `resolveKey()` reads the OS credential store first, falling back to `PLEXAR_HARNESS_KEY` only when the store holds no key. No key: "Not signed in. Run: plexar-harness login". `GET /me` 401: "Please sign in again: plexar-harness login". `entitled=false`: one of "Your Plexar access is paused." (`paused`), "Your Plexar access has been turned off. Ask the Plexar owner." (`grant_disabled`), or "Your account doesn't have Plexar Harness access yet. Ask the Plexar owner to enable it." (`product_not_granted` and any other reason). A network failure while reaching `/me` warns "Can't reach Plexar; starting offline." and starts anyway. On success the gate returns the key plus (when `/me` answered 200 with a `models` array) the chat-picker's model list and the full unfiltered one; the caller sets `PLEXAR_HARNESS_KEY` / `PLEXAR_HARNESS_MODELS` / `PLEXAR_HARNESS_ALL_MODELS` in this process's env, which spawned children inherit. Any `/v1/*` call answering `403 {error:{code:"product_not_granted"}}` mid-session means access was revoked: "Plexar Harness access was revoked. Ask the Plexar owner."

`-p` and `acp` run the gate before starting and exit 1 on any of the failure messages above, since neither can prompt; the desktop app launches `plexar-harness web` with the key already set, so the gate there is a cheap re-check against the same key, and `web` itself signs in first (below) only when the failure means "no valid key" and stdin is a terminal.

**Sign-in inside the harness.** The interactive client never exits on the gate: it starts the ACP host and the composer as usual, then checks the gate in place (`App#ensureSignedIn`, `tui/signin.mjs`'s `SignInState`). A failure that means no valid key or an unentitled key leaves the composer open with an in-TUI notice styled like other notices — "You're not signed in to Plexar. Press Enter to sign in in your browser, or type /login." for no key, or the `entitled=false` reason above for a key that just isn't entitled — and refuses submitted prompts with the same notice instead of sending them; `/help`, `/clear`, `/login` and `/logout` still work. Pressing Enter on the empty composer, or `/login`, runs the same loopback PKCE flow as `plexar-harness login` in place, showing "Waiting for you to sign in in your browser… (Esc to cancel)"; on success it stores the key, re-checks the gate, sets the three env vars above, and restarts the ACP host child so it inherits the key before resuming the open session, then shows "Signed in as `<email>`." and the composer stays open in the same session. `/logout` revokes the key server-side and deletes it locally, then returns to the signed-out state without quitting. A network failure while checking still only warns and starts offline, same as the blocking gate.

On success the gate also sets `PLEXAR_HARNESS_ALL_MODELS` to the full, unfiltered `/me` `models` array (chat and classifier, serving and not) whenever `/me` answered 200 with one; the `plexarModels` Host Remote parses it once at Host load for the Models settings page, which lists the signed-in person's chat models and classifiers with a serving pill, so a person can see why a model is missing from the composer's picker instead of only the narrower serving-chat list that feeds it.

## Desktop sign-in

The desktop app resolves a key from the Windows Credential Manager (service "Plexar Harness", user "default" — the same entry the CLI reads and writes) before starting the Host, falling back to the `PLEXAR_HARNESS_KEY` env var for developers; a stored or env key is checked against `<rig>/api/harness/me` first. With no key, the loading page shows a sign-in card ("Sign in with Google") instead of the spinner. A 401 from `/api/harness/me` deletes the stored key and shows the card with "Please sign in again."; a 200 with `entitled: false` shows the card with the rig's reason (paused, disabled, or no product), leaving the stored key in place; any other outcome (network failure, or the route not yet deployed — 404, 5xx, non-JSON) starts the Host anyway (offline tolerance).

Sign-in itself is desktop OAuth with PKCE: the app opens the system browser to `<rig>/api/harness/authorize` with a `code_challenge` and a `state` bound to a one-shot loopback listener on `127.0.0.1:<OS-chosen port>`; the rig does Google sign-in and redirects the browser to that listener's `/callback`, which the app matches to its `state` and answers with a small confirmation page. A returned code is exchanged at `<rig>/api/harness/token` for a key, stored in the Credential Manager and started with the Host in that child process's own env, never the app's process env; the exit-75 restart path reuses the same key. A Cancel control aborts an in-flight wait and frees the port. Signing out calls `<rig>/api/harness/logout` (best-effort) before deleting the stored key. The plaintext key never appears in logs, the window title, or URLs.

## Tools beyond the base set

- **Browser (Playwright):** the bundle mounts `dsh-browser-use` with the Playwright MCP provider in `launch` mode. Each session gets its own Chromium window, visible so people can watch what the agent does, and the model sees the `mcp__playwright-mcp__browser_*` tools (navigate, snapshot, click, type, fill_form, take_screenshot, console_messages, network_requests, …). One-time setup per machine: `npx @playwright/mcp install-browser chrome-for-testing`, run in `packages/experimental/browser-use-playwright-mcp`. `PLEXAR_BROWSER_HEADLESS=1` hides the window (for unattended runs). Page snapshots and console logs are written under `.playwright-mcp\` in the workspace.
- **Use my Chrome:** with the Plexar Browser Bridge extension installed in Chrome or Edge, the agent works in the person's own browser, with their logins, in its own tab: the extension connects without a prompt, and that tab joins a "Plexar" tab group. The person's other tabs are not shared unless they drag one into that group. Chrome shows a bar while a tab is being controlled. It is on by default; Settings > Features > Use my Chrome turns it off. Without the extension (detected from the browser's profile settings), the session uses its own window straight away and the person sees one line: "Install Plexar Browser Bridge from plexar.tech/harness/browser to let the agent use your Chrome."
- **Bash on Windows (primary shell; `PLEXAR_WIN_BASH=0` turns it off):** mounts a Git Bash executor (`@plexar/dsh-plexar/git-bash`) and the `bash` tool beside `pwsh`, each with its own `shell` service, and the system prompt tells the model to use `bash` for shell work and `pwsh` only for Windows-specific tasks. Git Bash is found under `Program Files\Git\bin\bash.exe`, or taken from `PLEXAR_BASH_PATH`; the WSL launcher `System32\bash.exe` is never used. Commands run unconfined and follow "Permission modes" above.
- **Document tools (`mcp__plexar-doc__*`):** an MCP stdio server, `python -m plexar_tools.harness_mcp` from `python/tools`, gives the model `read_file`, `find_in_file`, `query_sheet`, `convert_document`, `extract_document` and `create_document` by file path instead of inline bytes. Every `path` (and every `sources` entry `create_document` takes) must resolve inside the session workspace; a path outside it, or a file that does not exist, is refused. `PLEXAR_PYTHON` selects the interpreter (default `python` on Windows, `python3` elsewhere, found on PATH); Python 3.12+ is required. Without a usable Python, Harness still starts — it just does not offer these six tools. There is no Settings > Features switch for them yet (Features toggles by package, and all MCP servers share one), so turning them off alone means disabling the `plexar-document-tools` row in the profile's patch; in the Web UI and desktop app the allowed folder is the host's starting folder rather than each session's. Limitations are listed in the bundle README.

## Tests

- `node packages/bundle/plexar/cli/tests/tui.test.mjs`: keyless. A small VT emulator replays the composer and select output at 60 columns and checks one frame stays on screen, rows fit the window, and the prompt markers.
- `node --test packages/bundle/plexar/cli/tests/pkce.test.mjs packages/bundle/plexar/cli/tests/gate.test.mjs packages/bundle/plexar/cli/tests/credentials.test.mjs packages/bundle/plexar/cli/tests/signin.test.mjs`: keyless. PKCE (RFC 7636 Appendix B vector), state-mismatch rejection, callback parsing, entitlement-gate decisions against a local mock `/me` server, the credentials module with `@napi-rs/keyring`'s `Entry` mocked, and the in-TUI signed-out state machine with login/checkGate/host-restart injected as fakes.
- `python packages/bundle/plexar/cli/tests/live_gate.py`: needs the rig and `PLEXAR_HARNESS_KEY`. 24 end-to-end checks through the real harness.
- QA master and pass ledger: [`qa/QA_PLAN.md`](qa/QA_PLAN.md), [`qa/QA_PASSED.md`](qa/QA_PASSED.md).

## Limits

- No session titles: ACP does not carry them (`07-studio-api-contract.md`, "Cannot / does not"). `/sessions` shows ids.
- Skills have no typed commands yet (`/orch-code-anth` reaches the model as text, which loads the skill); work item 3.
- Answer markdown is drawn line by line as it streams. Tables and lists print as their source text.
