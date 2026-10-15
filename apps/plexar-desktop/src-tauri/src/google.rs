//! Desktop Google sign-in (N57), against the pinned contract: the system browser opens
//! `{rig}/api/harness/authorize?redirect_uri=...&state=...&code_challenge=...
//! &code_challenge_method=S256`; Plexar does Google sign-in and redirects the browser to
//! `redirect_uri` with `?code=...&state=...` (or `?error=...&state=...`); `POST
//! {rig}/api/harness/token {"code","code_verifier","redirect_uri"}` trades the single-use code
//! plus the PKCE verifier for a new key. `redirect_uri` must be byte-identical between the
//! authorize step and the token step.
//!
//! This module holds the pure pieces (PKCE, state, callback-query parsing/verification) and the
//! I/O pieces (the one-shot loopback listener, the token exchange, sign-out) separately so the
//! pure logic is unit-testable without a socket or the network.

use std::io::{BufRead, BufReader, Read, Write};
use std::net::{TcpListener, TcpStream};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};

use base64::engine::general_purpose::URL_SAFE_NO_PAD;
use base64::Engine;
use ring::rand::{SecureRandom, SystemRandom};
use sha2::{Digest, Sha256};

/// Generates 32 random bytes, base64url-encoded without padding (43 characters). Used for both
/// the PKCE code verifier (RFC 7636 section 4.1) and the OAuth `state` value.
fn random_url_safe_token() -> String {
    let mut bytes = [0u8; 32];
    SystemRandom::new().fill(&mut bytes).expect("system RNG for sign-in token");
    URL_SAFE_NO_PAD.encode(bytes)
}

/// Generates a fresh PKCE code verifier.
pub fn generate_verifier() -> String {
    random_url_safe_token()
}

/// Generates a fresh OAuth `state` value, checked back against the callback's `state` param.
pub fn generate_state() -> String {
    random_url_safe_token()
}

/// Derives the S256 PKCE challenge from a verifier: `base64url(SHA256(verifier))`, no padding.
pub fn challenge_from_verifier(verifier: &str) -> String {
    let digest = Sha256::digest(verifier.as_bytes());
    URL_SAFE_NO_PAD.encode(digest)
}

/// The redirect URI the loopback listener answers on: `http://127.0.0.1:<port>/callback`,
/// literal host, no trailing slash. Passed byte-identical to both the authorize URL and the
/// token exchange body.
pub fn redirect_uri(port: u16) -> String {
    format!("http://127.0.0.1:{port}/callback")
}

/// Builds the `{rig}/api/harness/authorize?...` URL, URL-encoding each value.
pub fn build_authorize_url(base_url: &str, redirect_uri: &str, state: &str, challenge: &str) -> String {
    format!(
        "{}/api/harness/authorize?redirect_uri={}&state={}&code_challenge={}&code_challenge_method=S256",
        base_url.trim_end_matches('/'),
        url_encode(redirect_uri),
        url_encode(state),
        url_encode(challenge),
    )
}

/// Minimal query-component percent-encoding: keeps unreserved characters (RFC 3986) literal and
/// percent-encodes everything else, including `&`, `=`, `:`, and `/`.
fn url_encode(value: &str) -> String {
    let mut out = String::with_capacity(value.len());
    for byte in value.bytes() {
        match byte {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' => out.push(byte as char),
            _ => out.push_str(&format!("%{byte:02X}")),
        }
    }
    out
}

/// Outcome of parsing and verifying the browser's `GET /callback?...` request against the
/// `state` this run generated.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum CallbackOutcome {
    /// `?code=...&state=...` was present and `state` matched.
    Code(String),
    /// `?error=...` was present, `state` was present but did not match, or `code`/`state` were
    /// missing. The reason string is shown in the card's error message.
    Error(String),
}

/// Parses the query string of a `GET /callback?...` request line and verifies `state` against
/// `expected_state` (constant-time is not needed here: `state` is not a secret, only a replay/
/// mixup guard, and its comparison is not on a path an attacker can time against the compare
/// itself — the state is bound to this one loopback listener). Percent-decoding is not needed:
/// the rig sends opaque token/reason values that never require it, and decoding here would let a
/// crafted value smuggle characters past this parser.
pub fn parse_callback_query(query: &str, expected_state: &str) -> CallbackOutcome {
    let mut code: Option<String> = None;
    let mut state: Option<String> = None;
    let mut error: Option<String> = None;
    for pair in query.split('&') {
        let mut parts = pair.splitn(2, '=');
        let key = parts.next().unwrap_or("");
        let value = parts.next().unwrap_or("");
        match key {
            "code" if code.is_none() => code = Some(value.to_string()),
            "state" if state.is_none() => state = Some(value.to_string()),
            "error" if error.is_none() => error = Some(value.to_string()),
            _ => {}
        }
    }
    if let Some(error) = error {
        return CallbackOutcome::Error(error);
    }
    match state {
        Some(ref s) if s != expected_state => return CallbackOutcome::Error("state_mismatch".to_string()),
        None => return CallbackOutcome::Error("missing_state".to_string()),
        Some(_) => {}
    }
    match code {
        Some(code) if !code.is_empty() => CallbackOutcome::Code(code),
        _ => CallbackOutcome::Error("missing_code".to_string()),
    }
}

/// Parses one HTTP request line (`"GET /callback?code=x&state=y HTTP/1.1"`). Returns `None` when
/// the method is not `GET` or the path is not exactly `/callback` (a request to any other path
/// is ignored by the caller: "accept ONLY the first request on path /callback").
pub fn parse_callback_request_line(line: &str, expected_state: &str) -> Option<CallbackOutcome> {
    let mut parts = line.trim_end().splitn(3, ' ');
    let method = parts.next()?;
    let target = parts.next()?;
    if method != "GET" {
        return None;
    }
    let (path, query) = target.split_once('?').unwrap_or((target, ""));
    if path != "/callback" {
        return None;
    }
    Some(parse_callback_query(query, expected_state))
}

/// Result of waiting for the browser callback.
#[derive(Debug)]
pub enum WaitOutcome {
    Code(String),
    Error(String),
    /// The 5-minute wait elapsed with no `/callback` request.
    TimedOut,
    /// `sign_in_google`'s Cancel control set the flag passed to `wait_for_callback`.
    Cancelled,
}

/// One page of HTML answered to the browser after the callback lands, styled to match the app's
/// dark/orange card. `message` is either the success line or the error text.
fn callback_page(success: bool, message: &str) -> String {
    let heading = if success { "You're signed in" } else { "Sign-in didn't complete" };
    format!(
        "<!doctype html><html><head><meta charset=\"utf-8\"><title>Plexar</title><style>\
body{{background:#1b1e23;color:#e6e8eb;font:15px/1.5 \"Segoe UI\",system-ui,sans-serif;\
display:flex;align-items:center;justify-content:center;height:100vh;margin:0;text-align:center}}\
main{{max-width:420px;padding:0 24px}}\
h1{{font-size:22px;font-weight:600;background:linear-gradient(90deg,#ff6a00,#ffb066);\
-webkit-background-clip:text;color:transparent;margin:0 0 12px}}\
p{{color:#8a929c;margin:0}}\
</style></head><body><main><h1>{heading}</h1><p>{message}</p></main></body></html>"
    )
}

/// Reads one HTTP request off `stream`, answers it with `callback_page`, and returns the parsed
/// outcome (or `None` when the request was not `GET /callback`, so the caller keeps listening).
fn handle_one_connection(mut stream: TcpStream, expected_state: &str) -> Option<CallbackOutcome> {
    let mut reader = BufReader::new(stream.try_clone().ok()?);
    let mut request_line = String::new();
    reader.read_line(&mut request_line).ok()?;
    // Drain the remaining header lines so the client's write completes cleanly; bodies are never
    // sent on this GET.
    loop {
        let mut header_line = String::new();
        match reader.read_line(&mut header_line) {
            Ok(0) => break,
            Ok(_) if header_line.trim().is_empty() => break,
            Ok(_) => continue,
            Err(_) => break,
        }
    }

    let outcome = parse_callback_request_line(&request_line, expected_state)?;
    let success = matches!(outcome, CallbackOutcome::Code(_));
    let message = match &outcome {
        CallbackOutcome::Code(_) => "You're signed in to Plexar. You can close this tab and return to the app.".to_string(),
        CallbackOutcome::Error(reason) => format!("Sign-in was cancelled or expired ({reason}). Try again in the app."),
    };
    let body = callback_page(success, &message);
    let response = format!(
        "HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
        body.len(),
        body
    );
    let _ = stream.write_all(response.as_bytes());
    let _ = stream.flush();
    Some(outcome)
}

/// Binds a one-shot listener on `127.0.0.1:0` (OS-chosen port) and returns it plus the chosen
/// port, so the caller can put the port in the redirect URI before waiting.
pub fn bind_loopback() -> std::io::Result<(TcpListener, u16)> {
    let listener = TcpListener::bind("127.0.0.1:0")?;
    let port = listener.local_addr()?.port();
    listener.set_nonblocking(true)?;
    Ok((listener, port))
}

/// Waits up to `timeout` for the first `GET /callback` request on `listener`, verifying `state`
/// and answering the browser. Any other path is accepted and closed without a matched outcome,
/// then listening continues (only `/callback` is honored). Polls `cancel` between accept
/// attempts so the app's Cancel control can abort the wait and free the port.
pub fn wait_for_callback(listener: &TcpListener, timeout: Duration, expected_state: &str, cancel: &Arc<AtomicBool>) -> WaitOutcome {
    let deadline = Instant::now() + timeout;
    loop {
        if cancel.load(Ordering::SeqCst) {
            return WaitOutcome::Cancelled;
        }
        if Instant::now() >= deadline {
            return WaitOutcome::TimedOut;
        }
        match listener.accept() {
            Ok((stream, _)) => {
                let _ = stream.set_nodelay(true);
                if let Some(outcome) = handle_one_connection(stream, expected_state) {
                    return match outcome {
                        CallbackOutcome::Code(code) => WaitOutcome::Code(code),
                        CallbackOutcome::Error(reason) => WaitOutcome::Error(reason),
                    };
                }
                // Not /callback: keep listening for the real one.
            }
            Err(ref e) if e.kind() == std::io::ErrorKind::WouldBlock => {
                std::thread::sleep(Duration::from_millis(50));
            }
            Err(_) => {
                std::thread::sleep(Duration::from_millis(50));
            }
        }
    }
}

/// A newly minted key and the account it belongs to, as returned by a successful token exchange.
#[derive(Debug, Clone)]
pub struct ExchangeSuccess {
    pub key: String,
    pub email: String,
}

/// Failure returned by the token endpoint, or a transport failure reaching it.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ExchangeError {
    /// A rejected sign-in (400, 403 paused, 409 key cap, 429 rate limit); `message` is the card's display text.
    InvalidGrant(String),
    /// Connection failure, timeout, or a non-200/400 status.
    NetworkError,
}

/// The card's message for a non-200 token response, or `None` for a status that means "can't
/// reach Plexar" (5xx, unexpected codes). `error_code` is the body's `error.code`, when present.
pub fn token_error_message(status: u16, error_code: Option<&str>) -> Option<String> {
    let message = match (status, error_code) {
        (400, _) => "Sign-in expired or was already used. Try again.",
        (403, Some("paused")) => "Your Plexar Harness access is paused. Ask the Plexar owner.",
        (403, _) => "Your account doesn't have Plexar Harness access yet. Ask the Plexar owner to enable it.",
        (409, Some("too_many_harness_keys")) | (409, _) => {
            "You're signed in on 5 computers already. Sign out on one of them, or remove a key in the Plexar portal, then try again."
        }
        (429, _) => "Plexar is busy. Try again shortly.",
        _ => return None,
    };
    Some(message.to_string())
}

/// `POST {base_url}/api/harness/token {"code","code_verifier","redirect_uri"}`. `redirect_uri`
/// must be byte-identical to the one used to build the authorize URL. Never sends a cookie or
/// bearer token. The plaintext key in a 200 body is the only place it ever appears — this
/// function returns it to the caller and nowhere logs it.
pub fn exchange(base_url: &str, code: &str, verifier: &str, redirect_uri: &str) -> Result<ExchangeSuccess, ExchangeError> {
    let url = format!("{}/api/harness/token", base_url.trim_end_matches('/'));
    let agent = ureq::Agent::config_builder()
        .timeout_global(Some(Duration::from_secs(15)))
        // Error responses carry `error.code` (paused, too_many_harness_keys); keep their bodies.
        .http_status_as_error(false)
        .build()
        .new_agent();
    let body = serde_json::json!({ "code": code, "code_verifier": verifier, "redirect_uri": redirect_uri });
    let mut response = match agent.post(&url).send_json(body) {
        Ok(response) => response,
        Err(_) => return Err(ExchangeError::NetworkError),
    };
    let status = response.status().as_u16();
    let mut text = String::new();
    if response.body_mut().as_reader().read_to_string(&mut text).is_err() {
        return Err(ExchangeError::NetworkError);
    }
    let parsed: serde_json::Value = serde_json::from_str(&text).unwrap_or(serde_json::Value::Null);
    if status != 200 {
        let code = parsed.pointer("/error/code").and_then(|v| v.as_str());
        return Err(match token_error_message(status, code) {
            Some(message) => ExchangeError::InvalidGrant(message),
            None => ExchangeError::NetworkError,
        });
    }
    match parsed.get("key").and_then(|v| v.as_str()) {
        Some(key) => Ok(ExchangeSuccess {
            key: key.to_string(),
            email: parsed.get("email").and_then(|v| v.as_str()).unwrap_or("").to_string(),
        }),
        None => Err(ExchangeError::NetworkError),
    }
}

/// `POST {base_url}/api/harness/logout` with `Authorization: Bearer <key>`, revoking the key
/// server-side. Best-effort: any transport failure or non-2xx status is swallowed, since the
/// caller (`sign_out`) deletes the local keyring entry regardless.
pub fn logout(base_url: &str, key: &str) {
    let url = format!("{}/api/harness/logout", base_url.trim_end_matches('/'));
    let agent = ureq::Agent::config_builder()
        .timeout_global(Some(Duration::from_secs(10)))
        .build()
        .new_agent();
    let _ = agent.post(&url).header("Authorization", &format!("Bearer {key}")).send_empty();
}

#[cfg(test)]
mod tests {
    use super::*;

    /// RFC 7636 appendix B vector.
    #[test]
    fn challenge_matches_rfc7636_appendix_b_vector() {
        let verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk";
        assert_eq!(challenge_from_verifier(verifier), "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM");
    }

    #[test]
    fn generated_verifier_is_43_url_safe_characters() {
        let verifier = generate_verifier();
        assert_eq!(verifier.len(), 43);
        assert!(verifier.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'-' || b == b'_'));
    }

    #[test]
    fn generated_verifiers_are_not_repeated() {
        assert_ne!(generate_verifier(), generate_verifier());
    }

    #[test]
    fn generated_states_are_not_repeated() {
        assert_ne!(generate_state(), generate_state());
    }

    #[test]
    fn parse_query_reads_code_when_state_matches() {
        assert_eq!(parse_callback_query("code=plxdc_abc&state=s1", "s1"), CallbackOutcome::Code("plxdc_abc".to_string()));
    }

    #[test]
    fn parse_query_reads_error() {
        assert_eq!(
            parse_callback_query("error=access_denied&state=s1", "s1"),
            CallbackOutcome::Error("access_denied".to_string())
        );
    }

    #[test]
    fn parse_query_rejects_mismatched_state() {
        assert_eq!(
            parse_callback_query("code=plxdc_abc&state=wrong", "s1"),
            CallbackOutcome::Error("state_mismatch".to_string())
        );
    }

    #[test]
    fn parse_query_missing_state_is_error() {
        assert_eq!(parse_callback_query("code=plxdc_abc", "s1"), CallbackOutcome::Error("missing_state".to_string()));
    }

    #[test]
    fn parse_query_missing_code_is_error() {
        assert_eq!(parse_callback_query("state=s1", "s1"), CallbackOutcome::Error("missing_code".to_string()));
    }

    #[test]
    fn parse_query_error_wins_over_code_and_state() {
        assert_eq!(
            parse_callback_query("code=plxdc_abc&state=wrong&error=access_denied", "s1"),
            CallbackOutcome::Error("access_denied".to_string())
        );
    }

    #[test]
    fn parse_request_line_rejects_other_paths() {
        assert_eq!(parse_callback_request_line("GET /favicon.ico HTTP/1.1", "s1"), None);
        assert_eq!(parse_callback_request_line("GET / HTTP/1.1", "s1"), None);
    }

    #[test]
    fn parse_request_line_rejects_non_get() {
        assert_eq!(parse_callback_request_line("POST /callback?code=x&state=s1 HTTP/1.1", "s1"), None);
    }

    #[test]
    fn parse_request_line_accepts_callback_with_matching_state() {
        assert_eq!(
            parse_callback_request_line("GET /callback?code=plxdc_x&state=s1 HTTP/1.1", "s1"),
            Some(CallbackOutcome::Code("plxdc_x".to_string()))
        );
    }

    #[test]
    fn build_authorize_url_encodes_all_params() {
        let url = build_authorize_url("https://rig.example", "http://127.0.0.1:51234/callback", "st ate", "chal/lenge");
        assert_eq!(
            url,
            "https://rig.example/api/harness/authorize?redirect_uri=http%3A%2F%2F127.0.0.1%3A51234%2Fcallback&state=st%20ate&code_challenge=chal%2Flenge&code_challenge_method=S256"
        );
    }

    #[test]
    fn redirect_uri_is_literal_127_0_0_1() {
        assert_eq!(redirect_uri(51234), "http://127.0.0.1:51234/callback");
    }

    /// The "Use a code instead" oob variant of contract §10p: `redirect_uri=oob`, same as
    /// `plexar-harness login --no-browser`.
    #[test]
    fn build_authorize_url_supports_oob_redirect_uri() {
        let url = build_authorize_url("https://rig.example", "oob", "s1", "chal");
        assert_eq!(
            url,
            "https://rig.example/api/harness/authorize?redirect_uri=oob&state=s1&code_challenge=chal&code_challenge_method=S256"
        );
    }

    /// `sign_in_code`'s exchange call: `redirect_uri: "oob"` against a mock 200 response.
    #[test]
    fn exchange_against_mock_server_200_with_oob_redirect_uri_returns_key() {
        let port = serve_once(200, r#"{"key":"plx_device_oob","key_id":"k1","email":"a@example.com","sub":"s1"}"#);
        let result = exchange(&format!("http://127.0.0.1:{port}"), "plxdc_pasted_code", "verifier", "oob");
        assert!(matches!(result, Ok(ExchangeSuccess { key, email }) if key == "plx_device_oob" && email == "a@example.com"));
    }

    /// `sign_in_code`'s exchange call against a mock 400 (expired/reused code), with `redirect_uri: "oob"`.
    #[test]
    fn exchange_against_mock_server_400_with_oob_redirect_uri_is_invalid_grant() {
        let port = serve_once(400, r#"{"error":{"code":"invalid_grant","message":"Sign-in expired or was already used. Try again."}}"#);
        let result = exchange(&format!("http://127.0.0.1:{port}"), "plxdc_pasted_code", "verifier", "oob");
        assert!(matches!(result, Err(ExchangeError::InvalidGrant(_))), "{result:?}");
    }

    /// Binds the loopback listener, sends a fake `GET /callback?code=x&state=...` from another
    /// thread, and confirms the code comes back — the card's required loopback test.
    #[test]
    fn loopback_listener_returns_the_callback_code() {
        let (listener, port) = bind_loopback().expect("bind loopback");
        let cancel = Arc::new(AtomicBool::new(false));

        let client = std::thread::spawn(move || {
            // Give the accept loop a moment to start polling.
            std::thread::sleep(Duration::from_millis(50));
            let mut stream = TcpStream::connect(("127.0.0.1", port)).expect("connect to loopback");
            stream
                .write_all(b"GET /callback?code=plxdc_test123&state=s1 HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n")
                .expect("send fake callback request");
            let mut buf = String::new();
            std::io::Read::read_to_string(&mut stream, &mut buf).ok();
            buf
        });

        let outcome = wait_for_callback(&listener, Duration::from_secs(5), "s1", &cancel);
        let response = client.join().expect("client thread");

        assert!(matches!(outcome, WaitOutcome::Code(ref code) if code == "plxdc_test123"));
        assert!(response.starts_with("HTTP/1.1 200 OK"));
    }

    #[test]
    fn loopback_listener_honors_cancel() {
        let (listener, _port) = bind_loopback().expect("bind loopback");
        let cancel = Arc::new(AtomicBool::new(false));
        let cancel_setter = cancel.clone();
        std::thread::spawn(move || {
            std::thread::sleep(Duration::from_millis(80));
            cancel_setter.store(true, Ordering::SeqCst);
        });
        let outcome = wait_for_callback(&listener, Duration::from_secs(5), "s1", &cancel);
        assert!(matches!(outcome, WaitOutcome::Cancelled));
    }

    /// Exchange against a local mock server: 200 with a key.
    #[test]
    fn token_error_messages_follow_the_server_codes() {
        assert!(token_error_message(403, Some("paused")).unwrap().contains("paused"));
        assert!(token_error_message(409, Some("too_many_harness_keys")).unwrap().contains("5 computers"));
        assert!(token_error_message(429, None).unwrap().contains("busy"));
        assert!(token_error_message(400, Some("invalid_grant")).unwrap().contains("expired"));
        assert_eq!(token_error_message(502, None), None);
    }

    #[test]
    fn exchange_against_mock_server_200_returns_key() {
        let port = serve_once(200, r#"{"key":"plx_device_abc","key_id":"k1","email":"a@example.com","sub":"s1"}"#);
        let result = exchange(&format!("http://127.0.0.1:{port}"), "plxdc_code", "verifier", "http://127.0.0.1:9/callback");
        assert!(matches!(result, Ok(ExchangeSuccess { key, email }) if key == "plx_device_abc" && email == "a@example.com"));
    }

    /// Exchange against a local mock server: 400 invalid_grant.
    #[test]
    fn exchange_against_mock_server_400_is_invalid_grant() {
        let port = serve_once(400, r#"{"error":{"code":"invalid_grant","message":"Sign-in expired or was already used. Try again."}}"#);
        let result = exchange(&format!("http://127.0.0.1:{port}"), "plxdc_code", "verifier", "http://127.0.0.1:9/callback");
        assert!(matches!(result, Err(ExchangeError::InvalidGrant(_))), "{result:?}");
    }

    /// Binds an ephemeral port and answers exactly one request with `status`/`body`, then stops.
    fn serve_once(status: u16, body: &'static str) -> u16 {
        let listener = TcpListener::bind("127.0.0.1:0").expect("bind ephemeral port");
        let port = listener.local_addr().expect("local addr").port();
        std::thread::spawn(move || {
            if let Ok((mut stream, _)) = listener.accept() {
                let mut buf = [0u8; 1024];
                let _ = stream.read(&mut buf);
                let status_line = if status == 200 { "200 OK" } else { "400 Bad Request" };
                let response = format!(
                    "HTTP/1.1 {}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
                    status_line,
                    body.len(),
                    body
                );
                let _ = stream.write_all(response.as_bytes());
                let _ = stream.flush();
                // Half-close and drain until the client closes its side, so the response is
                // fully delivered before this thread drops the socket (otherwise a `Connection:
                // close` response can be truncated by an early RST under load).
                let _ = stream.shutdown(std::net::Shutdown::Write);
                let mut drain = [0u8; 64];
                while let Ok(n) = stream.read(&mut drain) {
                    if n == 0 {
                        break;
                    }
                }
            }
        });
        port
    }
}
