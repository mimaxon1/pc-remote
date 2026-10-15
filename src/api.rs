use std::{
    io::Read,
    net::{IpAddr, Ipv4Addr, SocketAddr},
    sync::{Arc, atomic::Ordering},
    thread,
    time::Duration,
};

use qrcode::{QrCode, render::svg};
use serde_json::{Value, json};
use tiny_http::{Header, Method, Request, Response, Server, StatusCode};

use crate::{
    config, platform,
    state::{AppItem, AppState},
};

const INDEX_HTML: &[u8] = include_bytes!("../web/index.html");
const FAVICON: &[u8] = include_bytes!("../web/favicon.ico");
const ICON_192: &[u8] = include_bytes!("../web/icons/icon-192.png");

#[derive(Clone, Debug)]
pub struct ApiError {
    pub status: u16,
    pub message: String,
    pub retry_after: Option<u64>,
}

impl ApiError {
    fn new(status: u16, message: impl Into<String>) -> Self {
        Self {
            status,
            message: message.into(),
            retry_after: None,
        }
    }
    fn limited(seconds: u64) -> Self {
        Self {
            status: 429,
            message: "Too many login attempts. Try again later.".into(),
            retry_after: Some(seconds),
        }
    }
}

fn bad(message: impl Into<String>) -> ApiError {
    ApiError::new(400, message)
}
fn forbidden(message: impl Into<String>) -> ApiError {
    ApiError::new(403, message)
}

fn text<'a>(body: &'a Value, key: &str) -> Option<&'a str> {
    body.get(key).and_then(Value::as_str)
}

fn request_pin(body: &Value, key: &str) -> Result<String, ApiError> {
    let value = text(body, key).unwrap_or("").trim();
    if value.len() != config::PIN_LENGTH || !value.bytes().all(|byte| byte.is_ascii_digit()) {
        return Err(bad("PIN must contain exactly four digits"));
    }
    Ok(value.to_owned())
}

fn local_peer(peer: IpAddr) -> bool {
    AppState::is_loopback(peer)
}

fn authenticate(state: &AppState, body: &Value, peer: IpAddr) -> Result<(), ApiError> {
    if state.settings_error.load(Ordering::Relaxed) {
        return Err(ApiError::new(
            500,
            "settings.json is damaged; repair it before continuing",
        ));
    }
    if !state.auth_ready() {
        return Err(ApiError::new(409, "PIN setup required"));
    }
    if let Some(token) = text(body, "token") {
        if state.verify_token(token) {
            return Ok(());
        }
    }
    if text(body, "password").is_some() {
        let pin = request_pin(body, "password")?;
        return verify_pin_for_peer(state, &pin, peer).map_err(|error| {
            if error.status == 403 {
                ApiError::new(403, "Invalid PIN or expired session")
            } else {
                error
            }
        });
    }
    if text(body, "token").is_some() {
        return Err(forbidden("Invalid PIN or expired session"));
    }
    Err(forbidden("Active session required"))
}

fn verify_pin_for_peer(state: &AppState, pin: &str, peer: IpAddr) -> Result<(), ApiError> {
    let peer = peer.to_string();
    match state.verify_pin_for_peer(pin, &peer) {
        Ok(true) => Ok(()),
        Ok(false) => Err(forbidden("Invalid PIN")),
        Err(seconds) => Err(ApiError::limited(seconds)),
    }
}

fn token_string(state: &AppState, body: &Value) -> Result<String, ApiError> {
    let value = text(body, "token").unwrap_or_default();
    if value.len() < 32 || value.len() > 256 {
        return Err(bad("Invalid token"));
    }
    if state.verify_token(value) {
        return Ok(value.to_owned());
    }
    Err(forbidden("Invalid QR token"))
}

fn app_item(body: &Value) -> Result<AppItem, ApiError> {
    let path = text(body, "path").unwrap_or_default().trim();
    let name = text(body, "name").unwrap_or_default().trim();
    let args = text(body, "args").map(str::to_owned);
    let aumid = text(body, "aumid").map(str::to_owned);
    if path.is_empty() || path.len() > 4096 {
        return Err(bad("Application path is required"));
    }
    if name.len() > 4096 || args.as_ref().is_some_and(|value| value.len() > 4096) {
        return Err(bad("Application field is too long"));
    }
    Ok(AppItem {
        path: path.to_owned(),
        name: if name.is_empty() {
            std::path::Path::new(path)
                .file_stem()
                .and_then(|v| v.to_str())
                .unwrap_or("Application")
                .to_owned()
        } else {
            name.to_owned()
        },
        args,
        aumid,
        is_running: false,
    })
}

fn read_body(request: &mut Request) -> Result<Value, ApiError> {
    let mut bytes = Vec::new();
    request
        .as_reader()
        .take(65_537)
        .read_to_end(&mut bytes)
        .map_err(|_| ApiError::new(400, "Could not read request body"))?;
    if bytes.len() > 65_536 {
        return Err(ApiError::new(413, "Request body is too large"));
    }
    let body = if bytes.is_empty() {
        json!({})
    } else {
        serde_json::from_slice(&bytes)
            .map_err(|_| ApiError::new(400, "Invalid JSON request body"))?
    };
    if !body.is_object() {
        return Err(ApiError::new(400, "Request body must be a JSON object"));
    }
    Ok(body)
}

fn set_pair_token(state: &AppState, token: &str) -> bool {
    state.pair_touch(token)
}

fn route_api(
    method: &Method,
    path: &str,
    body: &Value,
    peer: IpAddr,
    state: &Arc<AppState>,
) -> Result<Value, ApiError> {
    match (method, path) {
        (Method::Get, "/" | "/health") => Ok(
            json!({"status":"healthy","version":config::version(),"auth_ready":state.auth_ready()}),
        ),
        (Method::Get, "/auth_state") => Ok(json!({"requires_password_setup":!state.auth_ready()})),
        (Method::Post, "/pair") => {
            if !local_peer(peer) {
                return Err(forbidden("Local only"));
            }
            let token = state.issue_token(true);
            state.log("QR pairing token issued");
            Ok(
                json!({"token":token,"expires_in":config::PAIR_TTL_SECS,"requires_password_setup":!state.auth_ready()}),
            )
        }
        (Method::Post, "/pair_touch") => {
            let token = token_string(state, body)?;
            if !set_pair_token(state, &token) {
                return Err(forbidden("Invalid QR token"));
            }
            Ok(json!({"status":"ok"}))
        }
        (Method::Post, "/pair_complete") => {
            let token = token_string(state, body)?;
            if !state.pair_complete(&token) {
                return Err(forbidden("Invalid QR token"));
            }
            Ok(json!({"status":"ok"}))
        }
        (Method::Post, "/pair_status") => {
            if !local_peer(peer) {
                return Err(forbidden("Local only"));
            }
            let token = token_string(state, body)?;
            let (opened, completed) = state.pair_status(&token);
            Ok(json!({"opened":opened,"completed":completed}))
        }
        (Method::Post, "/login") => {
            if !state.auth_ready() {
                return Err(ApiError::new(409, "PIN setup is not complete yet"));
            }
            let pin = request_pin(body, "password")?;
            if !state
                .verify_pin_for_peer(&pin, &peer.to_string())
                .map_err(ApiError::limited)?
            {
                state.log(&format!("Login failed: invalid PIN | IP: {peer}"));
                return Err(forbidden("Invalid PIN"));
            }
            state.log("Login: ok");
            Ok(json!({"token":state.issue_token(false),"expires_in":config::SESSION_TTL_SECS}))
        }
        (Method::Post, "/setup_password") => {
            if state.auth_ready() {
                return Err(ApiError::new(400, "PIN setup is already complete"));
            }
            if state.settings_error.load(Ordering::Relaxed) {
                return Err(ApiError::new(500, "settings.json needs repair"));
            }
            let pair_token = token_string(state, body)?;
            let pin = request_pin(body, "new_password")?;
            state
                .set_pin(&pin)
                .map_err(|_| ApiError::new(500, "Could not save PIN settings"))?;
            state.pair_complete(&pair_token);
            let token = state.issue_token(false);
            state.log("PIN setup completed");
            Ok(json!({"status":"ok","token":token,"expires_in":config::SESSION_TTL_SECS}))
        }
        (Method::Post, "/connect" | "/disconnect") => {
            authenticate(state, body, peer)?;
            let connected = path == "/connect";
            state.phone_connected.store(connected, Ordering::Relaxed);
            state.log(if connected {
                "Phone connected"
            } else {
                "Phone disconnected"
            });
            Ok(json!({"status":if connected {"connected"} else {"disconnected"}}))
        }
        (Method::Post, "/logout") => {
            authenticate(state, body, peer)?;
            if let Some(token) = text(body, "token") {
                state.revoke_token(token);
            }
            state.phone_connected.store(false, Ordering::Relaxed);
            Ok(json!({"status":"bye"}))
        }
        (Method::Post, "/status") => {
            authenticate(state, body, peer)?;
            let (volume, muted) = platform::audio_state(state);
            Ok(json!({"volume":volume,"muted":muted}))
        }
        (Method::Post, "/stats" | "/info") => {
            authenticate(state, body, peer)?;
            let info = platform::system_info(state);
            if path == "/info" {
                Ok(info)
            } else {
                Ok(
                    json!({"cpu_percent":info["cpu_percent"],"ram_percent":info["ram_percent"],"ram_used_mb":info["ram_used_mb"],"ram_total_mb":info["ram_total_mb"],"uptime_sec":info["uptime_sec"]}),
                )
            }
        }
        (Method::Post, "/volume") => {
            authenticate(state, body, peer)?;
            let current = platform::volume(state);
            let updated = if let Some(value) = body.get("value").and_then(Value::as_f64) {
                platform::set_volume(state, value as f32)
                    .map_err(|_| ApiError::new(500, "Audio operation failed"))?
            } else if let Some(action) = text(body, "action") {
                let delta = match action {
                    "up" => 0.05,
                    "down" => -0.05,
                    _ => return Err(bad("Unknown volume action")),
                };
                platform::set_volume(state, current + delta)
                    .map_err(|_| ApiError::new(500, "Audio operation failed"))?
            } else {
                return Err(bad("Provide either value or action"));
            };
            state.log(&format!("Volume changed: {:.0}%", updated * 100.0));
            Ok(json!({"volume":updated,"muted":state.muted.load(Ordering::Relaxed)}))
        }
        (Method::Post, "/mute") => {
            authenticate(state, body, peer)?;
            let muted = platform::toggle_mute(state)
                .map_err(|_| ApiError::new(500, "Audio operation failed"))?;
            state.log(if muted { "Mute on" } else { "Mute off" });
            Ok(json!({"muted":muted}))
        }
        (Method::Post, "/media") => {
            authenticate(state, body, peer)?;
            platform::send_media(text(body, "action").unwrap_or_default()).map_err(|error| {
                if error == "Unknown action" {
                    bad(error)
                } else {
                    ApiError::new(500, error)
                }
            })?;
            Ok(json!({"status":"ok"}))
        }
        (Method::Post, "/audio/devices") => {
            authenticate(state, body, peer)?;
            let device = platform::default_output_device();
            Ok(
                json!({"devices":[{"id":"default","name":device["name"],"is_default":true}],"active_output_device":device}),
            )
        }
        (Method::Post, "/audio/device") => {
            authenticate(state, body, peer)?;
            if text(body, "device_id") != Some("default") {
                return Err(bad("Unknown audio device"));
            }
            Ok(
                json!({"status":"ok","active_output_device":platform::default_output_device(),"devices":[{"id":"default","name":platform::default_output_device()["name"],"is_default":true}]}),
            )
        }
        (Method::Post, "/apps/recent") => {
            authenticate(state, body, peer)?;
            Ok(platform::list_apps(state))
        }
        (Method::Post, "/apps/open") => {
            authenticate(state, body, peer)?;
            let item = if text(body, "path").unwrap_or_default().is_empty() {
                state
                    .pinned()
                    .into_iter()
                    .next()
                    .or_else(|| platform::scan_shortcuts().into_iter().next())
                    .ok_or_else(|| bad("No recent applications found"))?
            } else {
                app_item(body)?
            };
            platform::launch(&item)
                .map_err(|_| ApiError::new(500, "Could not open the application"))?;
            state.log(&format!("Application launch requested: {}", item.name));
            let mut response = platform::list_apps(state);
            if let Some(object) = response.as_object_mut() {
                object.insert("status".into(), json!("ok"));
                object.insert(
                    "launched_app".into(),
                    serde_json::to_value(item).unwrap_or(Value::Null),
                );
            }
            Ok(response)
        }
        (Method::Post, "/apps/window") => {
            authenticate(state, body, peer)?;
            let item = app_item(body)?;
            platform::window_action(&item, text(body, "action").unwrap_or_default())
                .map_err(bad)?;
            let mut response = platform::list_apps(state);
            if let Some(object) = response.as_object_mut() {
                object.insert("status".into(), json!("ok"));
                object.insert("action".into(), json!(text(body, "action")));
                object.insert(
                    "app".into(),
                    serde_json::to_value(item).unwrap_or(Value::Null),
                );
            }
            Ok(response)
        }
        (Method::Post, "/apps/pin") => {
            authenticate(state, body, peer)?;
            let item = app_item(body)?;
            let pinned = state
                .pin_app(item.clone())
                .map_err(|_| ApiError::new(500, "Could not save the pinned application"))?;
            state.log(&format!("Application pinned: {}", item.name));
            Ok(json!({"status":"ok","pinned_app":item,"pinned_apps":pinned}))
        }
        (Method::Post, "/apps/unpin") => {
            authenticate(state, body, peer)?;
            let item = app_item(body)?;
            let (removed, pinned) = state
                .unpin_app(&item.path, item.args.as_deref(), item.aumid.as_deref())
                .map_err(|_| ApiError::new(500, "Could not update pinned applications"))?;
            Ok(json!({"status":"ok","removed":removed,"pinned_apps":pinned}))
        }
        (Method::Post, "/logs") => {
            authenticate(state, body, peer)?;
            let limit = body
                .get("limit")
                .and_then(Value::as_u64)
                .unwrap_or(200)
                .clamp(1, 1000) as usize;
            let since = body.get("since").and_then(Value::as_u64);
            let (entries, next_since, reset) = state.logs(since, limit);
            Ok(
                json!({"logs":entries.into_iter().map(|entry|entry.message).collect::<Vec<_>>(),"next_since":next_since,"reset":reset}),
            )
        }
        (Method::Post, "/shutdown" | "/reboot") => {
            authenticate(state, body, peer)?;
            platform::power_action(path == "/reboot").map_err(|error| ApiError::new(500, error))?;
            state.phone_connected.store(false, Ordering::Relaxed);
            Ok(json!({"status":if path == "/reboot" {"rebooting"} else {"bye"}}))
        }
        (Method::Post, "/change_password") => {
            if !state.auth_ready() {
                return Err(ApiError::new(409, "Complete first-run setup via QR first"));
            }
            let current = request_pin(body, "current_password")?;
            verify_pin_for_peer(state, &current, peer).map_err(|error| {
                if error.status == 403 {
                    forbidden("Invalid current PIN")
                } else {
                    error
                }
            })?;
            if let Some(token) = text(body, "token") {
                if !state.verify_token(token) {
                    return Err(forbidden("Invalid session"));
                }
            } else if !local_peer(peer) {
                return Err(forbidden("Active session required"));
            }
            let next = request_pin(body, "new_password")?;
            state
                .change_pin(&next)
                .map_err(|_| ApiError::new(500, "Could not save the new PIN"))?;
            state.phone_connected.store(false, Ordering::Relaxed);
            state.log("PIN changed");
            Ok(json!({"status":"ok"}))
        }
        (Method::Post, "/app/restart") => {
            let credentials_present = body.get("token").is_some_and(|value| !value.is_null())
                || body.get("password").is_some_and(|value| !value.is_null());
            if !local_peer(peer) || credentials_present {
                authenticate(state, body, peer)?;
            }
            let clean = body
                .get("clean_start")
                .and_then(Value::as_bool)
                .unwrap_or(false);
            if clean {
                state
                    .clear_pin()
                    .map_err(|_| ApiError::new(500, "Could not reset saved settings"))?;
            }
            state.restart_requested.store(true, Ordering::Relaxed);
            state.log(if clean {
                "Clean restart requested"
            } else {
                "Restart requested"
            });
            thread::spawn(|| {
                thread::sleep(Duration::from_millis(500));
                if let Ok(executable) = std::env::current_exe() {
                    if std::process::Command::new(executable).spawn().is_ok() {
                        std::process::exit(0);
                    }
                }
            });
            Ok(json!({"status":"restarting","clean_start":clean}))
        }
        _ => Err(ApiError::new(404, "Not found")),
    }
}

fn allowed_origin(origin: Option<&str>) -> bool {
    let Some(origin) = origin else {
        return true;
    };
    if origin == "null" {
        return false;
    }
    for port in [
        config::port("PC_REMOTE_WEB_PORT", config::WEB_PORT_DEFAULT),
        config::port("PC_REMOTE_API_PORT", config::API_PORT_DEFAULT),
    ] {
        if [
            format!("http://localhost:{port}"),
            format!("http://127.0.0.1:{port}"),
            format!("http://[::1]:{port}"),
            format!("http://{}:{port}", platform::local_ip()),
        ]
        .iter()
        .any(|allowed| origin == allowed)
        {
            return true;
        }
    }
    false
}

fn runtime_config() -> Value {
    #[cfg(target_os = "macos")]
    let platform_name = "macos";
    #[cfg(target_os = "windows")]
    let platform_name = "windows";
    json!({"appVersion":env!("CARGO_PKG_VERSION"),"platform":platform_name,"apiPort":config::port("PC_REMOTE_API_PORT",config::API_PORT_DEFAULT),"webPort":config::port("PC_REMOTE_WEB_PORT",config::WEB_PORT_DEFAULT),"pinLength":config::PIN_LENGTH,"pollIntervalMs":4000,"offlineRetryMinMs":4000,"offlineRetryMaxMs":30000,"pairPollIntervalMs":700})
}

#[cfg(test)]
mod runtime_config_tests {
    use super::*;

    #[test]
    fn runtime_config_identifies_the_native_platform() {
        #[cfg(target_os = "macos")]
        assert_eq!(runtime_config()["platform"], "macos");
        #[cfg(target_os = "windows")]
        assert_eq!(runtime_config()["platform"], "windows");
    }
}

fn html_escape(value: &str) -> String {
    value
        .replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
        .replace('\'', "&#39;")
}

fn qr_page(state: &AppState) -> Result<Vec<u8>, ApiError> {
    let token = state.issue_token(true);
    let host = platform::local_ip();
    let uri = format!(
        "http://{host}:{}/?token={token}",
        config::port("PC_REMOTE_WEB_PORT", config::WEB_PORT_DEFAULT)
    );
    let svg = QrCode::new(uri.as_bytes())
        .map_err(|_| ApiError::new(500, "Could not create pairing QR"))?
        .render::<svg::Color>()
        .min_dimensions(264, 264)
        .build();
    let instructions = if state.auth_ready() {
        "Scan with a phone on the same Wi-Fi or LAN. The QR code signs the phone in once."
    } else {
        "First start: scan the code, then choose a four-digit PIN on your phone."
    };
    Ok(format!("<!doctype html><html lang=\"en\"><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>PC Remote pairing</title><style>body{{font:16px system-ui;background:#f3f5f7;color:#17202a;display:grid;place-items:center;min-height:96vh;margin:0}}main{{text-align:center;background:white;padding:28px;border-radius:20px;box-shadow:0 12px 40px #17202a15;max-width:360px}}svg{{width:264px;height:264px}}p{{line-height:1.5;color:#465262;overflow-wrap:anywhere}}a{{color:#155eef}}</style><main><h1>PC Remote</h1>{svg}<p>{}</p><p><a href=\"http://{host}:{}\">Open the phone control panel</a></p><p>Pairing address: {}</p></main></html>",instructions,config::port("PC_REMOTE_WEB_PORT",config::WEB_PORT_DEFAULT),html_escape(&uri)).into_bytes())
}

fn respond(request: Request, state: &Arc<AppState>, web_server: bool) {
    let peer = request
        .remote_addr()
        .map(SocketAddr::ip)
        .unwrap_or(IpAddr::V4(Ipv4Addr::UNSPECIFIED));
    let origin = request
        .headers()
        .iter()
        .find(|header| header.field.equiv("Origin"))
        .map(|header| header.value.as_str().to_owned());
    let origin_ok = allowed_origin(origin.as_deref());
    if !origin_ok {
        let _ = json_response(
            request,
            ApiError::new(403, "Origin not allowed"),
            origin.as_deref(),
        );
        return;
    }
    if request.method() == &Method::Options {
        let mut response = Response::empty(StatusCode(204));
        if let Some(value) = origin {
            response = response
                .with_header(Header::from_bytes("Access-Control-Allow-Origin", value).unwrap());
        }
        response = response.with_header(
            Header::from_bytes("Access-Control-Allow-Methods", "GET, POST, OPTIONS").unwrap(),
        );
        response = response.with_header(
            Header::from_bytes("Access-Control-Allow-Headers", "Content-Type").unwrap(),
        );
        response =
            response.with_header(Header::from_bytes("Access-Control-Max-Age", "600").unwrap());
        let _ = request.respond(response);
        return;
    }
    let method = request.method().clone();
    let request_path = request.url().split('?').next().unwrap_or("/").to_owned();
    if web_server && method == Method::Get {
        if request_path == "/runtime-config.js" {
            let config = format!(
                "window.__PC_REMOTE_CONFIG__ = Object.freeze({});",
                runtime_config()
            )
            .into_bytes();
            let _ = static_response(
                request,
                &config,
                "application/javascript; charset=utf-8",
                origin.as_deref(),
            );
        } else if request_path == "/_tray/qr" {
            if !local_peer(peer) {
                let _ = json_response(request, forbidden("Local only"), origin.as_deref());
                return;
            }
            match qr_page(state) {
                Ok(page) => {
                    state.log("QR pairing page opened");
                    let _ = static_response(
                        request,
                        &page,
                        "text/html; charset=utf-8",
                        origin.as_deref(),
                    );
                }
                Err(error) => {
                    let _ = json_response(request, error, origin.as_deref());
                }
            }
        } else if request_path == "/" || request_path == "/index.html" {
            let _ = static_response(
                request,
                INDEX_HTML,
                "text/html; charset=utf-8",
                origin.as_deref(),
            );
        } else if request_path == "/favicon.ico" {
            let _ = static_response(request, FAVICON, "image/x-icon", origin.as_deref());
        } else if request_path == "/icons/icon-192.png" || request_path == "/web/icons/icon-192.png"
        {
            let _ = static_response(request, ICON_192, "image/png", origin.as_deref());
        } else {
            let _ = json_response(request, ApiError::new(404, "Not found"), origin.as_deref());
        }
        return;
    }
    if web_server
        && method != Method::Get
        && !request_path.starts_with("/health")
        && !request_path.starts_with("/auth_state")
    {
        let _ = json_response(request, ApiError::new(404, "Not found"), origin.as_deref());
        return;
    }
    let mut request = request;
    let body = match read_body(&mut request) {
        Ok(value) => value,
        Err(error) => {
            let _ = json_response(request, error, origin.as_deref());
            return;
        }
    };
    match route_api(&method, &request_path, &body, peer, state) {
        Ok(value) => {
            let _ = json_response_value(request, StatusCode(200), value, origin.as_deref(), None);
        }
        Err(error) => {
            let _ = json_response(request, error, origin.as_deref());
        }
    }
}

fn cors(
    response: Response<std::io::Cursor<Vec<u8>>>,
    origin: Option<&str>,
) -> Response<std::io::Cursor<Vec<u8>>> {
    let mut response = response;
    if let Some(value) = origin {
        if let Ok(header) = Header::from_bytes("Access-Control-Allow-Origin", value) {
            response = response.with_header(header);
        }
    }
    if let Ok(header) = Header::from_bytes("Vary", "Origin") {
        response = response.with_header(header);
    }
    response
}

fn json_response(
    request: Request,
    error: ApiError,
    origin: Option<&str>,
) -> Result<(), std::io::Error> {
    let status = StatusCode(error.status);
    let mut response = Response::from_data(
        serde_json::to_vec(
            &json!({"detail":error.message,"retry_after_seconds":error.retry_after}),
        )
        .unwrap_or_default(),
    )
    .with_status_code(status);
    response
        .add_header(Header::from_bytes("Content-Type", "application/json; charset=utf-8").unwrap());
    if let Some(seconds) = error.retry_after {
        response.add_header(Header::from_bytes("Retry-After", seconds.to_string()).unwrap());
    }
    request.respond(cors(response, origin)).map(|_| ())
}

fn json_response_value(
    request: Request,
    status: StatusCode,
    value: Value,
    origin: Option<&str>,
    retry_after: Option<u64>,
) -> Result<(), std::io::Error> {
    let mut response = Response::from_data(serde_json::to_vec(&value).unwrap_or_default())
        .with_status_code(status);
    response
        .add_header(Header::from_bytes("Content-Type", "application/json; charset=utf-8").unwrap());
    if let Some(seconds) = retry_after {
        response.add_header(Header::from_bytes("Retry-After", seconds.to_string()).unwrap());
    }
    request.respond(cors(response, origin)).map(|_| ())
}

fn static_response(
    request: Request,
    data: &[u8],
    mime: &str,
    origin: Option<&str>,
) -> Result<(), std::io::Error> {
    let response = Response::from_data(data.to_vec())
        .with_status_code(StatusCode(200))
        .with_header(Header::from_bytes("Content-Type", mime).unwrap())
        .with_header(Header::from_bytes("Cache-Control", "no-cache").unwrap());
    request.respond(cors(response, origin)).map(|_| ())
}

fn serve(server: Server, state: Arc<AppState>, web: bool, workers: usize) {
    let (sender, receiver) = crossbeam_channel::bounded::<Request>(32);
    for index in 0..workers {
        let jobs = receiver.clone();
        let state = Arc::clone(&state);
        thread::Builder::new()
            .name(format!("http-worker-{index}"))
            .spawn(move || {
                while let Ok(request) = jobs.recv() {
                    respond(request, &state, web);
                }
            })
            .expect("could not start HTTP worker");
    }
    loop {
        match server.recv() {
            Ok(request) => {
                if sender.send(request).is_err() {
                    break;
                }
            }
            Err(_) => thread::sleep(Duration::from_millis(20)),
        }
    }
}

pub fn start_servers(state: Arc<AppState>, api_port: u16, web_port: u16) -> Result<(), String> {
    if api_port == web_port {
        return Err("The web and API ports must be different".into());
    }
    let api = Server::http((Ipv4Addr::UNSPECIFIED, api_port))
        .map_err(|error| format!("API could not start on port {api_port}: {error}"))?;
    let web = Server::http((Ipv4Addr::UNSPECIFIED, web_port))
        .map_err(|error| format!("Web controller could not start on port {web_port}: {error}"))?;
    let api_state = Arc::clone(&state);
    thread::Builder::new()
        .name("api-http-listener".into())
        .spawn(move || serve(api, api_state, false, 4))
        .map_err(|e| e.to_string())?;
    let web_state = Arc::clone(&state);
    thread::Builder::new()
        .name("web-http-listener".into())
        .spawn(move || serve(web, web_state, true, 2))
        .map_err(|e| e.to_string())?;
    state.log(&format!(
        "Web controller available at http://{}:{web_port}",
        platform::local_ip()
    ));
    state.log(&format!("API listening on port {api_port}"));
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    #[test]
    fn browser_origin_is_limited_to_local_origins() {
        assert!(allowed_origin(None));
        assert!(allowed_origin(Some("http://localhost:8080")));
        assert!(!allowed_origin(Some("null")));
        assert!(!allowed_origin(Some("https://untrusted.invalid")));
    }

    #[test]
    fn pairing_page_cannot_issue_a_qr_token_to_another_lan_device() {
        assert!(local_peer(IpAddr::V4(Ipv4Addr::LOCALHOST)));
        assert!(local_peer(IpAddr::V6(std::net::Ipv6Addr::LOCALHOST)));
        assert!(!local_peer(IpAddr::V4(Ipv4Addr::new(192, 168, 1, 20))));
    }

    #[test]
    fn rate_limited_pin_cannot_bypass_through_action_endpoint() {
        let temp = tempfile::tempdir().unwrap();
        let state = Arc::new(AppState::new_in(temp.path().to_path_buf()));
        state.set_pin("1234").unwrap();
        let remote = IpAddr::V4(Ipv4Addr::new(192, 168, 1, 5));
        for attempt in 0..config::LOGIN_LIMIT {
            let result = route_api(
                &Method::Post,
                "/login",
                &json!({"password":"0000"}),
                remote,
                &state,
            );
            if attempt + 1 < config::LOGIN_LIMIT {
                assert_eq!(result.unwrap_err().status, 403);
            } else {
                assert_eq!(result.unwrap_err().status, 429);
            }
        }
        let error = route_api(
            &Method::Post,
            "/status",
            &json!({"password":"1234"}),
            remote,
            &state,
        )
        .unwrap_err();
        assert_eq!(error.status, 429);
        let token = state.issue_token(false);
        assert!(
            route_api(
                &Method::Post,
                "/status",
                &json!({"token":token}),
                remote,
                &state
            )
            .is_ok()
        );
    }

    #[test]
    fn action_pin_failures_also_block_login_and_password_changes_for_that_peer() {
        let temp = tempfile::tempdir().unwrap();
        let state = Arc::new(AppState::new_in(temp.path().to_path_buf()));
        state.set_pin("1234").unwrap();
        let remote = IpAddr::V4(Ipv4Addr::new(192, 168, 1, 5));
        for _ in 0..config::LOGIN_LIMIT {
            let result = route_api(
                &Method::Post,
                "/status",
                &json!({"password":"0000"}),
                remote,
                &state,
            );
            assert!(result.is_err());
        }
        let login = route_api(
            &Method::Post,
            "/login",
            &json!({"password":"1234"}),
            remote,
            &state,
        )
        .unwrap_err();
        assert_eq!(login.status, 429);
        let session = state.issue_token(false);
        let change = route_api(
            &Method::Post,
            "/change_password",
            &json!({"current_password":"1234","new_password":"5678","token":session}),
            remote,
            &state,
        )
        .unwrap_err();
        assert_eq!(change.status, 429);
        state.reset_login_failures("legacy-pin-actions");
        let other_peer = IpAddr::V4(Ipv4Addr::new(192, 168, 1, 6));
        assert!(
            route_api(
                &Method::Post,
                "/status",
                &json!({"password":"1234"}),
                other_peer,
                &state,
            )
            .is_ok()
        );
    }

    #[test]
    fn pairing_token_continues_to_authenticate_existing_phone_client() {
        let temp = tempfile::tempdir().unwrap();
        let state = Arc::new(AppState::new_in(temp.path().to_path_buf()));
        let token = state.issue_token(true);
        let peer = IpAddr::V4(Ipv4Addr::new(192, 168, 1, 5));
        let response = route_api(
            &Method::Post,
            "/setup_password",
            &json!({"token":token,"new_password":"0456"}),
            peer,
            &state,
        )
        .unwrap();
        assert_eq!(response["status"], "ok");
        assert!(state.auth_ready());
        let response = route_api(
            &Method::Post,
            "/connect",
            &json!({"token":token}),
            peer,
            &state,
        )
        .unwrap();
        assert_eq!(response["status"], "connected");
        assert!(state.phone_connected.load(Ordering::Relaxed));
    }
}
