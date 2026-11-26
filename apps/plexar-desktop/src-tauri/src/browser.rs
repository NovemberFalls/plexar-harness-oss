//! In-app browser panes (SPEC "Plexar in-app browser", section 2).
//!
//! A pane is a child webview of the `main` window, labelled `browser-pane-<n>`. Every pane uses
//! one data directory, `<app_local_data_dir>/browser-profile`, which differs from the main
//! webview's, so WebView2 runs the panes in their own browser process: the loopback debugging
//! port the panes open (`PLEXAR_INAPP_BROWSER_CDP`, passed to the Host child) reaches the panes and
//! nothing of the Web UI, whose URL carries the sign-in token. That separation is a security
//! requirement.
//!
//! The Web UI drives panes through the `browser_pane_*` commands (callable from the `main`
//! webview only) and hears about them through `plexar-browser:*` events. The Host asks for agent
//! panes with `plexar shell: <json>` lines on its stdout (`browser.ensure` / `browser.release`).
//! `url_allowed` is the single URL policy: http(s), a host, no credentials, and never the origin
//! of the Host Web UI. Nothing here logs a URL or a shell line's content.

use std::collections::BTreeMap;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex, OnceLock};

use serde::{Deserialize, Serialize};
use tauri::webview::{NewWindowResponse, PageLoadEvent, WebviewBuilder};
use tauri::{AppHandle, Emitter, LogicalPosition, LogicalSize, Manager, Url, Webview, WebviewUrl};

/// Environment variable that tells a Host child where the panes' debugging endpoint is.
pub const CDP_ENV: &str = "PLEXAR_INAPP_BROWSER_CDP";

/// Prefix of a Host stdout line addressed to the shell.
pub const SHELL_LINE_PREFIX: &str = "plexar shell: ";

/// wry 0.55.1's default `additional_browser_args` (`src/webview2/mod.rs`). Setting the argument
/// replaces wry's defaults, so they are restated here.
const WRY_DEFAULT_BROWSER_ARGS: &str = "--disable-features=msWebOOUI,msPdfOOUI,msSmartScreenProtection";

const MAIN_LABEL: &str = "main";
const PANE_LABEL_PREFIX: &str = "browser-pane-";
const PROFILE_DIR: &str = "browser-profile";
const MAX_SESSION_CHARS: usize = 128;
/// At most this many live panes created through `browser.ensure`; further ensures are ignored.
const MAX_AGENT_PANES: usize = 8;
const ABOUT_BLANK: &str = "about:blank";

const EVENT_STATE: &str = "plexar-browser:state";
const EVENT_OPEN_REQUESTED: &str = "plexar-browser:open-requested";
const EVENT_AGENT_OPENED: &str = "plexar-browser:agent-opened";
const EVENT_CLOSED: &str = "plexar-browser:closed";
const EVENT_LOAD_FAILED: &str = "plexar-browser:load-failed";

const UNKNOWN_PANE: &str = "unknown pane";

/// Who owns a pane: the Web UI (opened or adopted by a Browser tab) or the agent (`browser.ensure`).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum Owner {
    Ui,
    Agent,
}

/// What the Web UI sees of a pane (SPEC 2.2 `PaneState`).
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct PaneState {
    pub id: String,
    pub url: String,
    pub title: String,
    pub loading: bool,
    pub can_go_back: bool,
    pub can_go_forward: bool,
    pub owner: Owner,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub session: Option<String>,
}

/// One live pane. `webview` is `None` while the webview is still being created.
struct Pane {
    state: PaneState,
    webview: Option<Webview>,
}

#[derive(Default)]
struct Panes {
    next: u32,
    entries: BTreeMap<String, Pane>,
}

/// Managed state: the live panes and the origin of the Host Web UI the main window shows.
#[derive(Default, Clone)]
pub struct Browser {
    panes: Arc<Mutex<Panes>>,
    host_origin: Arc<Mutex<Option<String>>>,
}

impl Browser {
    fn host_origin(&self) -> Option<String> {
        self.host_origin.lock().unwrap().clone()
    }
}

/// The URL policy (SPEC 2.3): scheme http or https, a non-empty host, no username or password,
/// and an origin other than the Host Web UI's (`host_origin`, ASCII serialization). Also refused:
/// any `<name>.localhost` host, which Tauri serves its app and custom protocols on under Windows
/// (`Webview::is_local_url` strips the `.localhost` suffix), and any loopback host on the Host's
/// port (`localhost`, `127.0.0.0/8`, `[::1]`), not only the exact Host origin.
pub fn url_allowed(url: &Url, host_origin: Option<&str>) -> bool {
    if !matches!(url.scheme(), "http" | "https") {
        return false;
    }
    let Some(host) = url.host_str().filter(|host| !host.is_empty()) else {
        return false;
    };
    if host.trim_end_matches('.').ends_with(".localhost") {
        return false;
    }
    if !url.username().is_empty() || url.password().is_some() {
        return false;
    }
    let Some(origin) = host_origin else {
        return true;
    };
    if url.origin().ascii_serialization() == origin {
        return false;
    }
    let host_port = Url::parse(origin).ok().and_then(|origin| origin.port_or_known_default());
    !(is_loopback(url) && host_port.is_some() && url.port_or_known_default() == host_port)
}

/// True when the URL's host is a loopback name or address.
fn is_loopback(url: &Url) -> bool {
    let Some(host) = url.host_str() else {
        return false;
    };
    if host.trim_end_matches('.') == "localhost" {
        return true;
    }
    // The URL parser has already normalised IPv4 forms (`127.1`, `2130706433`) to dotted quads.
    let address = host.trim_start_matches('[').trim_end_matches(']');
    address.parse::<std::net::IpAddr>().is_ok_and(|address| address.is_loopback())
}

/// Parses `text` and applies `url_allowed`; a string that does not parse is not allowed.
fn parse_allowed(text: &str, host_origin: Option<&str>) -> Option<Url> {
    Url::parse(text).ok().filter(|url| url_allowed(url, host_origin))
}

/// A message from the Host (SPEC 1.2).
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ShellLine {
    Ensure(String),
    Release(String),
}

/// Parses one Host stdout line. Lines without the prefix, malformed JSON, unknown `op` values and
/// session ids that are empty or longer than 128 characters all give `None`.
pub fn parse_shell_line(line: &str) -> Option<ShellLine> {
    #[derive(Deserialize)]
    struct Raw {
        op: String,
        session: String,
    }
    let json = line.strip_prefix(SHELL_LINE_PREFIX)?;
    let raw: Raw = serde_json::from_str(json).ok()?;
    if raw.session.is_empty() || raw.session.chars().count() > MAX_SESSION_CHARS {
        return None;
    }
    match raw.op.as_str() {
        "browser.ensure" => Some(ShellLine::Ensure(raw.session)),
        "browser.release" => Some(ShellLine::Release(raw.session)),
        _ => None,
    }
}

/// The additional browser arguments every pane passes: wry's defaults plus the loopback
/// debugging port. WebView2 refuses a second webview in one data directory with different
/// arguments, so every pane builds the string from this one function and the one port.
pub fn browser_args(port: u16) -> String {
    format!("{WRY_DEFAULT_BROWSER_ARGS} --remote-debugging-port={port} --remote-debugging-address=127.0.0.1")
}

/// The debugging port for this app run: a free loopback port, picked once (bind
/// `127.0.0.1:0`, read the port, drop the listener). `None` when no port could be bound.
pub fn cdp_port() -> Option<u16> {
    static PORT: OnceLock<Option<u16>> = OnceLock::new();
    *PORT.get_or_init(|| {
        std::net::TcpListener::bind("127.0.0.1:0").ok().and_then(|listener| listener.local_addr().ok()).map(|addr| addr.port())
    })
}

/// The `PLEXAR_INAPP_BROWSER_CDP` value for Host children: set on Windows only.
pub fn cdp_endpoint() -> Option<String> {
    if cfg!(windows) {
        cdp_port().map(|port| format!("http://127.0.0.1:{port}"))
    } else {
        None
    }
}

/// Remembers the origin of the Host Web UI URL the main window navigates to, for the URL policy.
/// Called on every `dsh web: <url>` navigation, including after the code-75 restart (new port).
pub fn set_host_url(app: &AppHandle, url: &Url) {
    *app.state::<Browser>().host_origin.lock().unwrap() = Some(url.origin().ascii_serialization());
}

/// Handles one Host stdout line if it is a shell line; anything else is ignored silently.
pub fn handle_shell_line(app: &AppHandle, line: &str) {
    match parse_shell_line(line) {
        Some(ShellLine::Ensure(session)) => ensure_agent_pane(app, session),
        Some(ShellLine::Release(session)) => release_agent_pane(app, &session),
        None => {}
    }
}

/// `browser.ensure`: creates an agent pane for `session` unless one is live (agent or adopted).
fn ensure_agent_pane(app: &AppHandle, session: String) {
    let Some(id) = reserve_pane(app, Owner::Agent, Some(session.clone())) else {
        return;
    };
    if create_and_store(app, &id).is_ok() {
        let _ = app.emit_to(MAIN_LABEL, EVENT_AGENT_OPENED, serde_json::json!({ "id": id, "session": session }));
    }
}

/// `browser.release`: closes the session's pane while it is still agent-owned.
fn release_agent_pane(app: &AppHandle, session: &str) {
    let id = {
        let panes = app.state::<Browser>().panes.clone();
        let panes = panes.lock().unwrap();
        panes
            .entries
            .values()
            .find(|pane| pane.state.owner == Owner::Agent && pane.state.session.as_deref() == Some(session))
            .map(|pane| pane.state.id.clone())
    };
    if let Some(id) = id {
        close_pane(app, &id);
    }
}

/// Adds a placeholder entry with a fresh label and returns the label. For an agent pane, returns
/// `None` when the session already has a live pane. The entry exists before the webview so a
/// second `browser.ensure` and the webview's own callbacks both find it.
fn reserve_pane(app: &AppHandle, owner: Owner, session: Option<String>) -> Option<String> {
    let panes = app.state::<Browser>().panes.clone();
    let mut panes = panes.lock().unwrap();
    if session.is_some() {
        if panes.entries.values().any(|pane| pane.state.session == session) {
            return None;
        }
        if panes.entries.values().filter(|pane| pane.state.session.is_some()).count() >= MAX_AGENT_PANES {
            return None;
        }
    }
    panes.next += 1;
    let id = format!("{PANE_LABEL_PREFIX}{}", panes.next);
    let state = PaneState {
        id: id.clone(),
        url: ABOUT_BLANK.to_string(),
        title: String::new(),
        loading: false,
        can_go_back: false,
        can_go_forward: false,
        owner,
        session,
    };
    panes.entries.insert(id.clone(), Pane { state, webview: None });
    Some(id)
}

/// Creates the webview for the reserved entry `id` and stores it. On failure the entry is
/// removed. When the entry was closed while the webview was being created, the new webview is
/// closed too. No lock is held while the webview is created: its callbacks take the same lock on
/// the event loop.
fn create_and_store(app: &AppHandle, id: &str) -> Result<PaneState, String> {
    let browser = app.state::<Browser>().inner().clone();
    let webview = match create_webview(app, id) {
        Ok(webview) => webview,
        Err(message) => {
            eprintln!("plexar-desktop: could not create a browser pane: {message}");
            browser.panes.lock().unwrap().entries.remove(id);
            return Err(message);
        }
    };
    let state = {
        let mut panes = browser.panes.lock().unwrap();
        match panes.entries.get_mut(id) {
            Some(pane) => {
                pane.webview = Some(webview.clone());
                Some(pane.state.clone())
            }
            None => None,
        }
    };
    match state {
        Some(state) => {
            let _ = app.emit_to(MAIN_LABEL, EVENT_STATE, &state);
            Ok(state)
        }
        None => {
            let _ = webview.close();
            Err(UNKNOWN_PANE.to_string())
        }
    }
}

/// Builds one pane webview, hidden, at `about:blank`.
fn create_webview(app: &AppHandle, id: &str) -> Result<Webview, String> {
    let window = app.get_window(MAIN_LABEL).ok_or("the main window is gone")?;
    let port = cdp_port().ok_or("no free loopback port for the browser panes")?;
    let data_directory = app.path().app_local_data_dir().map_err(|e| e.to_string())?.join(PROFILE_DIR);
    let browser = app.state::<Browser>().inner().clone();
    let initial = Url::parse(ABOUT_BLANK).map_err(|e| e.to_string())?;

    // about:blank is allowed once, as the pane's initial document.
    let blank_used = AtomicBool::new(false);
    let nav_browser = browser.clone();
    let popup_browser = browser.clone();
    let popup_app = app.clone();
    let popup_id = id.to_string();
    let title_app = app.clone();
    let load_app = app.clone();

    let builder = WebviewBuilder::new(id, WebviewUrl::External(initial))
        // Not focused: wry's MoveFocus fails (E_INVALIDARG) while the main window is minimised,
        // and Tauri then drops the webview with only a log line, leaving a pane that never loads.
        .focused(false)
        .data_directory(data_directory)
        .additional_browser_args(&browser_args(port))
        .on_navigation(move |url| {
            if url.as_str() == ABOUT_BLANK {
                return !blank_used.swap(true, Ordering::SeqCst);
            }
            url_allowed(url, nav_browser.host_origin().as_deref())
        })
        .on_new_window(move |url, _features| {
            if url_allowed(&url, popup_browser.host_origin().as_deref()) {
                let _ = popup_app.emit_to(
                    MAIN_LABEL,
                    EVENT_OPEN_REQUESTED,
                    serde_json::json!({ "id": popup_id, "url": url.as_str() }),
                );
            }
            NewWindowResponse::Deny
        })
        .on_download(|_, _| false)
        .on_document_title_changed(move |webview, title| {
            update_pane(&title_app, webview.label(), |state| state.title = title);
        })
        .on_page_load(move |webview, payload| {
            let url = payload.url().to_string();
            let loading = matches!(payload.event(), PageLoadEvent::Started);
            update_pane(&load_app, webview.label(), |state| {
                state.url = url;
                state.loading = loading;
            });
        });

    let webview = window
        .add_child(builder, LogicalPosition::new(0.0, 0.0), LogicalSize::new(1.0, 1.0))
        .map_err(|e| e.to_string())?;
    let _ = webview.hide();
    #[cfg(windows)]
    attach_webview2_hooks(app, &webview);
    Ok(webview)
}

/// Applies `change` to pane `id` and emits `plexar-browser:state` when any field changed.
fn update_pane(app: &AppHandle, id: &str, change: impl FnOnce(&mut PaneState)) {
    let state = {
        let panes = app.state::<Browser>().panes.clone();
        let mut panes = panes.lock().unwrap();
        let Some(pane) = panes.entries.get_mut(id) else {
            return;
        };
        let before = pane.state.clone();
        change(&mut pane.state);
        if pane.state == before {
            return;
        }
        pane.state.clone()
    };
    let _ = app.emit_to(MAIN_LABEL, EVENT_STATE, &state);
}

/// Registers WebView2 handlers for what Tauri does not report: history (`CanGoBack` /
/// `CanGoForward`), the start of a navigation, the current source, and failed top-level
/// navigations. The handlers run on the event loop.
#[cfg(windows)]
fn attach_webview2_hooks(app: &AppHandle, webview: &Webview) {
    use webview2_com::Microsoft::Web::WebView2::Win32::{
        ICoreWebView2, COREWEBVIEW2_WEB_ERROR_STATUS, COREWEBVIEW2_WEB_ERROR_STATUS_OPERATION_CANCELED,
    };
    use webview2_com::{
        HistoryChangedEventHandler, NavigationCompletedEventHandler, NavigationStartingEventHandler,
        SourceChangedEventHandler,
    };
    use windows_core::{BOOL, PWSTR};

    fn history(core: &ICoreWebView2) -> (bool, bool) {
        let mut back = BOOL::default();
        let mut forward = BOOL::default();
        // SAFETY: plain COM getters on a live ICoreWebView2, called on the event loop.
        unsafe {
            let _ = core.CanGoBack(&mut back);
            let _ = core.CanGoForward(&mut forward);
        }
        (back.as_bool(), forward.as_bool())
    }

    fn source(core: &ICoreWebView2) -> Option<String> {
        let mut uri = PWSTR::null();
        // SAFETY: Source allocates the string; take_pwstr frees it.
        unsafe { core.Source(&mut uri).ok().map(|()| webview2_com::take_pwstr(uri)) }
    }

    let app = app.clone();
    let id = webview.label().to_string();
    let _ = webview.with_webview(move |platform| {
        // SAFETY: COM calls on the pane's controller, made on the event loop.
        let Ok(core) = (unsafe { platform.controller().CoreWebView2() }) else {
            return;
        };
        let mut token = 0i64;

        let (history_app, history_id) = (app.clone(), id.clone());
        let on_history = HistoryChangedEventHandler::create(Box::new(move |sender, _| {
            if let Some(core) = sender {
                let (back, forward) = history(&core);
                update_pane(&history_app, &history_id, |state| {
                    state.can_go_back = back;
                    state.can_go_forward = forward;
                });
            }
            Ok(())
        }));

        let (source_app, source_id) = (app.clone(), id.clone());
        let on_source = SourceChangedEventHandler::create(Box::new(move |sender, _| {
            if let Some(url) = sender.as_ref().and_then(source) {
                update_pane(&source_app, &source_id, |state| state.url = url);
            }
            Ok(())
        }));

        let (start_app, start_id) = (app.clone(), id.clone());
        let on_starting = NavigationStartingEventHandler::create(Box::new(move |_, _| {
            update_pane(&start_app, &start_id, |state| state.loading = true);
            Ok(())
        }));

        let (done_app, done_id) = (app.clone(), id.clone());
        let on_completed = NavigationCompletedEventHandler::create(Box::new(move |sender, args| {
            let (back, forward) = sender.as_ref().map(history).unwrap_or_default();
            update_pane(&done_app, &done_id, |state| {
                state.loading = false;
                state.can_go_back = back;
                state.can_go_forward = forward;
            });
            let Some(args) = args else {
                return Ok(());
            };
            let mut success = BOOL::default();
            let mut status = COREWEBVIEW2_WEB_ERROR_STATUS::default();
            // SAFETY: plain COM getters on the event's arguments.
            unsafe {
                args.IsSuccess(&mut success)?;
                args.WebErrorStatus(&mut status)?;
            }
            if !success.as_bool() && status != COREWEBVIEW2_WEB_ERROR_STATUS_OPERATION_CANCELED {
                let _ = done_app.emit_to(
                    MAIN_LABEL,
                    EVENT_LOAD_FAILED,
                    serde_json::json!({
                        "id": done_id,
                        "code": status.0,
                        "description": web_error_description(status.0),
                    }),
                );
            }
            Ok(())
        }));

        // SAFETY: registering handlers on a live ICoreWebView2, on the event loop.
        unsafe {
            let _ = core.add_HistoryChanged(&on_history, &mut token);
            let _ = core.add_SourceChanged(&on_source, &mut token);
            let _ = core.add_NavigationStarting(&on_starting, &mut token);
            let _ = core.add_NavigationCompleted(&on_completed, &mut token);
        }
        // Events raised before the handlers existed are lost; read the current values once.
        let (back, forward) = history(&core);
        let url = source(&core);
        update_pane(&app, &id, |state| {
            state.can_go_back = back;
            state.can_go_forward = forward;
            if let Some(url) = url {
                state.url = url;
            }
        });
    });
}

/// A short English name for a `COREWEBVIEW2_WEB_ERROR_STATUS` value.
#[cfg(windows)]
fn web_error_description(status: i32) -> &'static str {
    match status {
        1 => "certificate common name is incorrect",
        2 => "certificate expired",
        3 => "client certificate contains errors",
        4 => "certificate revoked",
        5 => "certificate is invalid",
        6 => "server unreachable",
        7 => "timeout",
        8 => "server returned an invalid or unrecognizable response",
        9 => "connection aborted",
        10 => "connection reset",
        11 => "disconnected",
        12 => "cannot connect",
        13 => "host name not resolved",
        15 => "redirect failed",
        16 => "unexpected error",
        17 => "valid authentication credentials required",
        18 => "valid proxy authentication required",
        _ => "navigation failed",
    }
}

/// Closes pane `id` and emits `plexar-browser:closed`. An unknown id does nothing.
pub fn close_pane(app: &AppHandle, id: &str) {
    let removed = app.state::<Browser>().panes.lock().unwrap().entries.remove(id);
    if let Some(pane) = removed {
        if let Some(webview) = pane.webview {
            let _ = webview.close();
        }
        let _ = app.emit_to(MAIN_LABEL, EVENT_CLOSED, serde_json::json!({ "id": id }));
    }
}

fn close_where(app: &AppHandle, keep: impl Fn(&PaneState) -> bool) {
    let ids: Vec<String> = {
        let panes = app.state::<Browser>().panes.clone();
        let panes = panes.lock().unwrap();
        panes.entries.values().filter(|pane| !keep(&pane.state)).map(|pane| pane.state.id.clone()).collect()
    };
    for id in ids {
        close_pane(app, &id);
    }
}

/// Closes every pane (the Host child exited).
pub fn close_all(app: &AppHandle) {
    close_where(app, |_| false);
}

/// The main webview started loading a new top-level page: the page that positioned the panes is
/// gone. Panes without a session are closed. Panes with a session (agent panes, adopted or not)
/// go back to `owner: "agent"`, are hidden and kept, since a Session may still be driving them.
pub fn reset_for_reload(app: &AppHandle) {
    close_where(app, |state| state.session.is_some());
    let kept: Vec<(String, Option<Webview>)> = {
        let panes = app.state::<Browser>().panes.clone();
        let panes = panes.lock().unwrap();
        panes.entries.values().map(|pane| (pane.state.id.clone(), pane.webview.clone())).collect()
    };
    for (id, webview) in kept {
        if let Some(webview) = webview {
            let _ = webview.hide();
        }
        update_pane(app, &id, |state| state.owner = Owner::Agent);
    }
}

/// The pane commands answer the `main` webview only, and only while it shows the Host Web UI
/// (the capability admits any loopback page in it).
fn require_main(app: &AppHandle, webview: &Webview) -> Result<(), String> {
    let denied = || "not allowed".to_string();
    if webview.label() != MAIN_LABEL {
        return Err(denied());
    }
    let origin = app.state::<Browser>().host_origin().ok_or_else(denied)?;
    let current = webview.url().map_err(|_| denied())?;
    if current.origin().ascii_serialization() == origin {
        Ok(())
    } else {
        Err(denied())
    }
}

fn pane_webview(app: &AppHandle, id: &str) -> Result<Webview, String> {
    let panes = app.state::<Browser>().panes.clone();
    let panes = panes.lock().unwrap();
    let pane = panes.entries.get(id).ok_or(UNKNOWN_PANE)?;
    pane.webview.clone().ok_or_else(|| UNKNOWN_PANE.to_string())
}

fn allowed_url(app: &AppHandle, url: &str) -> Result<Url, String> {
    parse_allowed(url, app.state::<Browser>().host_origin().as_deref()).ok_or_else(|| "url not allowed".to_string())
}

// The commands are `async` because creating or driving a webview from a synchronous command
// deadlocks on Windows.

/// Opens a new UI-owned pane; with `url`, navigation starts.
#[tauri::command]
pub async fn browser_pane_open(app: AppHandle, webview: Webview, url: Option<String>) -> Result<PaneState, String> {
    require_main(&app, &webview)?;
    let target = url.as_deref().map(|url| allowed_url(&app, url)).transpose()?;
    let id = reserve_pane(&app, Owner::Ui, None).ok_or(UNKNOWN_PANE)?;
    let state = create_and_store(&app, &id)?;
    if let Some(target) = target {
        let navigated = pane_webview(&app, &id).and_then(|pane| pane.navigate(target).map_err(|e| e.to_string()));
        if let Err(message) = navigated {
            // The Web UI never learns the id of a pane it got an error for; do not leave it behind.
            close_pane(&app, &id);
            return Err(message);
        }
    }
    Ok(state)
}

/// Marks an agent pane as UI-owned; its session is kept.
#[tauri::command]
pub async fn browser_pane_adopt(app: AppHandle, webview: Webview, id: String) -> Result<PaneState, String> {
    require_main(&app, &webview)?;
    update_pane(&app, &id, |state| state.owner = Owner::Ui);
    let panes = app.state::<Browser>().panes.clone();
    let panes = panes.lock().unwrap();
    panes.entries.get(&id).map(|pane| pane.state.clone()).ok_or_else(|| UNKNOWN_PANE.to_string())
}

#[tauri::command]
pub async fn browser_pane_navigate(app: AppHandle, webview: Webview, id: String, url: String) -> Result<(), String> {
    require_main(&app, &webview)?;
    let pane = pane_webview(&app, &id)?;
    let target = allowed_url(&app, &url)?;
    pane.navigate(target).map_err(|e| e.to_string())
}

/// `back`, `forward`, `reload` or `stop`.
#[tauri::command]
pub async fn browser_pane_command(app: AppHandle, webview: Webview, id: String, command: String) -> Result<(), String> {
    require_main(&app, &webview)?;
    let pane = pane_webview(&app, &id)?;
    match command.as_str() {
        "reload" => pane.reload().map_err(|e| e.to_string()),
        "back" | "forward" | "stop" => history_command(&pane, command),
        _ => Err("unknown command".to_string()),
    }
}

#[cfg(windows)]
fn history_command(pane: &Webview, command: String) -> Result<(), String> {
    pane.with_webview(move |platform| {
        // SAFETY: COM calls on the pane's controller, made on the event loop.
        unsafe {
            if let Ok(core) = platform.controller().CoreWebView2() {
                let _ = match command.as_str() {
                    "back" => core.GoBack(),
                    "forward" => core.GoForward(),
                    _ => core.Stop(),
                };
            }
        }
    })
    .map_err(|e| e.to_string())
}

#[cfg(not(windows))]
fn history_command(pane: &Webview, command: String) -> Result<(), String> {
    let script = match command.as_str() {
        "back" => "history.back()",
        "forward" => "history.forward()",
        _ => "window.stop()",
    };
    pane.eval(script).map_err(|e| e.to_string())
}

/// Positions the pane in logical pixels relative to the main webview's viewport. `visible:
/// false`, or a width or height below 1, hides it.
#[tauri::command]
#[allow(clippy::too_many_arguments)]
pub async fn browser_pane_set_bounds(
    app: AppHandle,
    webview: Webview,
    id: String,
    x: f64,
    y: f64,
    width: f64,
    height: f64,
    visible: bool,
) -> Result<(), String> {
    require_main(&app, &webview)?;
    let pane = pane_webview(&app, &id)?;
    if !visible || width < 1.0 || height < 1.0 {
        return pane.hide().map_err(|e| e.to_string());
    }
    pane.set_position(LogicalPosition::new(x, y)).map_err(|e| e.to_string())?;
    pane.set_size(LogicalSize::new(width, height)).map_err(|e| e.to_string())?;
    pane.show().map_err(|e| e.to_string())
}

/// Closes a pane; closing an unknown id succeeds.
#[tauri::command]
pub async fn browser_pane_close(app: AppHandle, webview: Webview, id: String) -> Result<(), String> {
    require_main(&app, &webview)?;
    close_pane(&app, &id);
    Ok(())
}

/// Every live pane.
#[tauri::command]
pub async fn browser_pane_list(app: AppHandle, webview: Webview) -> Result<Vec<PaneState>, String> {
    require_main(&app, &webview)?;
    let panes = app.state::<Browser>().panes.clone();
    let panes = panes.lock().unwrap();
    Ok(panes.entries.values().map(|pane| pane.state.clone()).collect())
}

#[cfg(test)]
mod tests {
    use super::*;

    const HOST: &str = "http://127.0.0.1:5173";

    fn allowed(text: &str) -> bool {
        parse_allowed(text, Some(HOST)).is_some()
    }

    #[test]
    fn url_policy_allows_http_and_https() {
        assert!(allowed("http://example.com/"));
        assert!(allowed("https://example.com/path?q=1"));
    }

    #[test]
    fn url_policy_allows_loopback_on_another_port() {
        assert!(allowed("http://127.0.0.1:3000/"));
        assert!(allowed("http://localhost:3000/"));
        assert!(allowed("http://[::1]:3000/"));
        assert!(allowed("http://example.com:5173/"));
    }

    #[test]
    fn url_policy_refuses_any_loopback_host_on_the_host_port() {
        assert!(!allowed("http://localhost:5173/"));
        assert!(!allowed("http://LOCALHOST:5173/x"));
        assert!(!allowed("http://localhost.:5173/"));
        assert!(!allowed("http://127.0.0.2:5173/"));
        assert!(!allowed("http://127.1:5173/"));
        assert!(!allowed("http://2130706433:5173/"));
        assert!(!allowed("http://[::1]:5173/"));
        assert!(!allowed("https://localhost:5173/"));
    }

    #[test]
    fn url_policy_refuses_tauri_localhost_origins() {
        assert!(!allowed("http://tauri.localhost/"));
        assert!(!allowed("https://tauri.localhost/index.html"));
        assert!(!allowed("http://ipc.localhost/sign_out"));
        assert!(!allowed("http://asset.localhost/x"));
        assert!(!allowed("http://my-scheme.localhost/"));
        assert!(!allowed("http://TAURI.LOCALHOST./"));
        assert!(parse_allowed("http://tauri.localhost/", None).is_none());
        // Plain localhost is ordinary loopback, not an app protocol.
        assert!(allowed("http://localhost/"));
    }

    #[test]
    fn url_policy_refuses_other_schemes() {
        assert!(!allowed("file:///C:/Windows/win.ini"));
        assert!(!allowed("javascript:alert(1)"));
        assert!(!allowed("data:text/html,hi"));
        assert!(!allowed("about:blank"));
    }

    #[test]
    fn url_policy_refuses_credentials() {
        assert!(!allowed("https://user@example.com/"));
        assert!(!allowed("https://user:pass@example.com/"));
        assert!(!allowed("https://:pass@example.com/"));
    }

    #[test]
    fn url_policy_refuses_the_host_origin_on_any_path() {
        assert!(!allowed("http://127.0.0.1:5173/"));
        assert!(!allowed("http://127.0.0.1:5173/some/path?token=x"));
        assert!(parse_allowed("http://127.0.0.1:5173/", None).is_some());
    }

    #[test]
    fn url_policy_refuses_an_empty_host() {
        assert!(!allowed("http://"));
        assert!(!allowed("https:///"));
    }

    #[test]
    fn shell_line_parses_ensure_and_release() {
        assert_eq!(
            parse_shell_line(r#"plexar shell: {"op":"browser.ensure","session":"s1"}"#),
            Some(ShellLine::Ensure("s1".to_string()))
        );
        assert_eq!(
            parse_shell_line(r#"plexar shell: {"op":"browser.release","session":"s1"}"#),
            Some(ShellLine::Release("s1".to_string()))
        );
    }

    #[test]
    fn shell_line_ignores_a_wrong_prefix() {
        assert_eq!(parse_shell_line(r#"plexar shel: {"op":"browser.ensure","session":"s1"}"#), None);
        assert_eq!(parse_shell_line(r#"{"op":"browser.ensure","session":"s1"}"#), None);
        assert_eq!(parse_shell_line("dsh web: http://127.0.0.1:1/"), None);
    }

    #[test]
    fn shell_line_ignores_malformed_json() {
        assert_eq!(parse_shell_line("plexar shell: {not json"), None);
        assert_eq!(parse_shell_line(r#"plexar shell: {"op":"browser.ensure"}"#), None);
        assert_eq!(parse_shell_line(r#"plexar shell: {"op":"browser.ensure","session":7}"#), None);
    }

    #[test]
    fn shell_line_ignores_an_unknown_op() {
        assert_eq!(parse_shell_line(r#"plexar shell: {"op":"browser.open","session":"s1"}"#), None);
    }

    #[test]
    fn shell_line_ignores_an_empty_session() {
        assert_eq!(parse_shell_line(r#"plexar shell: {"op":"browser.ensure","session":""}"#), None);
    }

    #[test]
    fn shell_line_session_limit_is_128_characters() {
        let at_limit = "a".repeat(128);
        let over = "a".repeat(129);
        assert_eq!(
            parse_shell_line(&format!(r#"plexar shell: {{"op":"browser.ensure","session":"{at_limit}"}}"#)),
            Some(ShellLine::Ensure(at_limit))
        );
        assert_eq!(parse_shell_line(&format!(r#"plexar shell: {{"op":"browser.ensure","session":"{over}"}}"#)), None);
    }

    #[test]
    fn browser_args_keep_wry_defaults_and_add_the_debugging_port() {
        let args = browser_args(9222);
        assert!(args.contains("--disable-features=msWebOOUI,msPdfOOUI,msSmartScreenProtection"));
        assert!(args.contains("--remote-debugging-port=9222"));
        assert!(args.contains("--remote-debugging-address=127.0.0.1"));
        assert_eq!(args, browser_args(9222));
    }

    #[test]
    fn pane_state_serializes_per_the_contract() {
        let state = PaneState {
            id: "browser-pane-1".to_string(),
            url: ABOUT_BLANK.to_string(),
            title: String::new(),
            loading: false,
            can_go_back: true,
            can_go_forward: false,
            owner: Owner::Agent,
            session: None,
        };
        assert_eq!(
            serde_json::to_value(&state).unwrap(),
            serde_json::json!({
                "id": "browser-pane-1", "url": "about:blank", "title": "", "loading": false,
                "canGoBack": true, "canGoForward": false, "owner": "agent"
            })
        );
    }
}
