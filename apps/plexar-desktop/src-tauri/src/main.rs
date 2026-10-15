//! Plexar Harness desktop app.
//!
//! Shows a local loading page, starts `plexar-harness web --no-open --port 0` as a child process,
//! reads the `dsh web: <url>` line it prints, and navigates the window to that URL (the one-time
//! token in it signs the webview in). When the Host exits before printing a URL, the loading page
//! shows its last stderr line. Closing the app stops the Host and its child processes.
//!
//! The harness is `PLEXAR_HARNESS_ROOT`, else the runtime the installer staged under the resource
//! directory, else the checkout this app was built from; Node is the staged `node.exe` when present,
//! else `node` on PATH. An installed copy creates or refreshes the Plexar profiles
//! (`cli/setup.mjs profiles`) before the Host starts, and checks the update endpoint in
//! `tauri.conf.json` once per launch: a failed check is logged to stderr only, and an available
//! update is installed only after the person accepts the dialog. `PLEXAR_HARNESS_KEY` and the other rig variables pass through. The Host is
//! spawned with `PLEXAR_DESKTOP=1` so its `plexarUpdate.restart()` Remote method is available.
//!
//! When the Host process exits with code 75, that is a restart request (`plexarUpdate.restart()`
//! after `plexarUpdate.apply()` reached `restart-required`): the app respawns the Host and
//! navigates the same window to its new `dsh web: <url>` line, instead of treating the exit as a
//! startup failure. Any other exit code keeps the existing failure/loading-page behavior.
//!
//! **Sign-in (N54, then Google sign-in N57).** The rig mints one per-account key. Before
//! spawning the Host, `main` resolves a key from the Windows Credential Manager (service "Plexar
//! Harness", user "default", via the `keyring` crate — the same entry the CLI reads/writes with
//! `@napi-rs/keyring`, so those two strings and the "raw key, nothing else" password format are
//! shared, never changed independently); with none stored it falls back to the
//! `PLEXAR_HARNESS_KEY` process env (a developer convenience — signing in never writes that env
//! back to the keyring automatically, and the keyring is never written by anything but
//! `sign_in_google` and `sign_out`). A stored or env key is validated against
//! `/api/harness/me` before the Host starts: entitled starts it directly, a network failure
//! starts it anyway (offline tolerance; model calls will surface their own errors), a 401
//! deletes the stored key and shows the sign-in card ("Please sign in again."), and an entitled:
//! false decision shows the card with the rig's reason. With no key at all, the loading page
//! shows the sign-in card immediately and the Host is not started. The resolved key reaches the
//! Host only through that child process's own env (`spawn_host_process`), never the app's own
//! process env, and every respawn (including the exit-75 restart path) reuses the same resolved
//! key.
//!
//! **Google sign-in (N57).** The card's one button opens the system browser to
//! `{rig}/api/harness/authorize` with a PKCE challenge and a `state` bound to this run's
//! loopback listener (`google::bind_loopback`, `127.0.0.1:0`); the rig does Google sign-in and
//! redirects the browser to that listener's `/callback`. `sign_in_google` waits up to 5 minutes,
//! answers the browser with a small HTML page, and exchanges a returned code at
//! `/api/harness/token`. `cancel_sign_in` aborts an in-flight wait and frees the port.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod auth;
mod google;

use std::io::{BufRead, BufReader};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Duration;

use tauri::{Manager, RunEvent, Url};

/// Host exit code that means "restart me", per the pinned desktop-restart contract.
const RESTART_EXIT_CODE: i32 = 75;

/// Host exit code that means "I was signed out (Settings Account block `plexarAuth.signOut()`);
/// stop respawning and show the sign-in card", per the pinned desktop-restart contract's sibling
/// (`packages/bundle/plexar/src/auth-remote.ts`, `SIGNOUT_EXIT_CODE`).
const SIGNOUT_EXIT_CODE: i32 = 76;

/// What a Host child's exit code means to the supervisor loop.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum HostExitAction {
    /// Respawn the Host with the same key and navigate the same window to its new URL.
    Restart,
    /// Stop respawning and show the sign-in card with "You're signed out."
    SignedOut,
    /// Any other exit: today's startup-failure/quiet-stop handling applies.
    Other,
}

/// Pure decision over a Host child's exit code, isolated from process/window handling so it is
/// unit-testable without spawning anything.
fn host_exit_action(code: Option<i32>) -> HostExitAction {
    match code {
        Some(RESTART_EXIT_CODE) => HostExitAction::Restart,
        Some(SIGNOUT_EXIT_CODE) => HostExitAction::SignedOut,
        _ => HostExitAction::Other,
    }
}

/// Windows Credential Manager entry that holds the user's rig key.
const KEYRING_SERVICE: &str = "Plexar Harness";
const KEYRING_USER: &str = "default";

/// Default rig base URL, overridden by `PLEXAR_RIG_URL` (same default as the bundle's
/// `llm-pi-ai` provider config in `packages/bundle/plexar/cordis.patch.yml`).
const DEFAULT_RIG_URL: &str = "https://llm.plexar.tech";

fn rig_url() -> String {
    std::env::var("PLEXAR_RIG_URL").unwrap_or_else(|_| DEFAULT_RIG_URL.to_string())
}

fn keyring_entry() -> Result<keyring::Entry, keyring::Error> {
    keyring::Entry::new(KEYRING_SERVICE, KEYRING_USER)
}

/// Reads the stored key, if any. A "no entry" result is `Ok(None)`; any other keyring failure
/// (locked store, platform error) is also treated as "no stored key" so startup degrades to the
/// env fallback or the sign-in card rather than failing outright.
fn stored_key() -> Option<String> {
    keyring_entry().ok()?.get_password().ok()
}

/// Resolves the key to use at startup: the keyring, else the `PLEXAR_HARNESS_KEY` developer
/// fallback. Returns which source it came from, since only a keyring-sourced key is left alone
/// on an explicit invalid decision ("delete nothing yet" — behavior step 4).
fn resolve_startup_key() -> Option<String> {
    stored_key().or_else(|| std::env::var("PLEXAR_HARNESS_KEY").ok())
}

/// What the loading page shows while the Host starts, or instead of the spinner when a key is
/// missing or was rejected.
#[derive(Clone, Default)]
struct Status {
    error: Option<String>,
    /// Set instead of `error` when the loading page must show the sign-in card. `None` message
    /// means "show the card with no message" (no key at all yet).
    needs_signin: Option<Option<String>>,
    /// The signed-in email, shown as "Signed in as <email>" while the Host starts after a
    /// successful sign-in. Cleared once the sign-in card is shown again.
    signin_email: Option<String>,
    /// The loopback listener's port while `sign_in_google` is waiting on its callback, for the
    /// card's "Waiting on port <n>…" footer line. `None` when no Google sign-in is in flight.
    signin_port: Option<u16>,
}

/// Tracks the current Host child by pid (not the `Child` handle itself, so the supervisor thread
/// can own the blocking `wait()` without holding a lock `stop_host` also needs).
struct HostState {
    child_pid: Arc<Mutex<Option<u32>>>,
    shutting_down: Arc<AtomicBool>,
    status: Arc<Mutex<Status>>,
    /// Set while `sign_in_google` is waiting on the loopback callback; `cancel_sign_in` flips it
    /// to abort that wait and free the port. `None` when no sign-in is in flight.
    signin_cancel: Arc<Mutex<Option<Arc<AtomicBool>>>>,
    /// The PKCE verifier for an in-flight "Use a code instead" (oob) sign-in, set by
    /// `start_code_sign_in` and consumed by `sign_in_code`. `None` when no code sign-in is in
    /// flight.
    pending_code_signin: Arc<Mutex<Option<String>>>,
}

/// Layout staged by `scripts/plexar-release/stage-windows-bundle.mjs` into the Tauri bundle's
/// resource directory (`apps/plexar-desktop/INSTALLER.md`): a built harness tree at
/// `plexar-runtime/harness` and a pinned Node at `plexar-runtime/node/node.exe`, resolved through
/// `resource_dir` rather than hardcoded so tests can pass an arbitrary base.
const STAGED_HARNESS_DIR: &str = "plexar-runtime/harness";
const STAGED_NODE_EXE: &str = "plexar-runtime/node/node.exe";

/// Resolves the harness root: `PLEXAR_HARNESS_ROOT` env (developer/test override), else the staged
/// runtime under `resource_dir` when present (installed case), else the checkout this binary was
/// built from (source-launch/dev case, unchanged from before N91).
fn harness_root_with(resource_dir: Option<&std::path::Path>) -> PathBuf {
    if let Some(root) = std::env::var_os("PLEXAR_HARNESS_ROOT") {
        return PathBuf::from(root);
    }
    if let Some(resource_dir) = resource_dir {
        let staged = resource_dir.join(STAGED_HARNESS_DIR);
        if staged.is_dir() {
            return staged;
        }
    }
    PathBuf::from(concat!(env!("CARGO_MANIFEST_DIR"), "/../../.."))
}

/// Set once from `main()`'s `app.path().resource_dir()` before `start_at_launch` runs. `None` in
/// unit tests and in the (unreachable at runtime) case Tauri fails to resolve a resource directory.
static RESOURCE_DIR: std::sync::OnceLock<Option<PathBuf>> = std::sync::OnceLock::new();

/// Strips the Windows verbatim prefix (`\\?\`) from a drive path. Tauri returns `resource_dir()` in
/// that form; Node resolves a `\\?\C:\...` script path to a different string than the module's own
/// `import.meta.url`, so the CLI's entry-point check fails and it exits 0 without doing anything.
fn without_verbatim_prefix(path: &std::path::Path) -> PathBuf {
    let text = path.to_string_lossy();
    match text.strip_prefix(r"\\?\") {
        Some(rest) if !rest.starts_with(r"UNC\") => PathBuf::from(rest),
        _ => path.to_path_buf(),
    }
}

fn resource_dir() -> Option<PathBuf> {
    RESOURCE_DIR.get().cloned().flatten()
}

fn harness_root() -> PathBuf {
    harness_root_with(resource_dir().as_deref())
}

/// Resolves the `node` executable: the staged Node under `resource_dir` when present (installed
/// case), else `"node"` off `PATH` (dev case, unchanged from before N91).
fn node_command_with(resource_dir: Option<&std::path::Path>) -> PathBuf {
    if let Some(resource_dir) = resource_dir {
        let staged = resource_dir.join(STAGED_NODE_EXE);
        if staged.is_file() {
            return staged;
        }
    }
    PathBuf::from("node")
}

/// True when the harness resolves to the runtime staged under `resource_dir` (the installed case).
fn installed_runtime() -> bool {
    std::env::var_os("PLEXAR_HARNESS_ROOT").is_none()
        && resource_dir().is_some_and(|dir| dir.join(STAGED_HARNESS_DIR).is_dir())
}

/// Runs `node setup.mjs profiles` from the installed runtime, so every Plexar profile exists and
/// links this installation before the Host starts (idempotent; see `cli/setup.mjs`).
fn ensure_installed_profiles() -> Result<(), String> {
    let setup = harness_root().join("packages/bundle/plexar/cli/setup.mjs");
    let mut command = Command::new(node_command_with(resource_dir().as_deref()));
    command.arg(&setup).arg("profiles").stdin(Stdio::null()).stdout(Stdio::null()).stderr(Stdio::piped());
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x0800_0000);
    }
    let output = command.output().map_err(|e| format!("could not set up the Plexar profiles ({e})"))?;
    if output.status.success() {
        return Ok(());
    }
    let stderr = String::from_utf8_lossy(&output.stderr);
    Err(stderr.lines().rev().find(|l| !l.trim().is_empty()).unwrap_or("could not set up the Plexar profiles").to_string())
}

/// Checks the updater endpoint once. Every failure (no network, no `latest.json` published yet, a
/// bad signature) is logged to stderr and otherwise ignored. When a newer signed release exists,
/// a dialog asks first; on yes the installer is downloaded and verified, the Host is stopped, and
/// the NSIS installer takes over (it relaunches the app).
fn check_for_update(app: &tauri::AppHandle) {
    use tauri_plugin_dialog::{DialogExt, MessageDialogButtons};
    use tauri_plugin_updater::UpdaterExt;

    let result: Result<(), String> = tauri::async_runtime::block_on(async {
        let updater = app.updater().map_err(|e| e.to_string())?;
        let Some(update) = updater.check().await.map_err(|e| e.to_string())? else {
            return Ok(());
        };
        let accepted = app
            .dialog()
            .message(format!("Plexar Harness {} is available. Restart now to update?", update.version))
            .title("Plexar Harness update")
            .buttons(MessageDialogButtons::OkCancelCustom("Restart now".to_string(), "Later".to_string()))
            .blocking_show();
        if !accepted {
            return Ok(());
        }
        // download() verifies the minisign signature against plugins.updater.pubkey.
        let bytes = update.download(|_, _| {}, || {}).await.map_err(|e| format!("download or signature check failed: {e}"))?;
        stop_host(&app.state::<HostState>());
        update.install(bytes).map_err(|e| format!("install failed: {e}"))?;
        app.restart();
    });
    if let Err(message) = result {
        eprintln!("plexar-desktop: update check skipped: {message}");
    }
}

/// The loading page polls this until the window navigates away, an error appears, or the
/// sign-in card must be shown.
#[tauri::command]
fn host_status(state: tauri::State<HostState>) -> serde_json::Value {
    let status = state.status.lock().unwrap().clone();
    serde_json::json!({
        "error": status.error,
        "needsSignin": status.needs_signin.is_some(),
        "signinMessage": status.needs_signin.flatten(),
        "signinEmail": status.signin_email,
        "signinPort": status.signin_port,
    })
}

/// Opens `url` in the system browser without a console window.
fn open_url(url: &str) -> Result<(), String> {
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        // Not `cmd /C start`: cmd splits the URL at its first `&`, dropping state and the PKCE challenge.
        Command::new("rundll32")
            .args(["url.dll,FileProtocolHandler", url])
            .creation_flags(CREATE_NO_WINDOW)
            .status()
            .map_err(|e| e.to_string())?;
    }
    #[cfg(not(windows))]
    {
        Command::new("xdg-open").arg(url).status().map_err(|e| e.to_string())?;
    }
    Ok(())
}

/// Applies an `auth::check` entitlement decision after a fresh sign-in: entitled starts the
/// Host; not entitled returns the card message. Distinct from `start_at_launch`'s handling of
/// `SignedOut` (impossible immediately after a fresh exchange) and `NetworkError` (still starts
/// the Host — offline tolerance applies here too, since the key was just minted and stored).
fn apply_entitlement_and_start(app: &tauri::AppHandle, state: &HostState, key: String, email: String) -> Result<(), String> {
    state.status.lock().unwrap().signin_email = Some(email.clone());
    match auth::check(&rig_url(), &key) {
        auth::CheckResult::Decision(auth::Decision::Entitled { .. }) | auth::CheckResult::NetworkError => {
            start_host(app, state, key)
        }
        auth::CheckResult::Decision(auth::Decision::NotEntitled { message }) => {
            state.status.lock().unwrap().signin_email = None;
            Err(message)
        }
        auth::CheckResult::SignedOut => {
            if let Ok(entry) = keyring_entry() {
                let _ = entry.delete_credential();
            }
            state.status.lock().unwrap().signin_email = None;
            Err("Please sign in again.".to_string())
        }
    }
}

/// Tauri command backing the card's "Sign in with Google" button. Runs the full desktop OAuth
/// flow: generates a PKCE verifier/challenge and a `state` value, binds the one-shot loopback
/// listener, opens the system browser to `{rig}/api/harness/authorize`, waits up to 5 minutes
/// for the browser's `/callback`, exchanges a returned code at `/api/harness/token`, stores the
/// key, checks entitlement, and starts the Host. Every other path returns a message string for
/// the card to display and never starts the Host.
// `async`: the browser wait and the network calls must not block the window.
#[tauri::command(async)]
fn sign_in_google(app: tauri::AppHandle, state: tauri::State<HostState>) -> Result<(), String> {
    let verifier = google::generate_verifier();
    let challenge = google::challenge_from_verifier(&verifier);
    let state_token = google::generate_state();

    let (listener, port) = google::bind_loopback().map_err(|e| format!("Couldn't start the local sign-in listener: {e}"))?;
    let redirect_uri = google::redirect_uri(port);

    let cancel = Arc::new(AtomicBool::new(false));
    *state.signin_cancel.lock().unwrap() = Some(cancel.clone());
    state.status.lock().unwrap().signin_port = Some(port);

    let url = google::build_authorize_url(&rig_url(), &redirect_uri, &state_token, &challenge);
    open_url(&url)?;

    let outcome = google::wait_for_callback(&listener, Duration::from_secs(300), &state_token, &cancel);
    *state.signin_cancel.lock().unwrap() = None;
    state.status.lock().unwrap().signin_port = None;

    let code = match outcome {
        google::WaitOutcome::Code(code) => code,
        google::WaitOutcome::Cancelled => return Err("Sign-in was cancelled.".to_string()),
        google::WaitOutcome::Error(reason) => {
            eprintln!("plexar-desktop: sign-in callback error: {reason}");
            // access_denied: the person chose Deny on Plexar's consent page.
            return Err(if reason == "access_denied" {
                "Sign-in was cancelled.".to_string()
            } else {
                "Sign-in was cancelled or expired. Try again.".to_string()
            });
        }
        google::WaitOutcome::TimedOut => return Err("Sign-in was cancelled or expired. Try again.".to_string()),
    };

    match google::exchange(&rig_url(), &code, &verifier, &redirect_uri) {
        Ok(google::ExchangeSuccess { key, email }) => {
            if let Ok(entry) = keyring_entry() {
                let _ = entry.set_password(&key);
            }
            apply_entitlement_and_start(&app, &state, key, email)
        }
        Err(google::ExchangeError::InvalidGrant(message)) => Err(message),
        Err(google::ExchangeError::NetworkError) => Err("Can't reach Plexar. Check your connection and try again.".to_string()),
    }
}

/// Tauri command backing the card's Cancel control: aborts an in-flight `sign_in_google` wait,
/// frees the loopback port, and drops any pending "Use a code instead" verifier. A no-op for
/// whichever flow was not in flight.
#[tauri::command]
fn cancel_sign_in(state: tauri::State<HostState>) {
    if let Some(cancel) = state.signin_cancel.lock().unwrap().as_ref() {
        cancel.store(true, Ordering::SeqCst);
    }
    *state.pending_code_signin.lock().unwrap() = None;
}

/// Tauri command backing the card's "Use a code instead" link: the oob variant of contract §10p
/// (same as `plexar-harness login --no-browser`). Generates a PKCE verifier/challenge and state,
/// opens the system browser to `{rig}/api/harness/authorize?redirect_uri=oob&...`, and stores the
/// verifier in `HostState` for `sign_in_code` to consume once the person pastes the code shown on
/// that page. Never waits on a loopback listener: the person supplies the code by hand.
#[tauri::command]
fn start_code_sign_in(state: tauri::State<HostState>) -> Result<(), String> {
    let verifier = google::generate_verifier();
    let challenge = google::challenge_from_verifier(&verifier);
    let state_token = google::generate_state();
    let url = google::build_authorize_url(&rig_url(), "oob", &state_token, &challenge);
    *state.pending_code_signin.lock().unwrap() = Some(verifier);
    open_url(&url)
}

/// Tauri command backing the card's code field: exchanges the pasted code against
/// `/api/harness/token` with `redirect_uri: "oob"`, using the verifier `start_code_sign_in`
/// stored, then the same keychain store + `/api/harness/me` check as the loopback path. Errors
/// when no code sign-in is in flight (the card was reloaded or the flow was cancelled).
// `async`: the network calls must not block the window.
#[tauri::command(async)]
fn sign_in_code(app: tauri::AppHandle, state: tauri::State<HostState>, code: String) -> Result<(), String> {
    let verifier = state
        .pending_code_signin
        .lock()
        .unwrap()
        .take()
        .ok_or_else(|| "Start over: open llm.plexar.tech again.".to_string())?;
    match google::exchange(&rig_url(), &code, &verifier, "oob") {
        Ok(google::ExchangeSuccess { key, email }) => {
            if let Ok(entry) = keyring_entry() {
                let _ = entry.set_password(&key);
            }
            apply_entitlement_and_start(&app, &state, key, email)
        }
        Err(google::ExchangeError::InvalidGrant(message)) => Err(message),
        Err(google::ExchangeError::NetworkError) => Err("Can't reach Plexar. Check your connection and try again.".to_string()),
    }
}

/// Tauri command that signs the user out: revokes the key server-side (best-effort), deletes the
/// stored key, stops the Host, and shows the sign-in card.
#[tauri::command(async)]
fn sign_out(state: tauri::State<HostState>) {
    if let Some(key) = stored_key() {
        google::logout(&rig_url(), &key);
    }
    if let Ok(entry) = keyring_entry() {
        let _ = entry.delete_credential();
    }
    stop_host(&state);
    *state.status.lock().unwrap() = Status { error: None, needs_signin: Some(None), signin_email: None, signin_port: None };
}

/// Spawn one `plexar-harness web` child with `key` as its `PLEXAR_HARNESS_KEY` (child env only —
/// the app's own process env is never touched). `PLEXAR_DESKTOP=1` tells the Host it runs under
/// the desktop app, so its `plexarUpdate.restart()` Remote method is available instead of
/// refused.
fn spawn_host_process(key: &str) -> Result<Child, String> {
    let cli = harness_root().join("packages/bundle/plexar/cli/plexar-harness.mjs");
    let mut command = Command::new(node_command_with(resource_dir().as_deref()));
    command
        .arg(&cli)
        .args(["web", "--no-open", "--port", "0"])
        .env("PLEXAR_DESKTOP", "1")
        .env("PLEXAR_HARNESS_KEY", key)
        .current_dir(std::env::var_os("USERPROFILE").or_else(|| std::env::var_os("HOME")).unwrap_or_else(|| ".".into()))
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        command.creation_flags(CREATE_NO_WINDOW);
    }
    command
        .spawn()
        .map_err(|e| format!("could not start Node ({e}). Install Node 22.19+ and make sure `node` is on PATH."))
}

/// Run one Host child to completion: stream its stderr into `last_err`, navigate the main window
/// to its `dsh web: <url>` line, and report whether navigation happened before it exited.
fn run_host_once(app: &tauri::AppHandle, mut child: Child) -> (std::process::ExitStatus, bool, String) {
    let stdout = child.stdout.take().expect("piped stdout");
    let stderr = child.stderr.take().expect("piped stderr");
    let last_err = Arc::new(Mutex::new(String::new()));
    let navigated = Arc::new(Mutex::new(false));

    let err_sink = last_err.clone();
    let stderr_thread = thread::spawn(move || {
        for line in BufReader::new(stderr).lines().map_while(Result::ok) {
            if !line.trim().is_empty() {
                *err_sink.lock().unwrap() = line;
            }
        }
    });

    let handle = app.clone();
    let navigated_sink = navigated.clone();
    let stdout_thread = thread::spawn(move || {
        for line in BufReader::new(stdout).lines().map_while(Result::ok) {
            if *navigated_sink.lock().unwrap() {
                continue;
            }
            if let Some(url) = line.strip_prefix("dsh web: ") {
                if let (Some(window), Ok(url)) = (handle.get_webview_window("main"), Url::parse(url.trim())) {
                    let _ = window.navigate(url);
                    *navigated_sink.lock().unwrap() = true;
                }
            }
        }
    });

    let status = child.wait().expect("wait on Host child");
    let _ = stdout_thread.join();
    let _ = stderr_thread.join();
    let did_navigate = *navigated.lock().unwrap();
    let reason = last_err.lock().unwrap().clone();
    (status, did_navigate, reason)
}

/// Spawn the Host with `key` and keep it running: on exit code 75 (a `plexarUpdate.restart()`
/// request, pinned in the shared contract) respawn it with the same key and navigate the same
/// window to its new URL. Any other exit is today's behaviour — a startup failure shows the last
/// stderr line; an exit after navigation leaves the window as-is.
fn start_host(app: &tauri::AppHandle, state: &HostState, key: String) -> Result<(), String> {
    let first_child = spawn_host_process(&key)?;
    *state.child_pid.lock().unwrap() = Some(first_child.id());
    state.status.lock().unwrap().needs_signin = None;
    state.shutting_down.store(false, Ordering::SeqCst);

    let handle = app.clone();
    let status = state.status.clone();
    let shutting_down = state.shutting_down.clone();
    let child_pid = state.child_pid.clone();

    thread::spawn(move || {
        let mut child = first_child;
        loop {
            let (exit_status, navigated, last_err) = run_host_once(&handle, child);
            *child_pid.lock().unwrap() = None;

            if shutting_down.load(Ordering::SeqCst) {
                return;
            }

            match host_exit_action(exit_status.code()) {
                HostExitAction::Restart => match spawn_host_process(&key) {
                    Ok(next) => {
                        *child_pid.lock().unwrap() = Some(next.id());
                        child = next;
                        continue;
                    }
                    Err(message) => {
                        status.lock().unwrap().error = Some(message);
                        return;
                    }
                },
                HostExitAction::SignedOut => {
                    *status.lock().unwrap() = Status {
                        error: None,
                        needs_signin: Some(Some("You're signed out.".to_string())),
                        signin_email: None,
                        signin_port: None,
                    };
                    return;
                }
                HostExitAction::Other => {}
            }

            // Any other exit code before navigation is a startup failure; after navigation the
            // Host simply stopped and today's loading-page error path does not apply.
            eprintln!("plexar-desktop: Host exited ({:?}): {last_err}", exit_status.code());
            if !navigated {
                let message = last_err
                    .strip_prefix("plexar-harness: ")
                    .unwrap_or(if last_err.is_empty() { "the harness exited before it was ready" } else { &last_err })
                    .to_string();
                status.lock().unwrap().error = Some(message);
            }
            return;
        }
    });

    Ok(())
}

/// Stop the Host and everything it started (Node children, language servers, shells). Works for
/// the respawned child too: `state.child_pid` tracks whichever process is current.
fn stop_host(state: &HostState) {
    state.shutting_down.store(true, Ordering::SeqCst);
    if let Some(pid) = state.child_pid.lock().unwrap().take() {
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            let _ = Command::new("taskkill")
                .args(["/PID", &pid.to_string(), "/T", "/F"])
                .creation_flags(0x0800_0000)
                .status();
        }
        #[cfg(not(windows))]
        {
            let _ = Command::new("kill").arg(pid.to_string()).status();
        }
    }
}

/// Resolves the startup key (keyring, else env) and decides what to show: no key shows the
/// sign-in card with no message and does not start the Host; an entitled key starts the Host; a
/// 401 (`SignedOut`) deletes the stored key and shows the card with "Please sign in again."; an
/// entitled: false decision shows the card with the rig's reason (the stored key is left in
/// place); a network failure starts the Host anyway (offline tolerance).
fn start_at_launch(app: &tauri::AppHandle, state: &HostState) {
    let Some(key) = resolve_startup_key() else {
        eprintln!("plexar-desktop: no stored key; showing the sign-in card");
        state.status.lock().unwrap().needs_signin = Some(None);
        return;
    };
    let outcome = match auth::check(&rig_url(), &key) {
        auth::CheckResult::Decision(auth::Decision::Entitled { .. }) => Ok(key),
        auth::CheckResult::Decision(auth::Decision::NotEntitled { message }) => Err(message),
        auth::CheckResult::SignedOut => {
            if let Ok(entry) = keyring_entry() {
                let _ = entry.delete_credential();
            }
            Err("Please sign in again.".to_string())
        }
        auth::CheckResult::NetworkError => Ok(key),
    };
    match outcome {
        Ok(key) => {
            if let Err(message) = start_host(app, state, key) {
                eprintln!("plexar-desktop: {message}");
                state.status.lock().unwrap().error = Some(message);
            }
        }
        Err(message) => {
            eprintln!("plexar-desktop: sign-in needed: {message}");
            state.status.lock().unwrap().needs_signin = Some(Some(message));
        }
    }
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_updater::Builder::new().build())
        .plugin(tauri_plugin_dialog::init())
        .manage(HostState {
            child_pid: Arc::new(Mutex::new(None)),
            shutting_down: Arc::new(AtomicBool::new(false)),
            status: Arc::new(Mutex::new(Status::default())),
            signin_cancel: Arc::new(Mutex::new(None)),
            pending_code_signin: Arc::new(Mutex::new(None)),
        })
        .invoke_handler(tauri::generate_handler![
            host_status,
            sign_in_google,
            cancel_sign_in,
            start_code_sign_in,
            sign_in_code,
            sign_out
        ])
        // One `setup` hook: a second `.setup` call replaces the first instead of adding to it.
        .setup(|app| {
            // `resource_dir()` needs the app handle, so it is resolved once here rather than at
            // each `harness_root()`/`node_command_with()` call.
            let _ = RESOURCE_DIR.set(app.path().resource_dir().ok().map(|dir| without_verbatim_prefix(&dir)));
            // Off the main thread: profile setup, the sign-in check and the update check can each
            // take seconds, and the window must stay responsive meanwhile.
            let handle = app.handle().clone();
            thread::spawn(move || {
                let installed = installed_runtime();
                let state = handle.state::<HostState>();
                match if installed { ensure_installed_profiles() } else { Ok(()) } {
                    Ok(()) => start_at_launch(&handle, &state),
                    Err(message) => {
                        eprintln!("plexar-desktop: profile setup failed: {message}");
                        state.status.lock().unwrap().error = Some(message);
                    }
                }
                if installed {
                    check_for_update(&handle);
                }
            });
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("failed to build the Plexar Harness app")
        .run(|app, event| {
            if let RunEvent::Exit = event {
                stop_host(&app.state::<HostState>());
            }
        });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn without_verbatim_prefix_strips_drive_paths_only() {
        use std::path::Path;
        assert_eq!(without_verbatim_prefix(Path::new(r"\\?\C:\Apps\Plexar")), PathBuf::from(r"C:\Apps\Plexar"));
        assert_eq!(without_verbatim_prefix(Path::new(r"\\?\UNC\srv\share")), PathBuf::from(r"\\?\UNC\srv\share"));
        assert_eq!(without_verbatim_prefix(Path::new(r"C:\Apps")), PathBuf::from(r"C:\Apps"));
    }

    #[test]
    fn host_exit_action_75_is_restart() {
        assert_eq!(host_exit_action(Some(RESTART_EXIT_CODE)), HostExitAction::Restart);
    }

    #[test]
    fn host_exit_action_76_is_signed_out() {
        assert_eq!(host_exit_action(Some(SIGNOUT_EXIT_CODE)), HostExitAction::SignedOut);
    }

    #[test]
    fn host_exit_action_other_codes_are_other() {
        assert_eq!(host_exit_action(Some(0)), HostExitAction::Other);
        assert_eq!(host_exit_action(Some(1)), HostExitAction::Other);
        assert_eq!(host_exit_action(None), HostExitAction::Other);
    }

    #[test]
    fn harness_root_with_no_resource_dir_falls_back_to_checkout() {
        std::env::remove_var("PLEXAR_HARNESS_ROOT");
        assert_eq!(harness_root_with(None), PathBuf::from(concat!(env!("CARGO_MANIFEST_DIR"), "/../../..")));
    }

    #[test]
    fn harness_root_with_staged_runtime_present_uses_it() {
        std::env::remove_var("PLEXAR_HARNESS_ROOT");
        let dir = std::env::temp_dir().join("plexar-desktop-test-harness-root-staged");
        let staged = dir.join(STAGED_HARNESS_DIR);
        std::fs::create_dir_all(&staged).unwrap();
        assert_eq!(harness_root_with(Some(&dir)), staged);
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn harness_root_with_resource_dir_but_no_staged_runtime_falls_back_to_checkout() {
        std::env::remove_var("PLEXAR_HARNESS_ROOT");
        let dir = std::env::temp_dir().join("plexar-desktop-test-harness-root-empty");
        std::fs::create_dir_all(&dir).unwrap();
        assert_eq!(harness_root_with(Some(&dir)), PathBuf::from(concat!(env!("CARGO_MANIFEST_DIR"), "/../../..")));
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn node_command_with_no_staged_node_uses_path_node() {
        let dir = std::env::temp_dir().join("plexar-desktop-test-node-command-empty");
        std::fs::create_dir_all(&dir).unwrap();
        assert_eq!(node_command_with(Some(&dir)), PathBuf::from("node"));
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn node_command_with_staged_node_present_uses_it() {
        let dir = std::env::temp_dir().join("plexar-desktop-test-node-command-staged");
        let node_dir = dir.join("plexar-runtime/node");
        std::fs::create_dir_all(&node_dir).unwrap();
        let node_exe = node_dir.join("node.exe");
        std::fs::write(&node_exe, b"").unwrap();
        assert_eq!(node_command_with(Some(&dir)), node_exe);
        std::fs::remove_dir_all(&dir).ok();
    }
}
