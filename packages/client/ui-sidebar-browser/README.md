---
description: "Right-Sidebar browser tabs for sandboxed HTTP(S) pages, including loopback services."
kind: "package-reference"
---

# @deepseek-ai/dsh-client-ui-sidebar-browser

English | [中文](README.zh.md)

## Summary

Browse HTTP(S) pages, including loopback services, inside independent right-Sidebar tabs. Web uses an iframe with application-managed history; Desktop uses Electron `<webview>` with native navigation history and retained pages; the Plexar desktop app (Tauri) uses a native pane, an OS-level browser view placed over the tab. The package never injects Electron or Node access into visited content.

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

Browser is disabled by default in Web profiles and enabled on Desktop. Enable the shipped entry through the Web profile patch to use it. Open **Browser** from the right-Sidebar guide and enter an HTTP(S) URL. Chat HTTP(S) links open here when the [link preference](../ui-chat/README.md) selects **In-App Sidebar**. A host name without a scheme becomes HTTPS. Public and loopback targets use the same default sandbox. Each guide action or delegated message-link activation creates another Browser tab.

### When to choose it

Choose Browser for a Web page that should remain beside the current Session. Choose [Document Preview](../ui-sidebar-documentpreview/README.md) for local files, and use the explicit external-browser action when a site refuses iframe embedding or needs browser capabilities this package withholds.

### Minimal configuration

The package has no plugin configuration. A Web profile enables the shipped entry through its profile patch:

```yaml
- id: ui-sidebar-browser
  disabled: false
```

Client plugins can open a tab through `ctx.sidebarRight.openTab('browser', { params: { url } })`. The optional URL passes the same validation as address-bar input before navigation. Under the Tauri shell a tab can instead be opened with `params: { pane }`, which adopts an existing agent pane (`browser_pane_adopt`); if the pane is gone, the tab behaves as if opened with neither parameter.

The toolbar provides Back, Forward, Reload, Go, and Open in system browser. Web also offers a per-tab sandbox toggle; disabling it is temporary and displays a warning. Desktop and the Tauri native pane show the observed page title. After a restart, Browser shows the saved title and URL; Restore or Reload opens that address only when requested.

-----

<a id="understand-the-implementation"></a>
## Understand the implementation

<details>
<summary>Implementation internals — click to expand</summary>

### Protocol policy

The address parser accepts HTTP and HTTPS, including loopback targets. It rejects `file:` URLs, script/data/blob input, embedded credentials, the DSH application origin, and malformed addresses. Document Preview owns local-file rendering.

### Iframe carrier

Web uses `sandbox="allow-scripts allow-forms allow-same-origin allow-popups allow-popups-to-escape-sandbox"` by default. The frame has no direct download or top-navigation flag. Popups leave the sandbox; in Web, an escaped popup retains its opener and can navigate the top-level application. The visited origin can use its own cookies and Web storage but a cross-origin target cannot read DSH DOM, storage, or API responses. The iframe sends no referrer and adds no package-owned Permissions Policy, so browser defaults and user grants apply. The toolbar can remove the sandbox for the current tab occurrence; the choice is not persisted. An unsandboxed page can navigate the top-level application under browser activation rules and use downloads, modal dialogs, and input locks. The package does not proxy or probe remote pages.

Web records toolbar submissions and typed tab opens. A navigation state machine treats the first iframe load for each controlled revision as known and a later load as proof that the page changed to an unreadable URL. In that unknown state the address is marked, Back, Forward, and external-open are disabled, and Reload returns to the last controlled URL. A remounted body reloads the latest application-known URL and uses its optional initial URL only before the first controlled target. History API and fragment changes that emit no iframe load remain invisible. An iframe `error` event displays a transient load-failure notice until the next controlled load without changing URL history.

### Native pane carrier

When `globalThis.__TAURI__` exposes `core.invoke` and `event.listen` (the Plexar desktop app, which sets `withGlobalTauri`), `apply` picks the native carrier, after Electron and before the iframe. The pane is a WebView2 child webview of the main window, owned by the shell (`apps/plexar-desktop`); the package reaches it only through `src/client/native/bridge.ts`, which wraps the `browser_pane_*` commands and `plexar-browser:*` events. `NativePaneImpl` is the `BrowserFrame`: it opens or adopts a pane when attached and asked to load, maps pane state (URL, title, loading, history) to frame state, treats Chromium `ERR_ABORTED` as no error, forwards `open-requested` popups to the Sidebar as new tabs, and drops a pane the shell closed, keeping the last address so a later attach or reload opens a fresh pane. `NativePanePresentation` is a `BrowserPresentation`; because the pane is not in the DOM it tracks the content element (`ResizeObserver`, `IntersectionObserver`, window `resize` and capturing `scroll`), sends logical-pixel bounds at most once per animation frame and only when changed, and sends `visible: false` when the element is hidden, detached or off-screen, on unmount and on dispose. The shell enforces the URL policy, so the pane never loads `file:`, credentials or the Web UI's own origin. The native tab declares `keepMounted`. At startup, and on `plexar-browser:agent-opened`, the package opens a Browser tab with `params: { pane }` for each agent-owned pane it has not offered, in the Session the Sidebar is showing.

### Controller

Each tab's `BrowserController` owns address validation, commands and explicit restoration. `BrowserFrame` supplies carrier-neutral navigation state; `IframeImpl` uses `BrowserNavigation`, while `ElectronWebViewImpl` observes Chromium history; `NativePaneImpl` reports the shell's pane state. `BrowserPresentation` owns physical DOM attachment. Slot injection supplies `useBrowserState` and plain callbacks, keeping provider objects and observables out of the React body.

Desktop's main process approves guest leases and enforces attachment, navigation and permission policy. Preload exposes only scoped Browser operations. Shared declarations use the standard `/types` export with `import type`; the Host and Client compile through separate tsconfig files. Desktop Browser tabs declare `keepMounted`, so Sidebar preserves their DOM across tab changes, Session switches, collapse and floating.

</details>

-----

<a id="further-exploration"></a>
## Further Exploration

- [Right Sidebar](../../../docs/subsystems/sidebar-right.md) — tab composition, navigation, and lifecycle.
- [Document Preview](../ui-sidebar-documentpreview/README.md) — local source, Markdown, images, HTML, and PDF rendering.
- [Sidebar Browser decision](../../../.agents/notes/implemented/feature/2026-09-16-sidebar-browser.md) — iframe behavior and controller ownership.
- [Desktop Browser decision](../../../.agents/notes/implemented/feature/2026-09-20-desktop-browser-webview.md) — webview leases, CWD storage grouping and manual restoration.

-----

<a id="model-experience"></a>
## Model Experience

None, as Browser tabs are user-facing presentation state and register no tool, prompt section, or Session event.

#### KV Cache effect

None; browsing does not enter a model request.

## Known Limitations and Deferred Work

<a id="known-limitations-and-deferred-work"></a>

The isolation policy deliberately gives up some browser compatibility:

- Many sites refuse iframe embedding or need downloads or top-level navigation withheld from the frame by the default sandbox. An HTTPS application can also block public HTTP pages as mixed content. Disabling the sandbox trades its restrictions for compatibility but does not bypass mixed-content or private-network policy. The unsandboxed frame can navigate the top-level application under browser activation rules and use downloads, modal dialogs, and input locks. It does not isolate the visited origin's cookies per Browser tab or prevent an in-frame page from choosing its own next URL.
- In Web, a popup that escapes the sandbox retains its opener and can use that chain to navigate the top-level application. Desktop handles popup creation separately.
- A later iframe load reveals that navigation occurred but not the new cross-origin URL. History API and fragment changes may remain invisible; Web Back and Forward are unavailable after the state becomes unknown.
- Browsers conceal many iframe failures for security: DNS, TLS, mixed-content, CSP, and `X-Frame-Options` failures may emit `load` or no actionable event instead of `error`. The load-failure notice is best-effort.
- Saved title and URL survive reloads and plugin unload while the tab remains in Sidebar's layout. Closing the tab removes its checkpoint. Restart restoration does not recover page memory, unsaved forms or Chromium's history stack.
- Local files are rejected and remain owned by Document Preview.
- The native pane is an OS-level view painted above the whole Web UI, so Web UI menus and dialogs that overlap the Browser tab are covered by it. Its placement follows the content element, and a pane is hidden whenever the tab is hidden.
- In the native pane the shell refuses `<name>.localhost` hosts (Tauri's own local origins) and any loopback host on the Web UI's port, so a dev site on `something.localhost` does not load there; plain `localhost` on another port does.
- The native pane is Windows only (WebView2). The agent's Playwright tools drive panes over a loopback, unauthenticated DevTools port; see `apps/plexar-desktop/README.md` for that and the shared sign-in profile. The carrier has unit tests with a fake bridge; the live window behaviour has a compile but no automated test.
- Desktop shares process-local storage partitions by canonical workspace CWD; Sessions without a resolved Workspace are isolated separately. Cookies and Web storage do not survive application restart. Guest permissions, downloads and native popups are denied; approved HTTP(S) popup requests open Sidebar tabs. Host-address filtering is not a general private-network or DNS-rebinding firewall.

<a id="dev-note"></a>
### Dev Note

<details>
<summary>Working context for maintainers — click to expand</summary>

None.

</details>

**Runtime invariant:** No companion is published. Each navigation provider owns its live state and publishes checkpoints directly; the UI consumes the same provider state through its controller.
