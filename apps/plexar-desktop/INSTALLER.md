# Windows installer with bundled Node and auto-update

`apps/plexar-desktop/build.ps1` produces a per-user NSIS installer, `PlexarHarness_<version>_x64-setup.exe`, that a person can download and run with no git, no pnpm and no Node pre-installed. The installed app keeps itself current through the Tauri updater.

## Build

`powershell -File apps/plexar-desktop/build.ps1` runs, in order:

1. `pnpm run build`.
2. Downloads the pinned win-x64 Node (`$NodeVersion` in `build.ps1`, the engines minimum `v22.19.0`) from nodejs.org into `%TEMP%\plexar-harness-node\` and fails unless its SHA-256 matches nodejs.org's `SHASUMS256.txt`.
3. `scripts/plexar-release/stage-windows-bundle.mjs --node-exe <node.exe>` stages the runtime into `src-tauri/plexar-runtime/` (git-ignored).
4. `tauri build` (`@tauri-apps/cli` pinned in `build.ps1`, run through `npx`) packages it as an NSIS installer.
5. Copies the installer to `src-tauri/target/release/bundle/release/PlexarHarness_<version>_x64-setup.exe`, signs it with `tauri signer sign` (`.sig` beside it), writes `src-tauri/target/release/bundle/latest.json` through `scripts/plexar-release/updater-manifest.ts`, and prints the installer's size and SHA-256.

The installer version is `packages/bundle/plexar/package.json`'s `version`; `build.ps1` rewrites `tauri.conf.json`'s `version` to match before building.

## What ships

`bundle.resources` installs `plexar-runtime\` next to `plexar-desktop.exe`:

```
%LOCALAPPDATA%\Plexar Harness\
  plexar-desktop.exe
  uninstall.exe
  plexar-runtime\
    node\node.exe                       pinned Node
    bin\plexar-harness.cmd              PATH shim: bundled node.exe + bundled CLI
    harness\                            repo-relative layout, so harnessRoot() needs no special case
      apps\cli\{lib,package.json}       the built dsh CLI, run under plain Node (no tsx, no sources)
      node_modules\...                  flat production dependencies, real files, no links
      packages\bundle\plexar\{lib,cli,profiles,skills,cordis.patch.yml,package.json}
      packages\client\ui-brand-plexar, packages\client\ui-settings-plexar,
      packages\experimental\voice-input-bundle     the other link: plugins of plexar-web
      python\tools\{src,pyproject.toml}  the document-tools server (needs a system Python)
```

`node_modules` is the merge (first wins) of `pnpm deploy --legacy --prod` with the hoisted linker for the CLI and each `link:` plugin, plus further deploy rounds for workspace peers a deploy leaves out, until every staged package's dependencies and required peers resolve. Links left inside copied packages are removed, because an NSIS installer cannot carry them; source maps, `.tsbuildinfo` and type declarations are pruned.

The CLI (`cli/acp.mjs` `dshEntry`) runs `apps/cli/src/bin.ts` under tsx when that source exists (a checkout) and `apps/cli/lib/bin.js` under plain Node otherwise (installed). `plexar-harness export` still needs a checkout, because `export.ts` runs under tsx.

## Profiles and PATH

A checkout creates profiles with `profiles/install.ps1`, which needs pnpm. An installed copy uses `cli/setup.mjs` instead, which needs neither pnpm nor the network: it creates each missing profile with the built `dsh --dump-default-config`, points its `link:` dependencies at the installed packages with directory junctions, adds bundles that declare `dsh.bundle.patch`, and copies the shipped patches under the same rules as `install.ps1`.

- The installer's `NSIS_HOOK_POSTINSTALL` (`src-tauri/windows/hooks.nsh`) runs `setup.mjs install`, which also appends `plexar-runtime\bin` to the user `PATH`; `NSIS_HOOK_PREUNINSTALL` runs `setup.mjs uninstall`, which removes it. Profiles and sessions under `%USERPROFILE%\.dsh` stay after uninstall.
- Every launch of an installed `plexar-desktop.exe` runs `setup.mjs profiles` before the Host starts, and `plexar-harness acp`/`web` run it when their profile is missing.
- Like `install.ps1`, setup re-points existing Plexar profiles at the copy that ran it: on a machine that also has a checkout, installing moves `~/.dsh/profiles/plexar*` to the installed runtime until `install.ps1` runs again.

## How the Host is launched

`harness_root()` in `main.rs` is `PLEXAR_HARNESS_ROOT`, else `resource_dir()/plexar-runtime/harness` when it exists (installed), else the checkout the exe was built from. The Node executable is `resource_dir()/plexar-runtime/node/node.exe` when present, else `node` on `PATH`.

## Updates

`tauri-plugin-updater` checks `https://downloads.plexar.tech/harness/latest.json` once per launch of an installed copy (dev builds never check). Any failure, including a missing `latest.json`, is written to stderr and otherwise ignored. When a newer release is listed, a dialog asks "Restart now" or "Later"; on yes the app downloads the installer, which the plugin verifies against `plugins.updater.pubkey`, stops the Host, and hands over to the NSIS installer in passive mode, which relaunches the app.

The updater keypair lives only in `<signing-dir>\` (`updater.key`, `updater.key.password`, `updater.key.pub`), outside every repository; `tauri.conf.json` holds only the public key. Losing the private key means installed copies can never auto-update again.

Publishing a release means uploading two files from `src-tauri/target/release/bundle/`:

| File | URL |
| --- | --- |
| `release/PlexarHarness_<version>_x64-setup.exe` | `https://downloads.plexar.tech/harness/windows/PlexarHarness_<version>_x64-setup.exe` |
| `latest.json` | `https://downloads.plexar.tech/harness/latest.json` |

## Code signing

The installer and `plexar-desktop.exe` are not Authenticode-signed, the same as Plexar Emails. Windows SmartScreen shows "Windows protected your PC" on first run; the person chooses More info, then Run anyway.
