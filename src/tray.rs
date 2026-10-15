use std::sync::{Arc, atomic::Ordering};

use tao::{
    event::Event,
    event_loop::{ControlFlow, EventLoopBuilder},
};
use tray_icon::{
    Icon, TrayIconBuilder,
    menu::{Menu, MenuEvent, MenuItem, PredefinedMenuItem},
};

use crate::{config, platform, state::AppState};

#[derive(Clone)]
enum UiAction {
    Pair,
    OpenController,
    ToggleAutostart,
    Quit,
}

fn pairing_page() -> String {
    format!(
        "http://127.0.0.1:{}/_tray/qr",
        config::port("PC_REMOTE_WEB_PORT", config::WEB_PORT_DEFAULT)
    )
}

fn open_pairing_page() {
    let _ = open::that(pairing_page());
}

fn open_controller() {
    let _ = open::that(format!(
        "http://127.0.0.1:{}",
        config::port("PC_REMOTE_WEB_PORT", config::WEB_PORT_DEFAULT)
    ));
}

fn menu() -> Result<Menu, Box<dyn std::error::Error>> {
    let menu = Menu::new();
    let pair = MenuItem::with_id("show-pairing-qr", "Show phone pairing QR code", true, None);
    let open = MenuItem::with_id("open-controller", "Open PC Remote", true, None);
    let startup = MenuItem::with_id(
        "toggle-autostart",
        if platform::autostart_enabled() {
            "Disable start at login"
        } else {
            "Start at login"
        },
        true,
        None,
    );
    let quit = MenuItem::with_id("quit", "Exit PC Remote", true, None);
    menu.append(&pair)?;
    menu.append(&open)?;
    menu.append(&PredefinedMenuItem::separator())?;
    menu.append(&startup)?;
    menu.append(&PredefinedMenuItem::separator())?;
    menu.append(&quit)?;
    Ok(menu)
}

fn icon() -> Result<Icon, String> {
    let decoded = image::load_from_memory(include_bytes!("../web/icons/icon-192.png"))
        .map_err(|error| error.to_string())?
        .to_rgba8();
    let (width, height) = decoded.dimensions();
    Icon::from_rgba(decoded.into_raw(), width, height).map_err(|error| error.to_string())
}

pub fn run(state: Arc<AppState>) -> Result<(), String> {
    let event_loop = EventLoopBuilder::<UiAction>::with_user_event().build();
    let tray_menu = menu().map_err(|error| error.to_string())?;
    let _icon = TrayIconBuilder::new()
        .with_tooltip(if state.auth_ready() {
            "PC Remote 2.0"
        } else {
            "PC Remote: scan QR to finish setup"
        })
        .with_icon(icon()?)
        .with_menu(Box::new(tray_menu))
        .build()
        .map_err(|error| format!("Could not create the system-tray icon: {error}"))?;

    let proxy = event_loop.create_proxy();
    MenuEvent::set_event_handler(Some(move |event: MenuEvent| {
        let action = match event.id.as_ref() {
            "show-pairing-qr" => Some(UiAction::Pair),
            "open-controller" => Some(UiAction::OpenController),
            "toggle-autostart" => Some(UiAction::ToggleAutostart),
            "quit" => Some(UiAction::Quit),
            _ => None,
        };
        if let Some(action) = action {
            let _ = proxy.send_event(action);
        }
    }));

    let restart = Arc::clone(&state);
    event_loop.run(move |event, _target, control_flow| {
        *control_flow = ControlFlow::Wait;
        if let Event::UserEvent(action) = event {
            match action {
                UiAction::Pair => open_pairing_page(),
                UiAction::OpenController => open_controller(),
                UiAction::ToggleAutostart => {
                    let enabled = !platform::autostart_enabled();
                    match platform::set_autostart(enabled) {
                        Ok(()) => restart.log(if enabled {
                            "Autostart enabled"
                        } else {
                            "Autostart disabled"
                        }),
                        Err(error) => restart.log(&format!("Autostart update failed: {error}")),
                    }
                }
                UiAction::Quit => *control_flow = ControlFlow::Exit,
            }
        }
        if restart.restart_requested.load(Ordering::Relaxed) {
            *control_flow = ControlFlow::Exit;
        }
    })
}
