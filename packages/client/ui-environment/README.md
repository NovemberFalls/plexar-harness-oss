---
description: "Environment rail for the dsh web client: a collapsible column right of the right Sidebar showing the current Session's workspace, git branch, context use, and background tasks."
kind: "package-reference"
---

# @deepseek-ai/dsh-client-ui-environment

English | [中文](README.zh.md)

## Summary

The **Environment** button in the conversation header opens a 280px rail at the far right of the window, to the right of the right Sidebar. The rail shows facts about the current Session: its workspace name and folder, the folder's git branch, how much of the context window is used, and the Session's running background tasks with a count of finished ones. The choice to show or hide the rail is remembered per browser.

## Table of Contents

- [Use this package](#use-this-package)
- [Understand the implementation](#understand-the-implementation)
- [Further Exploration](#further-exploration)
- [Model Experience](#model-experience)
- [Known Limitations and Deferred Work](#known-limitations-and-deferred-work)
- [Dev Note](#dev-note)

-----

<a id="use-this-package"></a>
## Use this package

Press **Environment** in the conversation header to show or hide the rail; the close button in the rail's title row hides it too. Sections, top to bottom: **Workspace** (always shown; the folder path loses its middle when long and shows in full on hover), **Branch**, **Context** and **Background tasks**, each hidden while it has nothing to show. With no Session selected the rail shows one line instead. On a window too narrow to keep the conversation at its minimum width beside the rail, the rail steps aside without forgetting that it was asked for, and it also steps aside while the right Sidebar is fullscreen.

-----

<a id="understand-the-implementation"></a>
## Understand the implementation

<details>
<summary>Implementation internals — click to expand</summary>

The browser half occupies the frame's `envbar` slot (declared by `ui-layout`, which gives it a real grid track right of the `rightbar` column only while it is occupied) with the rail, whose body is the `session-maybe` child `envbar.session`. The header toggle registers into `conversation.session.header.actions` and calls `ctx.layout.toggleEnvbar()`; the shown state is mirrored in a local snapshot (the toggle's `aria-pressed`) and in `localStorage` under `plexar.envbar.shown` (`'1'`/`'0'`, every access in try/catch, absent means hidden), which is applied on start. Workspace rows come from the optional `workspaces` service, background tasks from the optional `jobs` service (the roster is watched only while the rail is shown), and context use from the `contextPressure` projection through token-meter's `contextOccupancy`, the same fold the composer's meter uses.

The Host half is a `TypertRemoteService` mounted as `ctx.remote.environmentRail`. Its one method, `branch(sessionId)`, finds the Session's workspace in the Host's own `workspaceRegistry` (the caller never supplies a path), runs `git rev-parse --abbrev-ref HEAD` there through `execFile` (no shell, 2 s timeout, hidden window), and returns `{ branch }`, null on any error, outside a repository, or on a detached HEAD. The rail asks when the Session changes and every 30 s while it is shown, never while hidden.

</details>

-----

<a id="further-exploration"></a>
## Further Exploration

- [ui-layout](../ui-layout/README.md) — the frame, its `envbar` track, and `ctx.layout`.
- [ui-jobs](../ui-jobs/README.md) — the header job list over the same `jobs` service.
- [ui-workspace](../ui-workspace/README.md) — the workspace browser over the same `workspaces` service.
- [token-meter](../../llm/token-meter/README.md) — the `contextPressure` projection and its occupancy fold.

-----

<a id="model-experience"></a>
## Model Experience

None, as the package is a browser-side surface with a Host read for the UI; it registers no model surface.

#### KV Cache effect

None; this package neither assembles nor sends a provider request.

## Known Limitations and Deferred Work

<a id="known-limitations-and-deferred-work"></a>

- **No change summary or outputs** — the latest turn's change summary and presented deliverables are not held by a shared client store for the current Session, so the rail leaves those sections out rather than building a new Host aggregate.
- **Branch refresh is a timer** — the rail re-reads the branch every 30 s while shown instead of after each turn.
- **Runtime invariant:** No companion is published. The rail holds no owned relationship of its own: the remembered choice is a browser preference, and everything it shows derives from other services.

<a id="dev-note"></a>
### Dev Note

<details>
<summary>Working context for maintainers — click to expand</summary>

None.

</details>
