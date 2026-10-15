//! Entitlement check against the rig's `GET /api/harness/me`, per N57.
//!
//! Replaces the earlier `/api/me` product check (N54): the desktop app now validates a stored
//! or env key by calling `/api/harness/me` with `Authorization: Bearer <key>`, both right after
//! sign-in and at every launch. `decide` is the pure decision over the parsed body so it is
//! unit-testable without a network call; `check` performs the call and separately reports a 401
//! (treated as "signed out": the caller deletes the stored key) and a transport failure (offline
//! tolerance: the caller starts the Host anyway).

use std::io::Read;
use std::time::Duration;

/// Outcome of applying the rig's stated entitlement policy to a parsed `/api/harness/me` body.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Decision {
    /// `entitled: true`. Carries the signed-in email for the "Signed in as <email>" line.
    Entitled { email: String },
    /// `entitled: false`, with the card message for the given `reason`.
    NotEntitled { message: String },
}

/// Outcome of calling `/api/harness/me`.
#[derive(Debug)]
pub enum CheckResult {
    Decision(Decision),
    /// The key was rejected outright (revoked or unknown): the caller deletes the stored key and
    /// shows the sign-in card with "Please sign in again."
    SignedOut,
    /// Transport failure (DNS, connection refused, timeout): offline tolerance, the caller starts
    /// the Host anyway.
    NetworkError,
}

/// Maps `/api/harness/me`'s `reason` field to the card's message. `null`/`entitled: true` never
/// reaches this function. Any reason besides `"paused"` and `"grant_disabled"` (including the
/// documented `"product_not_granted"` and anything unrecognized) uses the generic message.
fn reason_message(reason: Option<&str>) -> String {
    match reason {
        Some("paused") => "Your Plexar access is paused.".to_string(),
        Some("grant_disabled") => "Your Plexar access has been turned off. Ask the Plexar owner.".to_string(),
        _ => "Your account doesn't have Plexar Harness access yet. Ask the Plexar owner to enable it.".to_string(),
    }
}

/// Pure decision over a parsed `/api/harness/me` 200 body. Only called for a 200 response; a 401
/// is `CheckResult::SignedOut` before this is reached.
pub fn decide(body: &serde_json::Value) -> Decision {
    let entitled = body.get("entitled").and_then(|v| v.as_bool()).unwrap_or(false);
    if entitled {
        let email = body.get("email").and_then(|v| v.as_str()).unwrap_or("").to_string();
        return Decision::Entitled { email };
    }
    let reason = body.get("reason").and_then(|v| v.as_str());
    Decision::NotEntitled { message: reason_message(reason) }
}

/// Calls `GET <base_url>/api/harness/me` with `Authorization: Bearer <key>` and a 10 s timeout.
/// A 401 is `SignedOut`; any other transport failure or non-200/401 status is `NetworkError`; a
/// 200 is parsed and decided.
pub fn check(base_url: &str, key: &str) -> CheckResult {
    let url = format!("{}/api/harness/me", base_url.trim_end_matches('/'));
    let agent = ureq::Agent::config_builder()
        .timeout_global(Some(Duration::from_secs(10)))
        .build()
        .new_agent();
    let result = agent.get(&url).header("Authorization", &format!("Bearer {key}")).call();
    let mut response = match result {
        Ok(response) if response.status() == 200 => response,
        Ok(response) if response.status() == 401 => return CheckResult::SignedOut,
        Err(ureq::Error::StatusCode(401)) => return CheckResult::SignedOut,
        _ => return CheckResult::NetworkError,
    };
    let mut text = String::new();
    if response.body_mut().as_reader().read_to_string(&mut text).is_err() {
        return CheckResult::NetworkError;
    }
    match serde_json::from_str::<serde_json::Value>(&text) {
        Ok(body) => CheckResult::Decision(decide(&body)),
        Err(_) => CheckResult::NetworkError,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    use std::net::TcpListener;

    #[test]
    fn decide_entitled_true_carries_email() {
        let body = serde_json::json!({ "email": "a@example.com", "sub": "s1", "entitled": true, "reason": null });
        assert_eq!(decide(&body), Decision::Entitled { email: "a@example.com".to_string() });
    }

    #[test]
    fn decide_paused_uses_paused_message() {
        let body = serde_json::json!({ "entitled": false, "reason": "paused" });
        assert_eq!(decide(&body), Decision::NotEntitled { message: "Your Plexar access is paused.".to_string() });
    }

    #[test]
    fn decide_grant_disabled_uses_that_message() {
        let body = serde_json::json!({ "entitled": false, "reason": "grant_disabled" });
        assert_eq!(
            decide(&body),
            Decision::NotEntitled { message: "Your Plexar access has been turned off. Ask the Plexar owner.".to_string() }
        );
    }

    #[test]
    fn decide_product_not_granted_uses_generic_message() {
        let body = serde_json::json!({ "entitled": false, "reason": "product_not_granted" });
        assert_eq!(
            decide(&body),
            Decision::NotEntitled {
                message: "Your account doesn't have Plexar Harness access yet. Ask the Plexar owner to enable it.".to_string()
            }
        );
    }

    #[test]
    fn decide_unrecognized_reason_uses_generic_message() {
        let body = serde_json::json!({ "entitled": false, "reason": "something_new" });
        assert_eq!(
            decide(&body),
            Decision::NotEntitled {
                message: "Your account doesn't have Plexar Harness access yet. Ask the Plexar owner to enable it.".to_string()
            }
        );
    }

    #[test]
    fn decide_null_reason_uses_generic_message() {
        let body = serde_json::json!({ "entitled": false, "reason": null });
        assert_eq!(
            decide(&body),
            Decision::NotEntitled {
                message: "Your account doesn't have Plexar Harness access yet. Ask the Plexar owner to enable it.".to_string()
            }
        );
    }

    /// Binds an ephemeral local listener and answers exactly one request with `status`/`body`,
    /// then stops. Returns the port to point `check` at.
    fn serve_once(status: u16, body: &'static str) -> u16 {
        let listener = TcpListener::bind("127.0.0.1:0").expect("bind ephemeral port");
        let port = listener.local_addr().expect("local addr").port();
        std::thread::spawn(move || {
            if let Ok((mut stream, _)) = listener.accept() {
                let mut buf = [0u8; 1024];
                let _ = std::io::Read::read(&mut stream, &mut buf);
                let status_line = match status {
                    200 => "200 OK",
                    401 => "401 Unauthorized",
                    404 => "404 Not Found",
                    _ => "500 Internal Server Error",
                };
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
                while let Ok(n) = std::io::Read::read(&mut stream, &mut drain) {
                    if n == 0 {
                        break;
                    }
                }
            }
        });
        port
    }

    #[test]
    fn check_against_mock_server_200_entitled() {
        let port = serve_once(200, r#"{"email":"a@example.com","sub":"s1","products":["llm"],"entitled":true,"reason":null,"models":[]}"#);
        let result = check(&format!("http://127.0.0.1:{port}"), "plx_test");
        assert!(matches!(result, CheckResult::Decision(Decision::Entitled { .. })));
    }

    #[test]
    fn check_against_mock_server_200_not_entitled() {
        let port = serve_once(200, r#"{"email":"a@example.com","sub":"s1","products":[],"entitled":false,"reason":"paused","models":[]}"#);
        let result = check(&format!("http://127.0.0.1:{port}"), "plx_test");
        assert!(matches!(result, CheckResult::Decision(Decision::NotEntitled { .. })));
    }

    #[test]
    fn check_against_mock_server_401_is_signed_out() {
        let port = serve_once(401, r#"{"error":"unauthorized"}"#);
        let result = check(&format!("http://127.0.0.1:{port}"), "plx_test");
        assert!(matches!(result, CheckResult::SignedOut));
    }

    /// The rig may not have this route deployed yet (404) or may be failing (5xx) or answering
    /// non-JSON; every one of those behaves like offline tolerance, never a sign-out — only a
    /// literal 401 signs out.
    #[test]
    fn check_against_mock_server_404_is_network_error_not_signed_out() {
        let port = serve_once(404, "not found");
        let result = check(&format!("http://127.0.0.1:{port}"), "plx_test");
        assert!(matches!(result, CheckResult::NetworkError));
    }

    #[test]
    fn check_against_connection_refused_is_network_error() {
        // An ephemeral port that was bound and then immediately dropped is not listening.
        let listener = TcpListener::bind("127.0.0.1:0").expect("bind ephemeral port");
        let port = listener.local_addr().expect("local addr").port();
        drop(listener);
        let result = check(&format!("http://127.0.0.1:{port}"), "plx_test");
        assert!(matches!(result, CheckResult::NetworkError));
    }
}
