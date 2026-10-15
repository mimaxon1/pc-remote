use std::{
    collections::{HashMap, VecDeque},
    env, fs,
    io::Write,
    net::IpAddr,
    path::PathBuf,
    sync::{
        Mutex,
        atomic::{AtomicBool, Ordering},
    },
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};

use base64::{Engine, engine::general_purpose::STANDARD};
use hmac::Hmac;
use pbkdf2::pbkdf2;
use rand::RngCore;
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value, json};
use sha2::Sha256;

use crate::config;

type HmacSha256 = Hmac<Sha256>;

#[derive(Clone, Serialize, Deserialize)]
pub struct AppItem {
    pub path: String,
    pub name: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub args: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub aumid: Option<String>,
    #[serde(default)]
    pub is_running: bool,
}

#[derive(Clone)]
struct Session {
    expires_at: Instant,
    pair: bool,
    opened: bool,
    completed: bool,
}

#[derive(Clone, Debug)]
struct AttemptState {
    timestamps: Vec<Instant>,
    blocked_until: Option<Instant>,
}

#[derive(Clone, Serialize)]
pub struct LogEntry {
    pub id: u64,
    pub time: u64,
    pub message: String,
}

pub struct AppState {
    pub settings_path: PathBuf,
    pub settings_error: AtomicBool,
    settings: Mutex<Value>,
    sessions: Mutex<HashMap<String, Session>>,
    attempts: Mutex<HashMap<String, AttemptState>>,
    pin_verification: Mutex<()>,
    logs: Mutex<VecDeque<LogEntry>>,
    next_log_id: Mutex<u64>,
    pub phone_connected: AtomicBool,
    pub restart_requested: AtomicBool,
    pub current_volume: Mutex<f32>,
    pub muted: AtomicBool,
    pinned_path: PathBuf,
}

fn read_object(path: &std::path::Path) -> Result<Value, String> {
    let text = fs::read_to_string(path).map_err(|error| error.to_string())?;
    let value: Value =
        serde_json::from_str(&text).map_err(|error| format!("invalid JSON: {error}"))?;
    if !value.is_object() {
        return Err("settings file must contain a JSON object".into());
    }
    Ok(value)
}

fn legacy_settings_paths() -> Vec<PathBuf> {
    let mut paths = Vec::new();
    #[cfg(target_os = "windows")]
    if let Some(appdata) = env::var_os("APPDATA") {
        paths.push(PathBuf::from(appdata).join("PC-Android/settings.json"));
    }
    #[cfg(target_os = "macos")]
    if let Some(home) = env::var_os("HOME") {
        paths
            .push(PathBuf::from(home).join("Library/Application Support/PC-Android/settings.json"));
    }
    if let Ok(executable) = env::current_exe() {
        if let Some(directory) = executable.parent() {
            paths.push(directory.join("settings.json"));
        }
    }
    paths
}

fn write_json_atomic(path: &std::path::Path, value: &Value) -> Result<(), String> {
    fs::create_dir_all(path.parent().ok_or("settings directory is missing")?)
        .map_err(|e| e.to_string())?;
    let mut temp =
        tempfile::NamedTempFile::new_in(path.parent().ok_or("settings directory is missing")?)
            .map_err(|e| e.to_string())?;
    temp.write_all(
        serde_json::to_vec_pretty(value)
            .map_err(|e| e.to_string())?
            .as_slice(),
    )
    .map_err(|e| e.to_string())?;
    temp.as_file().sync_all().map_err(|e| e.to_string())?;
    temp.persist(path).map_err(|e| e.error.to_string())?;
    Ok(())
}

fn load_settings(path: &std::path::Path) -> (Value, bool) {
    load_settings_from(path, &legacy_settings_paths())
}

fn load_settings_from(path: &std::path::Path, legacy_paths: &[PathBuf]) -> (Value, bool) {
    if path.exists() {
        return match read_object(path) {
            Ok(value) => (value, false),
            Err(error) => {
                eprintln!(
                    "Settings could not be read; preserving the file and requiring manual repair: {error}"
                );
                (Value::Object(Map::new()), true)
            }
        };
    }
    for source in legacy_paths {
        if source == path || !source.exists() {
            continue;
        }
        let Ok(value) = read_object(source) else {
            continue;
        };
        // Copy the complete document so the prior PIN and network preferences survive.
        // Keep the source as a rollback copy until a later explicit user cleanup.
        return match write_json_atomic(path, &value) {
            Ok(()) => (value, false),
            Err(error) => {
                eprintln!(
                    "Could not migrate settings from {}; leaving both files untouched: {error}",
                    source.display()
                );
                (Value::Object(Map::new()), true)
            }
        };
    }
    (Value::Object(Map::new()), false)
}

impl AppState {
    pub fn new() -> Self {
        Self::new_in(config::data_dir())
    }

    pub fn new_in(directory: PathBuf) -> Self {
        let settings_path = directory.join("settings.json");
        let pinned_path = directory.join("pinned_apps.json");
        let (settings, settings_error) = load_settings(&settings_path);
        let state = Self {
            settings_path,
            settings_error: AtomicBool::new(settings_error),
            settings: Mutex::new(settings),
            sessions: Mutex::new(HashMap::new()),
            attempts: Mutex::new(HashMap::new()),
            pin_verification: Mutex::new(()),
            logs: Mutex::new(VecDeque::with_capacity(200)),
            next_log_id: Mutex::new(1),
            phone_connected: AtomicBool::new(false),
            restart_requested: AtomicBool::new(false),
            current_volume: Mutex::new(0.5),
            muted: AtomicBool::new(false),
            pinned_path,
        };
        state.log("PC Remote 2.0 started");
        state
    }

    pub fn auth_ready(&self) -> bool {
        if self.settings_error.load(Ordering::Relaxed) {
            return false;
        }
        self.settings
            .lock()
            .ok()
            .and_then(|settings| {
                let password = settings.get("password")?;
                if password.get("is_default").and_then(Value::as_bool) == Some(true)
                    || password.get("is_set").and_then(Value::as_bool) == Some(false)
                    || password.get("algorithm").and_then(Value::as_str)
                        != Some("pbkdf2_hmac_sha256")
                    || password
                        .get("iterations")
                        .and_then(Value::as_u64)
                        .is_none_or(|count| count == 0 || count > 2_000_000)
                {
                    return None;
                }
                let salt = password
                    .get("salt")?
                    .as_str()
                    .and_then(|encoded| STANDARD.decode(encoded).ok())?;
                let hash = password
                    .get("hash")?
                    .as_str()
                    .and_then(|encoded| STANDARD.decode(encoded).ok())?;
                (salt.len() >= 8 && hash.len() == 32).then_some(())
            })
            .is_some()
    }

    pub fn settings_snapshot(&self) -> Value {
        self.settings
            .lock()
            .map(|s| s.clone())
            .unwrap_or_else(|_| Value::Object(Map::new()))
    }

    pub fn pin_hash_matches(&self, pin: &str) -> bool {
        if self.settings_error.load(Ordering::Relaxed) {
            return false;
        }
        let data = self.settings_snapshot();
        let Some(block) = data.get("password") else {
            return false;
        };
        if block.get("is_set").and_then(Value::as_bool) == Some(false) {
            return false;
        }
        if block.get("algorithm").and_then(Value::as_str) != Some("pbkdf2_hmac_sha256") {
            return false;
        }
        let Some(iterations) = block
            .get("iterations")
            .and_then(Value::as_u64)
            .and_then(|n| u32::try_from(n).ok())
        else {
            return false;
        };
        if iterations == 0 || iterations > 2_000_000 {
            return false;
        }
        let Some(salt) = block
            .get("salt")
            .and_then(Value::as_str)
            .and_then(|s| STANDARD.decode(s).ok())
        else {
            return false;
        };
        let Some(expected) = block
            .get("hash")
            .and_then(Value::as_str)
            .and_then(|s| STANDARD.decode(s).ok())
        else {
            return false;
        };
        if salt.len() < 8 || expected.len() != 32 {
            return false;
        }
        let mut actual = [0u8; 32];
        if pbkdf2::<HmacSha256>(pin.as_bytes(), &salt, iterations, &mut actual).is_err() {
            return false;
        }
        use std::sync::atomic::compiler_fence;
        let equal = actual
            .iter()
            .zip(expected.iter())
            .fold(0u8, |different, (a, b)| different | (*a ^ *b))
            == 0;
        compiler_fence(Ordering::SeqCst);
        equal
    }

    pub fn set_pin(&self, pin: &str) -> Result<(), String> {
        if self.settings_error.load(Ordering::Relaxed) {
            return Err("settings.json needs repair".into());
        }
        let mut salt = [0u8; 16];
        rand::rng().fill_bytes(&mut salt);
        let mut hash = [0u8; 32];
        pbkdf2::<HmacSha256>(pin.as_bytes(), &salt, config::PBKDF2_ITERATIONS, &mut hash)
            .map_err(|e| e.to_string())?;
        let mut data = self.settings.lock().map_err(|_| "settings lock poisoned")?;
        let mut replacement = data.clone();
        if !replacement.is_object() {
            replacement = Value::Object(Map::new());
        }
        let object = replacement.as_object_mut().ok_or("settings need repair")?;
        object.insert("version".into(), json!(3));
        object.insert(
            "password".into(),
            json!({
                "is_set": true,
                "algorithm": "pbkdf2_hmac_sha256",
                "iterations": config::PBKDF2_ITERATIONS,
                "salt": STANDARD.encode(salt),
                "hash": STANDARD.encode(hash),
            }),
        );
        write_json_atomic(&self.settings_path, &replacement)?;
        *data = replacement;
        Ok(())
    }

    pub fn change_pin(&self, pin: &str) -> Result<(), String> {
        self.set_pin(pin)?;
        if let Ok(mut sessions) = self.sessions.lock() {
            sessions.clear();
        }
        Ok(())
    }

    pub fn clear_pin(&self) -> Result<(), String> {
        if self.settings_error.load(Ordering::Relaxed) {
            return Err("settings.json needs repair".into());
        }
        let mut data = self.settings.lock().map_err(|_| "settings lock poisoned")?;
        let mut replacement = data.clone();
        if let Some(object) = replacement.as_object_mut() {
            object.insert("version".into(), json!(3));
            object.insert("password".into(), json!({ "is_set": false }));
        }
        write_json_atomic(&self.settings_path, &replacement)?;
        *data = replacement;
        if let Ok(mut sessions) = self.sessions.lock() {
            sessions.clear();
        }
        Ok(())
    }

    pub fn issue_token(&self, pair: bool) -> String {
        let mut bytes = [0u8; 32];
        rand::rng().fill_bytes(&mut bytes);
        let token = base64::engine::general_purpose::URL_SAFE_NO_PAD.encode(bytes);
        if let Ok(mut sessions) = self.sessions.lock() {
            let ttl = if pair {
                config::PAIR_TTL_SECS
            } else {
                config::SESSION_TTL_SECS
            };
            sessions.insert(
                token.clone(),
                Session {
                    expires_at: Instant::now() + Duration::from_secs(ttl),
                    pair,
                    opened: false,
                    completed: false,
                },
            );
        }
        token
    }

    pub fn verify_token(&self, token: &str) -> bool {
        let Ok(mut sessions) = self.sessions.lock() else {
            return false;
        };
        let Some(session) = sessions.get(token) else {
            return false;
        };
        if session.expires_at <= Instant::now() {
            sessions.remove(token);
            return false;
        }
        true
    }

    pub fn pair_touch(&self, token: &str) -> bool {
        if let Ok(mut sessions) = self.sessions.lock() {
            if let Some(item) = sessions.get_mut(token) {
                if item.pair && item.expires_at > Instant::now() {
                    item.opened = true;
                    return true;
                }
            }
        }
        false
    }

    pub fn pair_complete(&self, token: &str) -> bool {
        if let Ok(mut sessions) = self.sessions.lock() {
            if let Some(item) = sessions.get_mut(token) {
                if item.pair && item.expires_at > Instant::now() {
                    item.completed = true;
                    return true;
                }
            }
        }
        false
    }

    pub fn pair_status(&self, token: &str) -> (bool, bool) {
        self.sessions
            .lock()
            .ok()
            .and_then(|s| {
                s.get(token)
                    .filter(|p| p.pair && p.expires_at > Instant::now())
                    .map(|p| (p.opened, p.completed))
            })
            .unwrap_or((false, false))
    }

    pub fn revoke_token(&self, token: &str) {
        if let Ok(mut sessions) = self.sessions.lock() {
            sessions.remove(token);
        }
    }

    pub fn login_blocked_for(&self, peer: &str) -> Option<u64> {
        let mut all = self.attempts.lock().ok()?;
        let item = all.get_mut(peer)?;
        match item.blocked_until {
            Some(until) if until > Instant::now() => Some(
                until
                    .saturating_duration_since(Instant::now())
                    .as_secs()
                    .max(1),
            ),
            Some(_) => {
                item.blocked_until = None;
                item.timestamps.clear();
                None
            }
            None => None,
        }
    }

    pub fn login_failed(&self, peer: &str) -> Option<u64> {
        let now = Instant::now();
        let mut all = self.attempts.lock().ok()?;
        let item = all.entry(peer.to_owned()).or_insert(AttemptState {
            timestamps: vec![],
            blocked_until: None,
        });
        item.timestamps
            .retain(|ts| now.duration_since(*ts) < Duration::from_secs(config::LOGIN_WINDOW_SECS));
        item.timestamps.push(now);
        if item.timestamps.len() >= config::LOGIN_LIMIT {
            let until = now + Duration::from_secs(config::LOGIN_BLOCK_SECS);
            item.blocked_until = Some(until);
            return Some(config::LOGIN_BLOCK_SECS);
        }
        None
    }

    pub fn reset_login_failures(&self, peer: &str) {
        if let Ok(mut all) = self.attempts.lock() {
            all.remove(peer);
        }
    }

    fn verify_legacy_pin(&self, pin: &str) -> Result<bool, u64> {
        if let Some(secs) = self.login_blocked_for("legacy-pin-actions") {
            return Err(secs);
        }
        if self.pin_hash_matches(pin) {
            self.reset_login_failures("legacy-pin-actions");
            Ok(true)
        } else {
            Err(self.login_failed("legacy-pin-actions").unwrap_or(0))
        }
    }

    pub fn verify_pin_for_peer(&self, pin: &str, peer: &str) -> Result<bool, u64> {
        let _verification = self
            .pin_verification
            .lock()
            .expect("PIN verification lock poisoned");
        if let Some(seconds) = self.login_blocked_for(peer) {
            return Err(seconds);
        }
        match self.verify_legacy_pin(pin) {
            Ok(true) => {
                self.reset_login_failures(peer);
                Ok(true)
            }
            Err(seconds) if seconds > 0 => {
                let peer_block = self.login_failed(peer);
                Err(peer_block.unwrap_or(seconds))
            }
            Err(_) => match self.login_failed(peer) {
                Some(seconds) => Err(seconds),
                None => Ok(false),
            },
            Ok(false) => Ok(false),
        }
    }

    pub fn logs(&self, since: Option<u64>, limit: usize) -> (Vec<LogEntry>, u64, bool) {
        let Ok(entries) = self.logs.lock() else {
            return (vec![], 0, false);
        };
        let cursor = entries.back().map(|row| row.id).unwrap_or(0);
        let reset = since.is_some_and(|mark| {
            entries
                .front()
                .is_some_and(|front| mark.saturating_add(1) < front.id)
        });
        let rows = entries
            .iter()
            .filter(|row| reset || since.is_none_or(|mark| row.id > mark))
            .take(limit.min(1000))
            .cloned()
            .collect();
        (rows, cursor, reset)
    }

    pub fn log(&self, message: &str) {
        let Ok(mut next) = self.next_log_id.lock() else {
            return;
        };
        let entry = LogEntry {
            id: *next,
            time: SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap_or_default()
                .as_secs(),
            message: message.chars().take(1024).collect(),
        };
        *next += 1;
        if let Ok(mut rows) = self.logs.lock() {
            if rows.len() >= 500 {
                rows.pop_front();
            }
            rows.push_back(entry);
        }
    }

    pub fn pinned(&self) -> Vec<AppItem> {
        fs::read_to_string(&self.pinned_path)
            .ok()
            .and_then(|text| serde_json::from_str::<Vec<AppItem>>(&text).ok())
            .unwrap_or_default()
    }

    pub fn pin_app(&self, item: AppItem) -> Result<Vec<AppItem>, String> {
        let mut items = self.pinned();
        items.retain(|existing| {
            existing.path != item.path || existing.args != item.args || existing.aumid != item.aumid
        });
        items.insert(0, item);
        items.truncate(100);
        write_json_atomic(
            &self.pinned_path,
            &serde_json::to_value(&items).map_err(|e| e.to_string())?,
        )?;
        Ok(items)
    }

    pub fn unpin_app(
        &self,
        path: &str,
        args: Option<&str>,
        aumid: Option<&str>,
    ) -> Result<(bool, Vec<AppItem>), String> {
        let mut items = self.pinned();
        let previous = items.len();
        items.retain(|existing| {
            !(existing.path.eq_ignore_ascii_case(path)
                && existing.args.as_deref() == args
                && existing.aumid.as_deref() == aumid)
        });
        if items.len() != previous {
            write_json_atomic(
                &self.pinned_path,
                &serde_json::to_value(&items).map_err(|e| e.to_string())?,
            )?;
        }
        Ok((previous != items.len(), items))
    }

    pub fn is_loopback(ip: IpAddr) -> bool {
        ip.is_loopback()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn preserves_legacy_pin_fields_on_change() {
        let temp = tempfile::tempdir().unwrap();
        let state = AppState::new_in(temp.path().to_path_buf());
        state.settings_error.store(false, Ordering::Relaxed);
        let mut settings = state.settings.lock().unwrap();
        *settings = json!({"network":{"preferred_ip":"192.168.1.10"},"keep":"value"});
        drop(settings);
        state.set_pin("0712").unwrap();
        assert!(state.pin_hash_matches("0712"));
        assert!(!state.pin_hash_matches("1234"));
        let document = state.settings_snapshot();
        assert_eq!(document["network"]["preferred_ip"], "192.168.1.10");
        assert_eq!(document["keep"], "value");
    }

    #[test]
    fn copies_valid_legacy_settings_without_removing_the_source() {
        let temp = tempfile::tempdir().unwrap();
        let legacy = temp.path().join("legacy-settings.json");
        let current = temp.path().join("current/settings.json");
        let contents = json!({"version":3,"password":{"is_set":false},"network":{"preferred_interface":"Wi-Fi","preferred_ip":"192.168.1.20"}});
        fs::write(&legacy, serde_json::to_vec(&contents).unwrap()).unwrap();

        let (loaded, damaged) = load_settings_from(&current, std::slice::from_ref(&legacy));

        assert!(!damaged);
        assert_eq!(loaded, contents);
        assert_eq!(read_object(&current).unwrap(), contents);
        assert_eq!(read_object(&legacy).unwrap(), contents);
    }

    #[test]
    fn damaged_current_settings_never_delete_or_replace_the_legacy_copy() {
        let temp = tempfile::tempdir().unwrap();
        let legacy = temp.path().join("legacy-settings.json");
        let current = temp.path().join("current/settings.json");
        let source = json!({"version":3,"network":{"preferred_ip":"192.168.1.20"}});
        fs::write(&legacy, serde_json::to_vec(&source).unwrap()).unwrap();
        fs::create_dir_all(current.parent().unwrap()).unwrap();
        fs::write(&current, b"{").unwrap();

        let (loaded, damaged) = load_settings_from(&current, std::slice::from_ref(&legacy));

        assert!(damaged);
        assert_eq!(loaded, json!({}));
        assert_eq!(fs::read(&current).unwrap(), b"{");
        assert_eq!(read_object(&legacy).unwrap(), source);
    }

    #[test]
    fn existing_current_settings_keep_precedence_without_deleting_legacy_data() {
        let temp = tempfile::tempdir().unwrap();
        let legacy = temp.path().join("legacy-settings.json");
        let current = temp.path().join("current/settings.json");
        let old = json!({"network":{"preferred_ip":"192.168.1.10"}});
        let new = json!({"network":{"preferred_ip":"192.168.1.20"}});
        fs::write(&legacy, serde_json::to_vec(&old).unwrap()).unwrap();
        write_json_atomic(&current, &new).unwrap();

        let (loaded, damaged) = load_settings_from(&current, std::slice::from_ref(&legacy));

        assert!(!damaged);
        assert_eq!(loaded, new);
        assert_eq!(read_object(&legacy).unwrap(), old);
    }

    #[test]
    fn pairing_token_remains_a_usable_session_for_its_full_ttl() {
        let temp = tempfile::tempdir().unwrap();
        let state = AppState::new_in(temp.path().to_path_buf());
        let token = state.issue_token(true);
        assert!(state.verify_token(&token));
        assert_eq!(config::PAIR_TTL_SECS, config::SESSION_TTL_SECS);
        assert!(state.pair_touch(&token));
        assert_eq!(state.pair_status(&token), (true, false));
    }

    #[test]
    fn failed_pin_checks_share_a_global_budget() {
        let temp = tempfile::tempdir().unwrap();
        let state = AppState::new_in(temp.path().to_path_buf());
        for attempt in 0..config::LOGIN_LIMIT - 1 {
            assert!(
                !state
                    .verify_pin_for_peer("wrong", &format!("192.0.2.{}", attempt + 1))
                    .unwrap()
            );
        }
        assert!(
            state
                .verify_pin_for_peer("correct-but-now-blocked", "192.0.2.5")
                .unwrap_err()
                > 0
        );
        assert!(
            state
                .verify_pin_for_peer("correct-but-now-blocked", "192.0.2.6")
                .unwrap_err()
                > 0
        );
    }

    #[test]
    fn concurrent_pin_failures_cannot_overrun_peer_limit() {
        let temp = tempfile::tempdir().unwrap();
        let state = std::sync::Arc::new(AppState::new_in(temp.path().to_path_buf()));
        let workers = (0..8)
            .map(|_| {
                let state = std::sync::Arc::clone(&state);
                std::thread::spawn(move || state.verify_pin_for_peer("wrong", "192.0.2.2"))
            })
            .collect::<Vec<_>>();
        let results = workers
            .into_iter()
            .map(|worker| worker.join().unwrap())
            .collect::<Vec<_>>();
        assert_eq!(
            results
                .iter()
                .filter(|result| **result == Ok(false))
                .count(),
            config::LOGIN_LIMIT - 1
        );
        assert_eq!(
            results
                .iter()
                .filter(|result| result.as_ref().is_err())
                .count(),
            8 - (config::LOGIN_LIMIT - 1)
        );
        assert!(
            state
                .verify_pin_for_peer("correct", "192.0.2.2")
                .unwrap_err()
                > 0
        );
    }
}
