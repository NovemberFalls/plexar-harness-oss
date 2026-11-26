# Plexar Harness desktop

A Tauri window around the Plexar Web UI. It shows a local loading page, starts `plexar-harness web --no-open --port 0` as a child process, reads the `dsh web: <url>` line the Host prints, and navigates to that URL; the one-time token in it signs the window in. Closing the window stops the Host and every process it started (`taskkill /T` on Windows).

When the Host exits before printing a URL, the loading page shows the harness error line with a fix: a missing `PLEXAR_HARNESS_KEY` (exit 11), a missing `plexar-web` profile (12), or Node older than 22.19 (10).

## Build and run

Requirements: Rust (stable), the WebView2 runtime (Windows 10/11 ship it), Node 22.19+ on `PATH`, and a harness checkout with `pnpm install`, `pnpm run build` and `profiles/install.ps1` done.

```
cd apps/plexar-desktop/src-tauri
cargo build            # debug build: target/debug/plexar-desktop.exe
cargo build --release  # release build, no console window
```

The checkout the app runs is `PLEXAR_HARNESS_ROOT`, else the checkout it was built from. Sessions start in the user's home folder; the Web UI's workspace picker chooses the project.

The debug exe uses a staged runtime under `target/debug/plexar-runtime` when it exists. To run the checkout's code instead, set `PLEXAR_HARNESS_ROOT` to the checkout.

## Installer

`powershell -File build.ps1` builds the Windows installer with a bundled Node and runtime, signs it for the updater and writes `latest.json`; [`INSTALLER.md`](INSTALLER.md) covers the layout, first-run profile setup, PATH, and publishing.

## In-app browser

The right-Sidebar **Browser** tab runs in a native pane in this window instead of an iframe. A pane is a child WebView2 webview of the `main` window, painted above the Web UI over the tab's content box, with back, forward, reload and the address bar driven from the Web UI (`ui-sidebar-browser`). The agent's Playwright browser tools can drive the same panes (the Host's third browser route, see `packages/bundle/plexar/README.md`); the person sees what the agent does and can take over a pane. The feature is Windows only; elsewhere the Browser tab keeps the iframe.

- **Profile.** All panes share one data directory, `<app_local_data_dir>/browser-profile`, separate from the main webview's. Sign-ins made in a pane persist across restarts. Panes are never scoped per Session.
- **CDP port.** At start the shell picks one free loopback TCP port and opens the panes with `--remote-debugging-port=<port> --remote-debugging-address=127.0.0.1`. It sets `PLEXAR_INAPP_BROWSER_CDP=http://127.0.0.1:<port>` on the Host child (Windows only); the Host never guesses a port. Because the panes' data directory differs from the main webview's, WebView2 runs them in their own browser process, so the port exposes the panes and nothing of the Web UI, whose URL carries the sign-in token. The port is loopback only and **unauthenticated**: while a pane is open, any local process of the same user can attach to it and read or drive every pane, and the profile's cookies.
- **Host to shell.** The Host writes `plexar shell: <json>` lines on its stdout: `browser.ensure` makes an agent pane for a session id, `browser.release` closes it unless the person adopted it. Other lines, malformed JSON, unknown ops and ids that are empty or over 128 characters are ignored without logging their content. Lines are handled for the whole life of the Host child, before and after the window navigates.
- **IPC the Web UI now has.** The Web UI is a remote `http://127.0.0.1:*` origin and used to have no Tauri API. `capabilities/webui.json` now grants the `main` webview, on that origin only (`"local": false`), `core:event:allow-listen`, `core:event:allow-unlisten` and the seven `browser_pane_*` commands (open, adopt, navigate, command, set_bounds, close, list). Nothing else: no window, webview, shell, fs, dialog or updater permission. `build.rs` declares all thirteen app commands, so the six existing ones (`host_status`, sign-in and sign-out) are now behind an ACL and only `capabilities/default.json` (the local loading page) allows them. Both capability files are scoped with `"webviews": ["main"]`, so a pane never matches either. Each pane command also fails unless the calling webview is `main` and its current page is on the Host's origin (the capability itself admits any loopback page). Panes themselves get no IPC, no initialization script and no preload.
- **URL policy.** Open, navigate, popups and in-pane navigation allow only `http` or `https` URLs with a host and no username or password, and never the Host Web UI's origin. It also refuses any host ending in `.localhost` (Tauri's own local origins on Windows; plain `localhost` is allowed) and any loopback host (`localhost`, `127.0.0.0/8`, `[::1]`) on the Host's port. `about:blank` is allowed only as a pane's initial document. A popup never opens a window: an allowed URL is sent to the Web UI as an open request (a new Browser tab), others are dropped. Downloads are denied.
- **Lifetimes.** The panes close when the Host child exits (including the code-75 restart). When the Web UI reloads, panes without a session are closed; panes with a session (agent panes, adopted or not) are hidden, go back to owner `agent` and are kept, since a Session may still be driving them. `browser.ensure` is ignored once 8 live panes with a session exist. A pane whose first navigation fails in `browser_pane_open` is closed.

Known limits:

- A dev site served on a `<name>.localhost` host, or on loopback at the Host's own port, does not load in a pane.
- A pane paints above everything in the Web UI, so Web UI menus and dialogs that overlap the Browser tab's area are covered by it.
- The agent cannot open a new tab itself in this route (WebView2 has no `Target.createTarget`); it works in the panes that exist, and each new pane comes from the shell.
- Every Session's agent sees every in-app pane: one shared profile and no per-Session scoping, unlike the extension relay.
- The debugging port is unauthenticated, as above.
- Windows only.
- Tested by unit tests (URL policy, shell-line parser, browser arguments) and a successful `cargo build`; the live window behaviour (placement, history, popups, the Host attaching to a real pane) has not been exercised by an automated test.

## Known limits

- Built with `cargo build` from a checkout, the app uses the checkout's `packages/bundle/plexar` and the `node` on `PATH`; only an installer build ships its own runtime and checks for updates.
- The installer is not Authenticode-signed, so SmartScreen warns on first run.
- The window loads the Host over loopback HTTP; there is no custom protocol like the Electron shell's `dsh-app://`.
