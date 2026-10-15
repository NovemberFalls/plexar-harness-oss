---
description: "Plexar brand occupants for the Web client's sidebar slots: the shared --px-* token sheet, accent palette, glassmorphism, and aurora background."
kind: "package-reference"
---

# @plexar/dsh-client-ui-brand

## Summary

`dsh-client-ui-brand` fills the sidebar and blank-session hero brand slots with the Plexar mark
and name, and layers three browser-injected stylesheets over the design platform's own tokens: an
accent palette (the `--dsw-static-deepseek-*` scale in Plexar orange), a glassmorphism sheet
(translucent sidebar/menu/dialog/toast surfaces and a dark-theme base background), and a slow
aurora background that shows only on the blank-session empty/loading screen, and that the viewer
can also switch off from Settings > Features. The package also carries a
byte-for-byte copy of the shared Plexar `--px-*` design tokens (`src/client/tokens/`) and derives
every other brand color in this package from them.

## Table of Contents

- [Use this package](#use-this-package)
- [Understand the implementation](#understand-the-implementation)
- [Model Experience](#model-experience)
- [Known Limitations and Deferred Work](#known-limitations-and-deferred-work)

-----

<a id="use-this-package"></a>
## Use this package

Compose this plugin into a Web client build (`dsh.client.inject`: `dsh-client-ui-renderer`,
`dsh-client-ui-sidebar`) to apply the Plexar brand. It has no configuration; the aurora on/off
choice is a per-viewer `localStorage` preference exposed as `ctx.plexarAurora` for the Settings
row that reads and sets it.

<a id="understand-the-implementation"></a>
## Understand the implementation

`apply()` registers four `ctx.effect()`s, in order: the token sheet, the accent palette, the
glassmorphism sheet, and the aurora layer — the token sheet installs first so every later sheet
can read `var(--px-*)`.

### Shared tokens (`src/client/tokens/`)

`plexar-tokens.css`, `plexar-tokens.json` (unused here), and `fonts/montserrat-medium.woff2` are
copied unmodified from `plexar-coord/brand/tokens/` (commit `33fa228`; see `SOURCE.md`). **Never
edit the copy** — re-copy from that path to pick up a token update, and re-run
`scripts/generate-font.ts` to refresh the generated `font.ts` font data. Everything else in this
package maps its own variables onto `--px-*` rather than hardcoding brand colors, per the shared
tokens' own README: a token update is a re-copy, not a re-theme. Per-product customisation
overrides `--px-*` at runtime (a scoped stylesheet or class) rather than forking the pinned values,
and nothing outside `src/client/tokens/` may redeclare a `--px-*` value.

`src/client/tokens/index.ts` loads the copied sheet through the client bundler's `?inline` loader
(compiled CSS text) and substitutes the `@font-face` rule's relative `url('fonts/...')` — which
would 404 once the sheet is injected into the Host page — with a `data:` URL embedding the font,
generated ahead of time into `font.ts` by `scripts/generate-font.ts`. The CSS file itself is never
rewritten; the substitution happens only in the injected text.

### Accent, glass, and aurora (`palette.ts`, `aurora.ts`, `Brand.tsx`)

The aurora layer cross-fades in over ~600ms only while the viewer's switch is on AND at least one
blank-session hero occupant (`PlexarHeroMark` / `PlexarHeroHeadline`, which render only when a
session has no conversation yet) is mounted, tracked by a module-scoped mount counter in
`aurora.ts` that the hero components' own effects increment and decrement; it never shows behind
an open conversation or terminal output. The `--dsw-static-deepseek-*` accent scale is derived
from `var(--px-accent)` with `color-mix` toward white (lighter steps) or black (darker steps).
The glassmorphism sheet's dark-theme surface
fills derive from `var(--px-bg)` / `var(--px-bg-2)` / `var(--px-surface)` / `var(--px-elev)` with
`color-mix` transparency, and its dark-theme `--dsw-alias-bg-base` maps to `var(--px-bg)`; the
light-theme fills stay literal near-white `rgba` (the shared tokens are a dark design with no
light-theme surface values to map onto). Both themes' soft orange background glow, the aurora's
orange ribbon stops, and the sidebar/hero brand name gradient all derive from `var(--px-accent)`
and `var(--px-accent-soft)`; the aurora's decorative teal and violet ribbon stops have no brand-token
equivalent and stay literal. The brand name and hero headline use `var(--px-font-display)`.

<a id="model-experience"></a>
## Model Experience

This package renders sidebar and hero brand slots and injects stylesheets; it contributes no
model-visible tokens, tool schemas, or session log entries.

<a id="known-limitations-and-deferred-work"></a>
## Known Limitations and Deferred Work

None beyond the token re-copy step above.
