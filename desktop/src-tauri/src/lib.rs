//! RadSpeed Windows desktop companion — library entry point.
//!
//! The binary in `main.rs` simply calls `run()`. Splitting library / binary
//! lets us keep the door open for tauri::mobile_entry_point and unit tests
//! without the binary getting in the way.

mod api;
mod feedback;
mod hotkey;
mod keyboard;
mod settings;
mod tray;
pub(crate) mod updater;

use serde::Deserialize;
use tauri::{AppHandle, LogicalSize, Manager, PhysicalPosition, Position, Size};
use tauri_plugin_autostart::ManagerExt as AutostartManagerExt;
use tauri_plugin_global_shortcut::{GlobalShortcutExt, ShortcutState};

use crate::settings::Settings;

// ---------- Tauri commands invoked by the settings window frontend ----------

#[tauri::command]
fn cmd_get_settings(app: AppHandle) -> Settings {
    settings::load(&app)
}

#[derive(Debug, Deserialize)]
struct SaveBody {
    settings: Settings,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct CopyReportRtfBody {
    text: String,
    bold_lines: Vec<String>,
    #[serde(default)]
    bold_prefixes: Vec<String>,
}

#[tauri::command]
fn cmd_copy_report_rtf(body: CopyReportRtfBody) -> Result<(), String> {
    const MAX_REPORT_CHARS: usize = 200_000;
    const MAX_BOLD_LINES: usize = 500;
    const MAX_BOLD_PREFIXES: usize = 500;
    const MAX_BOLD_LINE_CHARS: usize = 500;

    if body.text.chars().count() > MAX_REPORT_CHARS {
        return Err("Report is too long to copy".to_string());
    }
    if body.bold_lines.len() > MAX_BOLD_LINES
        || body
            .bold_lines
            .iter()
            .any(|line| line.chars().count() > MAX_BOLD_LINE_CHARS)
    {
        return Err("Report has too many formatted headings".to_string());
    }
    if body.bold_prefixes.len() > MAX_BOLD_PREFIXES
        || body
            .bold_prefixes
            .iter()
            .any(|prefix| prefix.chars().count() > MAX_BOLD_LINE_CHARS)
    {
        return Err("Report has too many formatted subheadings".to_string());
    }
    keyboard::set_report_clipboard_rtf(&body.text, &body.bold_lines, &body.bold_prefixes)
}

#[tauri::command]
fn cmd_save_settings(app: AppHandle, body: SaveBody) -> Result<(), String> {
    settings::save(&app, &body.settings)?;
    rebind_hotkey(&app, &body.settings.hotkey)?;
    tray::set_status(&app, "Settings saved.");
    Ok(())
}

#[tauri::command]
async fn cmd_test_api(api_base: String) -> Result<(), String> {
    api::ping(&api_base).await
}

#[tauri::command]
fn cmd_hide_settings(app: AppHandle) {
    if let Some(window) = app.get_webview_window("settings") {
        let _ = window.hide();
    }
}

#[tauri::command]
fn cmd_get_version() -> String {
    env!("CARGO_PKG_VERSION").to_string()
}

#[tauri::command]
fn cmd_show_app(app: AppHandle) {
    if let Ok(mut app_url) = url::Url::parse(&settings::load(&app).api_base) {
        app_url.set_path("/app");
        app_url.set_query(Some("desktop=overlay"));
        if let Some(window) = app.get_webview_window("app") {
            let _ = window.navigate(app_url);
        }
    }
    show_app_window(&app);
}

#[tauri::command]
fn cmd_show_reporting_settings(app: AppHandle) -> Result<(), String> {
    let api_base = settings::load(&app).api_base;
    let mut settings_url = url::Url::parse(&api_base)
        .map_err(|error| format!("Invalid RadSpeed cloud URL: {error}"))?;
    settings_url.set_path("/settings");
    settings_url.set_query(None);
    settings_url.set_fragment(None);

    let window = app
        .get_webview_window("app")
        .ok_or_else(|| "RadSpeed window is not available".to_string())?;
    window
        .navigate(settings_url)
        .map_err(|error| format!("Could not open reporting preferences: {error}"))?;
    let _ = window.show();
    let _ = window.set_focus();
    Ok(())
}

#[tauri::command]
fn cmd_show_settings(app: AppHandle) {
    if let Some(window) = app.get_webview_window("settings") {
        let _ = window.show();
        let _ = window.set_focus();
    }
}

#[tauri::command]
fn cmd_set_compact_mode(app: AppHandle, compact: bool) {
    let Some(window) = app.get_webview_window("app") else {
        return;
    };
    if compact {
        let _ = window.set_resizable(true);
        let _ = window.set_size(Size::Logical(LogicalSize::new(520.0, 300.0)));
        let _ = window.set_always_on_top(true);
        position_app_overlay(&window);
    } else {
        let _ = window.set_always_on_top(false);
        let _ = window.set_resizable(true);
        let _ = window.set_size(Size::Logical(LogicalSize::new(1400.0, 900.0)));
        let _ = window.center();
    }
}

pub(crate) fn show_app_window(app: &AppHandle) {
    if let Some(window) = app.get_webview_window("app") {
        let _ = window.show();
        let _ = window.set_focus();
    }
}

fn position_app_overlay(window: &tauri::WebviewWindow) {
    let monitor = window
        .cursor_position()
        .ok()
        .and_then(|cursor| window.monitor_from_point(cursor.x, cursor.y).ok().flatten())
        .or_else(|| window.primary_monitor().ok().flatten());
    let Some(monitor) = monitor else { return; };
    let monitor_size = monitor.size();
    let monitor_origin = monitor.position();
    let window_size = window.outer_size().ok();
    let width = window_size.map(|size| size.width).unwrap_or(520);
    let x = monitor_origin.x + monitor_size.width.saturating_sub(width + 24) as i32;
    let y = monitor_origin.y + (56.0 * monitor.scale_factor()) as i32;
    let _ = window.set_position(Position::Physical(PhysicalPosition::new(x, y)));
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum InitialWindow {
    App,
    Settings,
}

fn initial_window(is_first_run: bool) -> InitialWindow {
    if is_first_run {
        InitialWindow::Settings
    } else {
        InitialWindow::App
    }
}

#[tauri::command]
fn cmd_trigger_now(app: AppHandle) {
    hotkey::run_impressions_flow(app);
}

// ---------- Hotkey lifecycle ----------

fn rebind_hotkey(app: &AppHandle, spec: &str) -> Result<(), String> {
    let new_shortcut = hotkey::parse(spec)?;
    let gs = app.global_shortcut();
    let _ = gs.unregister_all();
    let app_clone = app.clone();
    let target_shortcut = new_shortcut.clone();
    gs.on_shortcut(new_shortcut, move |_app, shortcut, event| {
        if shortcut == &target_shortcut && event.state() == ShortcutState::Pressed {
            hotkey::run_impressions_flow(app_clone.clone());
        }
    })
    .map_err(|e| format!("register hotkey: {e}"))?;
    Ok(())
}

fn enable_start_with_windows(app: &AppHandle) {
    let autostart = app.autolaunch();
    match autostart.is_enabled() {
        Ok(true) => log::info!("start with Windows is enabled"),
        Ok(false) => match autostart.enable() {
            Ok(()) => log::info!("enabled start with Windows"),
            Err(error) => log::warn!("could not enable start with Windows: {error}"),
        },
        Err(error) => log::warn!("could not read start with Windows state: {error}"),
    }
}

// ---------- Entry point ----------

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let _ = env_logger::try_init();

    tauri::Builder::default()
        // Must be registered first so duplicate launches are caught before
        // any expensive setup happens. The callback runs in the original
        // (already-running) instance and brings the main app window forward.
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            show_app_window(app);
        }))
        .plugin(tauri_plugin_autostart::init(
            tauri_plugin_autostart::MacosLauncher::LaunchAgent,
            None,
        ))
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .plugin(tauri_plugin_process::init())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .invoke_handler(tauri::generate_handler![
            cmd_get_settings,
            cmd_save_settings,
            cmd_test_api,
            cmd_hide_settings,
            cmd_trigger_now,
            cmd_show_app,
            cmd_show_reporting_settings,
            cmd_show_settings,
            cmd_set_compact_mode,
            cmd_get_version,
            cmd_copy_report_rtf,
        ])
        .setup(|app| {
            tray::build(app)?;
            feedback::build(app)?;
            enable_start_with_windows(app.handle());

            // Prevent the settings window's close button from quitting the app.
            // Hide instead — tray menu is the canonical app exit path.
            if let Some(window) = app.get_webview_window("settings") {
                let win = window.clone();
                window.on_window_event(move |event| {
                    if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                        api.prevent_close();
                        let _ = win.hide();
                    }
                });
            }

            // Build the full-app window (loads the RadSpeed web app in WebView2).
            // Hidden until the user clicks "Open RadSpeed" in the tray menu.
            let api_base = settings::load(app.handle()).api_base;
            let mut app_url = url::Url::parse(&api_base)
                .unwrap_or_else(|_| url::Url::parse("https://radspeed.com.au").unwrap());
            app_url.set_path("/app");
            app_url.set_query(Some("desktop=overlay"));
            let app_window = tauri::WebviewWindowBuilder::new(
                app,
                "app",
                tauri::WebviewUrl::External(app_url),
            )
            .title("RadSpeed")
            .inner_size(520.0, 300.0)
            .min_inner_size(420.0, 280.0)
            .resizable(true)
            // Runs on every navigation, including the query-free OAuth return.
            .initialization_script("window.__RADSPEED_DESKTOP_OVERLAY__ = true;")
            .always_on_top(true)
            .visible(false)
            .build()?;

            // Close button hides; tray menu is the exit path.
            let win = app_window.clone();
            app_window.on_window_event(move |event| {
                if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                    api.prevent_close();
                    let _ = win.hide();
                }
            });
            position_app_overlay(&app_window);

            // Register the configured hotkey at boot.
            let cfg = settings::load(app.handle());
            if let Err(e) = rebind_hotkey(app.handle(), &cfg.hotkey) {
                log::warn!("hotkey bind failed at startup: {e}");
                tray::set_status(app.handle(), &format!("Hotkey error: {e}"));
            } else {
                tray::set_status(
                    app.handle(),
                    &format!("Ready. Hotkey: {}", cfg.hotkey),
                );
            }

            // Show exactly one window at launch. A new install needs settings;
            // later launches open the web app. The settings window can open the
            // app after Save, without two windows competing for focus.
            match initial_window(first_run(app.handle())) {
                InitialWindow::App => {
                    let _ = app_window.show();
                    let _ = app_window.set_focus();
                }
                InitialWindow::Settings => {
                    if let Some(window) = app.get_webview_window("settings") {
                        let _ = window.show();
                        let _ = window.set_focus();
                    }
                }
            }

            // Background update check after 10 s — lets the tray settle first
            // and avoids a restart in the first seconds of the app's life.
            let app_for_update = app.handle().clone();
            tauri::async_runtime::spawn(async move {
                tokio::time::sleep(std::time::Duration::from_secs(10)).await;
                updater::run(app_for_update);
            });

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running RadSpeed desktop");
}

fn first_run(app: &AppHandle) -> bool {
    let dir = match app.path().app_config_dir() {
        Ok(d) => d,
        Err(_) => return true,
    };
    !dir.join("config.json").exists()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn first_run_opens_only_settings() {
        assert_eq!(initial_window(true), InitialWindow::Settings);
    }

    #[test]
    fn configured_launch_opens_only_app() {
        assert_eq!(initial_window(false), InitialWindow::App);
    }

    #[test]
    fn desktop_registers_start_with_windows() {
        let source = include_str!("lib.rs");
        assert!(source.contains("tauri_plugin_autostart::init"));
        assert!(source.contains("enable_start_with_windows(app.handle())"));
        assert!(source.contains("api.prevent_close()"));
        assert!(source.contains("win.hide()"));
    }

    #[test]
    fn desktop_exposes_reporting_preferences() {
        let source = include_str!("lib.rs");
        let html = include_str!("../../src/index.html");
        let javascript = include_str!("../../src/main.js");
        assert!(source.contains("settings_url.set_path(\"/settings\")"));
        assert!(html.contains("Reporting preferences"));
        assert!(html.contains("Roman or Arabic numerals"));
        assert!(javascript.contains("cmd_show_reporting_settings"));
    }

    #[test]
    fn local_settings_commands_are_allowed_by_acl() {
        let capability = include_str!("../capabilities/default.json");
        let permissions = include_str!("../permissions/report-copy.toml");
        assert!(capability.contains("allow-settings-commands"));
        for command in [
            "cmd_get_settings",
            "cmd_save_settings",
            "cmd_test_api",
            "cmd_hide_settings",
            "cmd_trigger_now",
            "cmd_show_app",
            "cmd_show_settings",
            "cmd_show_reporting_settings",
            "cmd_set_compact_mode",
            "cmd_get_version",
        ] {
            assert!(
                permissions.contains(command),
                "missing ACL permission for {command}"
            );
        }
    }
}
