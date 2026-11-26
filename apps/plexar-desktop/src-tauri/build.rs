//! The app manifest gives the app's own commands an ACL: without it every command would be
//! callable from any capability-matched webview, including the remote Web UI. `capabilities/`
//! grants them per origin.
fn main() {
    tauri_build::try_build(tauri_build::Attributes::new().app_manifest(tauri_build::AppManifest::new().commands(&[
        "host_status",
        "sign_in_google",
        "cancel_sign_in",
        "start_code_sign_in",
        "sign_in_code",
        "sign_out",
        "browser_pane_open",
        "browser_pane_adopt",
        "browser_pane_navigate",
        "browser_pane_command",
        "browser_pane_set_bounds",
        "browser_pane_close",
        "browser_pane_list",
    ])))
    .expect("failed to run tauri-build");
}