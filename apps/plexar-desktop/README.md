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

## Installer

`powershell -File build.ps1` builds the Windows installer with a bundled Node and runtime, signs it for the updater and writes `latest.json`; [`INSTALLER.md`](INSTALLER.md) covers the layout, first-run profile setup, PATH, and publishing.

## Known limits

- Built with `cargo build` from a checkout, the app uses the checkout's `packages/bundle/plexar` and the `node` on `PATH`; only an installer build ships its own runtime and checks for updates.
- The installer is not Authenticode-signed, so SmartScreen warns on first run.
- The window loads the Host over loopback HTTP; there is no custom protocol like the Electron shell's `dsh-app://`.
