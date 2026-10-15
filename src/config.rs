use std::{env, path::PathBuf};

pub const APP_NAME: &str = "PC Remote";
pub const APP_VERSION: &str = match option_env!("PC_REMOTE_VERSION") {
    Some(version) => version,
    None => env!("CARGO_PKG_VERSION"),
};
pub const PIN_LENGTH: usize = 4;
pub const API_PORT_DEFAULT: u16 = 8000;
pub const WEB_PORT_DEFAULT: u16 = 8080;
pub const SESSION_TTL_SECS: u64 = 3600;
pub const PAIR_TTL_SECS: u64 = SESSION_TTL_SECS;
pub const PBKDF2_ITERATIONS: u32 = 200_000;
pub const LOGIN_LIMIT: usize = 5;
pub const LOGIN_WINDOW_SECS: u64 = 60;
pub const LOGIN_BLOCK_SECS: u64 = 900;

pub fn port(name: &str, default: u16) -> u16 {
    env::var(name)
        .ok()
        .and_then(|raw| raw.parse().ok())
        .filter(|p: &u16| *p != 0)
        .unwrap_or(default)
}

pub fn version() -> &'static str {
    APP_VERSION
}

pub fn data_dir() -> PathBuf {
    #[cfg(target_os = "windows")]
    if let Some(base) = env::var_os("APPDATA") {
        return PathBuf::from(base).join(APP_NAME);
    }
    #[cfg(target_os = "macos")]
    if let Some(home) = env::var_os("HOME") {
        return PathBuf::from(home)
            .join("Library/Application Support")
            .join(APP_NAME);
    }
    if let Some(base) = env::var_os("XDG_CONFIG_HOME") {
        return PathBuf::from(base).join(APP_NAME);
    }
    env::current_dir()
        .unwrap_or_else(|_| PathBuf::from("."))
        .join(".pc-remote")
}
