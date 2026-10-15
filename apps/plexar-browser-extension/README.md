# Plexar Browser Bridge

A Chrome/Edge MV3 extension that lets Plexar Harness work in your own
Chrome — your tabs, your signed-in sessions — instead of only a browser
Chromium instance it launches itself. Each harness process gets one colored "Plexar · <directory>" tab group;
its Sessions work in tabs of that group, plus any tab you drag into it. Connected tabs show a green checkmark badge.
When the harness process exits or is killed, the tabs the agent opened close and the tabs you dragged in leave the
group and stay open. A connect page whose harness has gone closes itself.

This is a fork of the Playwright MCP Bridge Chrome extension
(`microsoft/playwright`, commit `b9a34ac7783a1b6c2e1dfff0c08ac744c048fa59`,
`packages/extension`). See [NOTICE](./NOTICE) for the full list of changes
and [LICENSE](./LICENSE) for the upstream Apache-2.0 terms. The
relay-facing wire protocol (the connect page's `mcpRelayUrl`, `client`,
`protocolVersion`, and `token` URL parameters, and the `chrome.*`
command/event allow-lists the background service worker forwards) is
unchanged, so this extension stays compatible with the harness-side relay
under `packages/bundle/plexar/src/browser-bridge/`.

## Load unpacked (for testers)

1. `pnpm install` at the repo root (once), then from this directory:
   ```sh
   pnpm build
   ```
   This writes a load-unpacked-ready extension to `dist/`.
2. In Chrome or Edge, open `chrome://extensions` (or `edge://extensions`).
3. Turn on **Developer mode** (top-right toggle).
4. Click **Load unpacked** and select this package's `dist/` directory.
5. The extension loads with the pinned developer id
   `cnfgenfphpnhddlefhminclbbjdgkbbd` (see "The pinned developer key"
   below) — Plexar Harness's browser-bridge feature toggle targets this id
   when it opens the connect page.

Re-run `pnpm build` after any source change, then click the refresh icon
for the extension on `chrome://extensions`.

## Pack for the Chrome Web Store

```sh
pnpm build
pnpm pack
```

`pnpm pack` reads the already-built `dist/manifest.json` for the version
and writes `dist/plexar-browser-bridge-<version>.zip`, the artifact the
Chrome Web Store developer dashboard accepts for upload.

## The pinned developer key

`manifest.json`'s `"key"` field is this fork's own RSA public key,
pinned so that `chrome://extensions` "Load unpacked" always assigns the
same 32-character extension id
(`cnfgenfphpnhddlefhminclbbjdgkbbd`, derived as the first 32 hex nibbles
of `sha256(der-decoded key)`, each nibble mapped `0`-`f` to `a`-`p`) across
every tester's machine and CI run. `tests/manifest.test.mjs` checks this
derivation against the built manifest.

**The Chrome Web Store assigns its own key and id on first upload.** Once
this extension is uploaded to the Web Store for the first time, replace
the pinned `"key"` in `manifest.json` with the store-assigned key (or
remove the field entirely and let the store manage it) — do not keep
shipping the load-unpacked developer key in the published listing.

## Build tooling

- `pnpm build` — `scripts/build.mjs` bundles the background service worker
  and the connect/status UI pages with esbuild, then copies
  `manifest.json` and `icons/` into `dist/`.
- `pnpm pack` — `scripts/pack.mjs` zips the built `dist/` directory using a
  small dependency-free ZIP writer (`scripts/zip.mjs`).
- `pnpm icons` — `scripts/make-icons.mjs` resizes
  `apps/plexar-desktop/ui/mark.png` to the four MV3 icon sizes via `sharp`
  and writes them to `icons/`. The generated PNGs are committed, so this
  only needs re-running if `mark.png` changes.
- `pnpm typecheck` — runs `tsc` against the background/service-worker
  source and the React UI source separately (they target different
  `lib`/JSX configurations, matching upstream's split).

No new dependency was added beyond `@types/chrome` (chrome.* API types for
`tsc`, not shipped in the built extension); everything else reuses
`esbuild`, `sharp`, `react`, and `typescript` already vendored in this
monorepo's toolchain.

## Tests

```sh
pnpm build
node --test
```

`tests/manifest.test.mjs` loads the built `dist/manifest.json` and checks
its name, version, permissions, the pinned key, and that the key derives
the pinned extension id.
