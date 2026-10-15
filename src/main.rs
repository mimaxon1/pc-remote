#![cfg_attr(all(windows, not(debug_assertions)), windows_subsystem = "windows")]

mod api;
mod config;
mod platform;
mod state;
mod tray;

#[cfg(target_os = "macos")]
use std::process::Command;
use std::sync::Arc;

fn handle_cli() -> bool {
    let args: Vec<String> = std::env::args().skip(1).collect();
    match args.first().map(String::as_str) {
        Some("--install-autostart") => platform::set_autostart(true)
            .map(|_| println!("Autostart enabled"))
            .unwrap_or_else(|error| eprintln!("{error}")),
        Some("--remove-autostart") => platform::set_autostart(false)
            .map(|_| println!("Autostart disabled"))
            .unwrap_or_else(|error| eprintln!("{error}")),
        Some("--autostart-status") => {
            println!(
                "{}",
                if platform::autostart_enabled() {
                    "enabled"
                } else {
                    "disabled"
                }
            );
            return true;
        }
        _ => return false,
    }
    true
}

fn show_start_error(message: &str) {
    eprintln!("{message}");
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::ffi::OsStrExt;
        let title: Vec<u16> = std::ffi::OsStr::new("PC Remote could not start")
            .encode_wide()
            .chain(Some(0))
            .collect();
        let text: Vec<u16> = std::ffi::OsStr::new(message)
            .encode_wide()
            .chain(Some(0))
            .collect();
        unsafe {
            windows_sys::Win32::UI::WindowsAndMessaging::MessageBoxW(
                std::ptr::null_mut(),
                text.as_ptr(),
                title.as_ptr(),
                0x10,
            );
        }
    }
    #[cfg(target_os = "macos")]
    {
        let _ = Command::new("osascript")
            .args([
                "-e",
                &format!(
                    "display alert \"PC Remote could not start\" message \"{}\"",
                    message.replace('"', "'").replace('\n', " ")
                ),
            ])
            .spawn();
    }
}

fn main() {
    if handle_cli() {
        return;
    }
    let state = Arc::new(state::AppState::new());
    let api_port = config::port("PC_REMOTE_API_PORT", config::API_PORT_DEFAULT);
    let web_port = config::port("PC_REMOTE_WEB_PORT", config::WEB_PORT_DEFAULT);
    if let Err(error) = api::start_servers(Arc::clone(&state), api_port, web_port) {
        show_start_error(&error);
        return;
    }
    if let Err(error) = tray::run(Arc::clone(&state)) {
        show_start_error(&error);
    }
}
