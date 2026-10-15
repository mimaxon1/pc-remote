use std::{
    env, fs,
    net::{Ipv4Addr, UdpSocket},
    path::{Path, PathBuf},
    process::Command,
    thread,
    time::Duration,
};

use serde_json::{Value, json};
#[cfg(target_os = "macos")]
use smappservice_rs::{AppService, ServiceManagementError, ServiceStatus, ServiceType};
use sysinfo::System;

use crate::state::{AppItem, AppState};

pub fn local_ip() -> Ipv4Addr {
    UdpSocket::bind((Ipv4Addr::UNSPECIFIED, 0))
        .and_then(|socket| {
            socket.connect((Ipv4Addr::new(8, 8, 8, 8), 80))?;
            match socket.local_addr()?.ip() {
                std::net::IpAddr::V4(ip) if !ip.is_loopback() => Ok(ip),
                _ => Err(std::io::Error::other("no active LAN route")),
            }
        })
        .unwrap_or(Ipv4Addr::LOCALHOST)
}

pub fn default_output_device() -> Value {
    #[cfg(target_os = "macos")]
    let name = "System default audio output";
    #[cfg(target_os = "windows")]
    let name = "System default audio output";
    json!({ "id": "default", "name": name })
}

#[cfg(target_os = "macos")]
fn parse_macos_audio_settings(raw: &str) -> Option<(f32, bool)> {
    let mut volume = None;
    let mut muted = None;
    for field in raw
        .trim()
        .trim_start_matches('{')
        .trim_end_matches('}')
        .split(',')
    {
        let (key, value) = field.trim().split_once(':')?;
        match key.trim() {
            "output volume" => volume = value.trim().parse::<f32>().ok(),
            "output muted" => muted = value.trim().parse::<bool>().ok(),
            _ => {}
        }
    }
    Some((volume?.clamp(0.0, 100.0) / 100.0, muted?))
}

pub fn audio_state(state: &AppState) -> (f32, bool) {
    #[cfg(target_os = "windows")]
    unsafe {
        let mut levels = 0u32;
        if windows_sys::Win32::Media::Audio::waveOutGetVolume(std::ptr::null_mut(), &mut levels)
            == 0
        {
            let left = (levels & 0xFFFF) as f32 / 65535.0;
            let right = (levels >> 16) as f32 / 65535.0;
            if let Ok(mut current) = state.current_volume.lock() {
                *current = (left + right) / 2.0;
            }
        }
    }
    #[cfg(target_os = "macos")]
    if let Ok(output) = Command::new("osascript")
        .args(["-e", "get volume settings"])
        .output()
    {
        if output.status.success() {
            if let Ok(raw) = String::from_utf8(output.stdout) {
                if let Some((volume, muted)) = parse_macos_audio_settings(&raw) {
                    if let Ok(mut current) = state.current_volume.lock() {
                        *current = volume;
                    }
                    state
                        .muted
                        .store(muted, std::sync::atomic::Ordering::Relaxed);
                }
            }
        }
    }
    let volume = state
        .current_volume
        .lock()
        .map(|volume| *volume)
        .unwrap_or(0.5);
    let muted = state.muted.load(std::sync::atomic::Ordering::Relaxed);
    (volume, muted)
}

pub fn volume(state: &AppState) -> f32 {
    audio_state(state).0
}

pub fn set_volume(state: &AppState, value: f32) -> Result<f32, String> {
    let value = value.clamp(0.0, 1.0);
    #[cfg(target_os = "windows")]
    {
        let word = (value * 65535.0).round() as u32;
        let levels = word | (word << 16);
        let result = unsafe {
            windows_sys::Win32::Media::Audio::waveOutSetVolume(std::ptr::null_mut(), levels)
        };
        if result != 0 {
            return Err(format!("Windows audio operation failed ({result})"));
        }
    }
    #[cfg(target_os = "macos")]
    {
        let percent = (value * 100.0).round().to_string();
        let output = Command::new("osascript")
            .args(["-e", &format!("set volume output volume {percent}")])
            .output()
            .map_err(|error| error.to_string())?;
        if !output.status.success() {
            return Err("macOS could not change output volume".into());
        }
    }
    if let Ok(mut current) = state.current_volume.lock() {
        *current = value;
    }
    Ok(value)
}

pub fn set_mute(state: &AppState, muted: bool) -> Result<bool, String> {
    #[cfg(target_os = "windows")]
    {
        use windows_sys::Win32::UI::Input::KeyboardAndMouse::{VK_VOLUME_MUTE, keybd_event};
        let current = state.muted.load(std::sync::atomic::Ordering::Relaxed);
        if current != muted {
            unsafe {
                keybd_event(VK_VOLUME_MUTE as u8, 0, 0, 0);
            }
        }
    }
    #[cfg(target_os = "macos")]
    {
        let script = format!(
            "set volume output muted {}",
            if muted { "true" } else { "false" }
        );
        let output = Command::new("osascript")
            .args(["-e", script.as_str()])
            .output()
            .map_err(|error| error.to_string())?;
        if !output.status.success() {
            return Err("macOS could not change mute state".into());
        }
    }
    state
        .muted
        .store(muted, std::sync::atomic::Ordering::Relaxed);
    Ok(muted)
}

pub fn toggle_mute(state: &AppState) -> Result<bool, String> {
    let next = !audio_state(state).1;
    set_mute(state, next)
}

pub fn send_media(action: &str) -> Result<(), String> {
    #[cfg(target_os = "windows")]
    {
        use windows_sys::Win32::UI::Input::KeyboardAndMouse::{
            VK_MEDIA_NEXT_TRACK, VK_MEDIA_PLAY_PAUSE, VK_MEDIA_PREV_TRACK, VK_MEDIA_STOP,
            keybd_event,
        };
        let key = match action {
            "play_pause" => VK_MEDIA_PLAY_PAUSE as u8,
            "next" => VK_MEDIA_NEXT_TRACK as u8,
            "prev" => VK_MEDIA_PREV_TRACK as u8,
            "stop" => VK_MEDIA_STOP as u8,
            _ => return Err("Unknown action".into()),
        };
        unsafe {
            keybd_event(key, 0, 0, 0);
        }
    }
    #[cfg(target_os = "macos")]
    {
        // Music is the supported macOS media target; keep this explicit in the UI.
        let script = match action {
            "play_pause" => "tell application \"Music\" to playpause",
            "next" => "tell application \"Music\" to next track",
            "prev" => "tell application \"Music\" to previous track",
            "stop" => "tell application \"Music\" to stop",
            _ => return Err("Unknown action".into()),
        };
        let result = Command::new("osascript")
            .args(["-e", script])
            .output()
            .map_err(|error| error.to_string())?;
        if !result.status.success() {
            return Err(
                "macOS could not control Music; allow PC Remote under System Settings > Privacy & Security > Automation".into(),
            );
        }
    }
    Ok(())
}

fn app_name(path: &Path) -> String {
    path.file_stem()
        .or_else(|| path.file_name())
        .and_then(|name| name.to_str())
        .unwrap_or("Application")
        .to_owned()
}

#[cfg(target_os = "windows")]
fn recent_apps() -> Vec<AppItem> {
    let mut dirs = Vec::new();
    if let Some(appdata) = env::var_os("APPDATA") {
        dirs.push(PathBuf::from(appdata).join("Microsoft/Windows/Recent"));
    }
    if let Some(appdata) = env::var_os("APPDATA") {
        dirs.push(PathBuf::from(appdata).join("Microsoft/Windows/Start Menu/Programs"));
    }
    if let Some(programdata) = env::var_os("ProgramData") {
        dirs.push(PathBuf::from(programdata).join("Microsoft/Windows/Start Menu/Programs"));
    }
    let mut found = Vec::new();
    for dir in dirs {
        let Ok(entries) = fs::read_dir(dir) else {
            continue;
        };
        for entry in entries.flatten() {
            let path = entry.path();
            if path
                .extension()
                .is_some_and(|extension| extension.eq_ignore_ascii_case("lnk"))
            {
                let modified = entry
                    .metadata()
                    .and_then(|metadata| metadata.modified())
                    .unwrap_or(std::time::UNIX_EPOCH);
                found.push((
                    modified,
                    AppItem {
                        name: app_name(&path),
                        path: path.to_string_lossy().into_owned(),
                        args: None,
                        aumid: None,
                        is_running: false,
                    },
                ));
            }
        }
    }
    found.sort_by_key(|item| std::cmp::Reverse(item.0));
    let mut unique = std::collections::HashSet::new();
    found
        .into_iter()
        .filter(|(_, item)| unique.insert(item.path.to_lowercase()))
        .map(|(_, item)| item)
        .take(30)
        .collect()
}

#[cfg(target_os = "macos")]
fn recent_apps() -> Vec<AppItem> {
    let mut found = Vec::new();
    for directory in [
        PathBuf::from("/Applications"),
        PathBuf::from("/System/Applications"),
    ] {
        let Ok(entries) = fs::read_dir(directory) else {
            continue;
        };
        for entry in entries.flatten() {
            let path = entry.path();
            if path.extension().is_some_and(|extension| extension == "app") {
                found.push(AppItem {
                    name: app_name(&path),
                    path: path.to_string_lossy().into_owned(),
                    args: None,
                    aumid: None,
                    is_running: false,
                });
            }
        }
    }
    found.sort_by_cached_key(|item| item.name.to_lowercase());
    found.truncate(30);
    found
}

pub fn list_apps(state: &AppState) -> Value {
    let mut apps = recent_apps();
    let pinned = state.pinned();
    let mut seen: std::collections::HashSet<String> =
        pinned.iter().map(|app| app.path.to_lowercase()).collect();
    apps.retain(|app| seen.insert(app.path.to_lowercase()));
    apps.truncate(30);
    json!({ "apps": apps, "pinned_apps": pinned })
}

fn split_arguments(input: Option<&str>) -> Vec<String> {
    let Some(raw) = input else { return Vec::new() };
    let mut parts = Vec::new();
    let mut value = String::new();
    let mut quoted = false;
    for char in raw.chars() {
        match char {
            '"' => quoted = !quoted,
            c if c.is_whitespace() && !quoted => {
                if !value.is_empty() {
                    parts.push(std::mem::take(&mut value));
                }
            }
            c => value.push(c),
        }
    }
    if !value.is_empty() {
        parts.push(value);
    }
    parts
}

pub fn launch(item: &AppItem) -> Result<(), String> {
    let path = PathBuf::from(&item.path);
    if path.as_os_str().is_empty() || item.path.chars().any(char::is_control) {
        return Err("Invalid application path".into());
    }
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::ffi::OsStrExt;
        if item.aumid.as_ref().is_some_and(|id| !id.is_empty()) {
            let target = format!(
                "shell:AppsFolder\\{}",
                item.aumid.as_deref().unwrap_or_default()
            );
            let wide: Vec<u16> = std::ffi::OsStr::new(&target)
                .encode_wide()
                .chain(Some(0))
                .collect();
            let result = unsafe {
                windows_sys::Win32::UI::Shell::ShellExecuteW(
                    std::ptr::null_mut(),
                    std::ptr::null(),
                    wide.as_ptr(),
                    std::ptr::null(),
                    std::ptr::null(),
                    windows_sys::Win32::UI::WindowsAndMessaging::SW_SHOWNORMAL,
                )
            };
            if result as isize <= 32 {
                return Err("Windows could not open the application".into());
            }
            return Ok(());
        }
        let extension = path.extension().unwrap_or_default().to_string_lossy();
        if extension.eq_ignore_ascii_case("lnk") || extension.eq_ignore_ascii_case("url") {
            use std::os::windows::ffi::OsStrExt;
            let target: Vec<u16> = path.as_os_str().encode_wide().chain(Some(0)).collect();
            let result = unsafe {
                windows_sys::Win32::UI::Shell::ShellExecuteW(
                    std::ptr::null_mut(),
                    std::ptr::null(),
                    target.as_ptr(),
                    std::ptr::null(),
                    std::ptr::null(),
                    windows_sys::Win32::UI::WindowsAndMessaging::SW_SHOWNORMAL,
                )
            };
            if result as isize <= 32 {
                return Err("Windows could not open the shortcut".into());
            }
            return Ok(());
        }
        Command::new(&path)
            .args(split_arguments(item.args.as_deref()))
            .spawn()
            .map_err(|error| error.to_string())?;
    }
    #[cfg(target_os = "macos")]
    {
        let mut command = Command::new("open");
        command
            .arg("-a")
            .arg(&path)
            .args(split_arguments(item.args.as_deref()));
        command.spawn().map_err(|error| error.to_string())?;
    }
    Ok(())
}

#[cfg(target_os = "macos")]
fn applescript_quote(value: &str) -> String {
    value
        .chars()
        .flat_map(|ch| match ch {
            '\\' => "\\\\".chars().collect::<Vec<_>>(),
            '"' => "\\\"".chars().collect(),
            '\n' | '\r' => " ".chars().collect(),
            c => vec![c],
        })
        .collect()
}

pub fn window_action(item: &AppItem, action: &str) -> Result<(), String> {
    if action != "minimize" && action != "close" {
        return Err("Unsupported window action".into());
    }
    #[cfg(target_os = "macos")]
    {
        let app = applescript_quote(&item.name);
        let verb = if action == "close" {
            "close"
        } else {
            "set miniaturized of front window to true"
        };
        let script = if action == "close" {
            format!(
                "tell application \"System Events\" to tell process \"{app}\" to {verb} front window"
            )
        } else {
            format!("tell application \"System Events\" to tell process \"{app}\" to {verb}")
        };
        let result = Command::new("osascript")
            .args(["-e", &script])
            .output()
            .map_err(|error| error.to_string())?;
        if !result.status.success() {
            return Err("Could not control the window. Allow PC Remote under System Settings > Privacy & Security > Automation and Accessibility".into());
        }
        return Ok(());
    }
    #[cfg(target_os = "windows")]
    {
        use windows_sys::Win32::Foundation::{HWND, LPARAM};
        use windows_sys::Win32::UI::WindowsAndMessaging::{
            EnumWindows, GetWindowThreadProcessId, IsWindowVisible, SC_MINIMIZE, SendMessageW,
            WM_CLOSE, WM_SYSCOMMAND,
        };
        use windows_sys::core::BOOL;
        let mut system = System::new();
        system.refresh_processes(sysinfo::ProcessesToUpdate::All, true);
        struct Search<'a> {
            system: &'a System,
            name: String,
            minimize: bool,
            matched: bool,
        }
        unsafe extern "system" fn find(window: HWND, data: LPARAM) -> BOOL {
            let search = unsafe { &mut *(data as *mut Search<'_>) };
            if unsafe { IsWindowVisible(window) } == 0 {
                return 1;
            }
            let mut pid = 0;
            unsafe {
                GetWindowThreadProcessId(window, &mut pid);
            }
            if let Some(process) = search.system.process(sysinfo::Pid::from_u32(pid)) {
                let actual = process.name().to_string_lossy();
                let expected = format!("{}.exe", search.name);
                if actual.eq_ignore_ascii_case(&expected)
                    || actual.eq_ignore_ascii_case(&search.name)
                {
                    let (message, wparam) = if !search.minimize {
                        (WM_CLOSE, 0)
                    } else {
                        (WM_SYSCOMMAND, SC_MINIMIZE as usize)
                    };
                    unsafe {
                        SendMessageW(window, message, wparam, 0);
                    }
                    search.matched = true;
                    return 0;
                }
            }
            1
        }
        let mut search = Search {
            system: &system,
            name: item.name.clone(),
            minimize: action == "minimize",
            matched: false,
        };
        unsafe {
            EnumWindows(Some(find), &mut search as *mut Search as LPARAM);
        }
        if !search.matched {
            return Err("Application window not found".into());
        }
        return Ok(());
    }
    #[allow(unreachable_code)]
    Err("Window control is unavailable".into())
}

pub fn system_info(state: &AppState) -> Value {
    let mut system = System::new();
    system.refresh_memory();
    system.refresh_cpu_usage();
    thread::sleep(Duration::from_millis(80));
    system.refresh_cpu_usage();
    let total = system.total_memory();
    let used = system.used_memory();
    let ip = local_ip();
    let interfaces = if ip.is_loopback() {
        vec![]
    } else {
        vec![
            json!({"name":"Network","ip":ip.to_string(),"speed_mbps":0,"kind":"other","is_virtualbox_host_only":false,"is_preferred_candidate":true}),
        ]
    };
    let uptime = System::uptime();
    let network = json!({"hostname": System::host_name().unwrap_or_else(|| "PC Remote".into()), "current_ip":ip.to_string(), "primary_interface":interfaces.first(), "interfaces":interfaces});
    let audio = json!({ "active_output_device": default_output_device() });
    let (volume, muted) = audio_state(state);
    let battery = battery_info();
    json!({
        "cpu_percent": system.global_cpu_usage(),
        "ram_percent": if total > 0 { used as f32 * 100.0 / total as f32 } else { 0.0 },
        "ram_used_mb": used / 1024,
        "ram_total_mb": total / 1024,
        "uptime_sec": uptime,
        "battery": battery,
        "network": network,
        "audio": audio,
        "volume": volume,
        "muted": muted,
    })
}

#[cfg(target_os = "windows")]
fn battery_info() -> Value {
    use windows_sys::Win32::System::Power::{GetSystemPowerStatus, SYSTEM_POWER_STATUS};
    let mut status = SYSTEM_POWER_STATUS::default();
    if unsafe { GetSystemPowerStatus(&mut status) } == 0
        || status.BatteryFlag == 128
        || status.BatteryLifePercent == 255
    {
        return json!({"present":false,"percent":null,"power_plugged":null,"secs_left":null});
    }
    json!({"present":true,"percent":status.BatteryLifePercent,"power_plugged":status.ACLineStatus == 1,"secs_left":if status.BatteryLifeTime == u32::MAX { Value::Null } else { json!(status.BatteryLifeTime) }})
}

#[cfg(target_os = "macos")]
fn battery_info() -> Value {
    if let Ok(output) = Command::new("pmset").args(["-g", "batt"]).output() {
        if output.status.success() {
            let text = String::from_utf8_lossy(&output.stdout);
            if let Some(percentage) = text
                .split('%')
                .next_back()
                .and_then(|_| text.split('%').next())
                .and_then(|value| value.trim().rsplit(' ').next())
                .and_then(|value| value.parse::<u8>().ok())
            {
                return json!({"present":true,"percent":percentage,"power_plugged":text.contains("AC Power"),"secs_left":null});
            }
        }
    }
    json!({"present":false,"percent":null,"power_plugged":null,"secs_left":null})
}

pub fn power_action(reboot: bool) -> Result<(), String> {
    #[cfg(target_os = "windows")]
    let result = if reboot {
        Command::new("shutdown").args(["/r", "/t", "0"]).spawn()
    } else {
        Command::new("shutdown").args(["/s", "/t", "0"]).spawn()
    };
    #[cfg(target_os = "macos")]
    {
        let output = Command::new("osascript")
            .args([
                "-e",
                if reboot {
                    "tell application \"System Events\" to restart"
                } else {
                    "tell application \"System Events\" to shut down"
                },
            ])
            .output()
            .map_err(|error| error.to_string())?;
        if !output.status.success() {
            let detail = String::from_utf8_lossy(&output.stderr).trim().to_owned();
            return Err(if detail.is_empty() {
                "macOS did not accept the power command. Allow PC Remote under System Settings > Privacy & Security > Automation".into()
            } else {
                format!("macOS did not accept the power command: {detail}")
            });
        }
        Ok(())
    }
    #[cfg(target_os = "windows")]
    result.map(|_| ()).map_err(|error| error.to_string())
}

#[cfg(target_os = "windows")]
pub fn autostart_path() -> Option<PathBuf> {
    env::var_os("APPDATA")
        .map(PathBuf::from)
        .map(|path| path.join("Microsoft/Windows/Start Menu/Programs/Startup/PC Remote.cmd"))
}

#[cfg(target_os = "macos")]
pub fn autostart_path() -> Option<PathBuf> {
    env::var_os("HOME")
        .map(PathBuf::from)
        .map(|path| path.join("Library/LaunchAgents/com.mimaxon1.PCRemote.plist"))
}

#[cfg(target_os = "macos")]
fn supports_smappservice() -> bool {
    Command::new("sw_vers")
        .arg("-productVersion")
        .output()
        .ok()
        .filter(|output| output.status.success())
        .and_then(|output| String::from_utf8(output.stdout).ok())
        .and_then(|version| version.split('.').next()?.parse::<u32>().ok())
        .is_some_and(|major| major >= 13)
}

#[cfg(target_os = "macos")]
fn remove_legacy_autostart() -> Result<(), String> {
    if let Some(path) = autostart_path() {
        if path.exists() {
            fs::remove_file(path).map_err(|error| error.to_string())?;
        }
    }
    Ok(())
}

pub fn autostart_enabled() -> bool {
    #[cfg(target_os = "macos")]
    if supports_smappservice() {
        let status = AppService::new(ServiceType::MainApp).status();
        if status != ServiceStatus::NotRegistered && status != ServiceStatus::NotFound {
            return true;
        }
    }
    autostart_path().is_some_and(|path| path.exists())
}

pub fn set_autostart(enabled: bool) -> Result<(), String> {
    let path = autostart_path().ok_or("Could not locate the current user's startup folder")?;
    #[cfg(target_os = "macos")]
    if supports_smappservice() {
        let service = AppService::new(ServiceType::MainApp);
        let status = service.status();
        if enabled {
            match service.register() {
                Ok(()) | Err(ServiceManagementError::AlreadyRegistered) => {
                    remove_legacy_autostart()?;
                    if service.status() == ServiceStatus::RequiresApproval {
                        AppService::open_system_settings_login_items();
                        return Err(
                            "Approve PC Remote under System Settings > General > Login Items"
                                .into(),
                        );
                    }
                    return Ok(());
                }
                Err(ServiceManagementError::InvalidSignature) => {
                    // Ad-hoc signed builds may not satisfy ServiceManagement's signature policy.
                    // Keep the legacy per-user LaunchAgent as a functional fallback.
                }
                Err(ServiceManagementError::LaunchDeniedByUser) => {
                    AppService::open_system_settings_login_items();
                    return Err(
                        "Enable PC Remote under System Settings > General > Login Items".into(),
                    );
                }
                Err(error) => {
                    return Err(format!("Could not register the macOS login item: {error}"));
                }
            }
        } else {
            if status != ServiceStatus::NotRegistered && status != ServiceStatus::NotFound {
                service.unregister().map_err(|error| {
                    format!("Could not unregister the macOS login item: {error}")
                })?;
            }
            remove_legacy_autostart()?;
            return Ok(());
        }
    }
    if enabled {
        let executable = std::env::current_exe().map_err(|error| error.to_string())?;
        let content = if cfg!(target_os = "windows") {
            format!(
                "@echo off\r\nstart \"\" /b \"{}\"\r\n",
                executable.display()
            )
        } else {
            let executable = executable
                .to_string_lossy()
                .replace('&', "&amp;")
                .replace('<', "&lt;")
                .replace('>', "&gt;")
                .replace('"', "&quot;");
            format!(
                "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<!DOCTYPE plist PUBLIC \"-//Apple//DTD PLIST 1.0//EN\" \"http://www.apple.com/DTDs/PropertyList-1.0.dtd\">\n<plist version=\"1.0\"><dict><key>Label</key><string>com.mimaxon1.PCRemote</string><key>ProgramArguments</key><array><string>{executable}</string></array><key>RunAtLoad</key><true/></dict></plist>\n"
            )
        };
        fs::create_dir_all(path.parent().ok_or("Startup folder is missing")?)
            .map_err(|error| error.to_string())?;
        fs::write(path, content).map_err(|error| error.to_string())?;
    } else if path.exists() {
        fs::remove_file(path).map_err(|error| error.to_string())?;
    }
    Ok(())
}

pub fn scan_shortcuts() -> Vec<AppItem> {
    recent_apps()
}

#[cfg(all(test, target_os = "macos"))]
mod tests {
    use super::parse_macos_audio_settings;

    #[test]
    fn parses_macos_output_volume_and_mute_state_together() {
        assert_eq!(
            parse_macos_audio_settings(
                "output volume:50, input volume:100, alert volume:50, output muted:true"
            ),
            Some((0.5, true))
        );
        assert_eq!(
            parse_macos_audio_settings(
                "output volume:125, input volume:100, alert volume:50, output muted:false"
            ),
            Some((1.0, false))
        );
    }
}
