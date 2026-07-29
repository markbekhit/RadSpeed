//! Focus-free status HUD for global-hotkey actions.
//!
//! The tray tooltip remains useful for diagnostics, but it is too easy to miss
//! during reporting. This window appears near the top of the active monitor,
//! never accepts focus or mouse input, and never includes report text.

use serde::Serialize;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::Duration;
use tauri::{App, AppHandle, Manager, PhysicalPosition, Position, WebviewUrl};

const WINDOW_LABEL: &str = "feedback";
static MESSAGE_GENERATION: AtomicU64 = AtomicU64::new(0);

#[derive(Debug, Clone, Copy, Serialize)]
#[serde(rename_all = "lowercase")]
enum Tone {
    Working,
    Success,
    Warning,
    Error,
}

#[derive(Debug, Serialize)]
struct FeedbackPayload<'a> {
    tone: Tone,
    title: &'a str,
    message: &'a str,
}

pub fn build(app: &mut App) -> Result<(), tauri::Error> {
    let builder = tauri::WebviewWindowBuilder::new(
        app,
        WINDOW_LABEL,
        WebviewUrl::App("feedback.html".into()),
    )
    .title("RadSpeed status")
    .inner_size(470.0, 88.0)
    .resizable(false)
    .maximizable(false)
    .minimizable(false)
    .closable(false)
    .decorations(false)
    .always_on_top(true)
    .skip_taskbar(true)
    .focusable(false)
    .focused(false)
    .shadow(true)
    .visible(false);

    // Transparent webviews require a private API feature on macOS. RadSpeed is
    // distributed on Windows, while keeping the Rust tests portable to macOS.
    #[cfg(target_os = "windows")]
    let builder = builder.transparent(true);

    let window = builder.build()?;
    let _ = window.set_ignore_cursor_events(true);
    position_on_active_monitor(&window);
    Ok(())
}

pub fn working(app: &AppHandle, title: &str, message: &str) {
    show(app, Tone::Working, title, message, None);
}

pub fn success(app: &AppHandle, title: &str, message: &str) {
    show(
        app,
        Tone::Success,
        title,
        message,
        Some(Duration::from_secs(6)),
    );
}

pub fn warning(app: &AppHandle, title: &str, message: &str) {
    show(
        app,
        Tone::Warning,
        title,
        message,
        Some(Duration::from_secs(5)),
    );
}

pub fn error(app: &AppHandle, title: &str, message: &str) {
    show(
        app,
        Tone::Error,
        title,
        message,
        Some(Duration::from_secs(9)),
    );
}

fn show(app: &AppHandle, tone: Tone, title: &str, message: &str, hide_after: Option<Duration>) {
    let generation = MESSAGE_GENERATION.fetch_add(1, Ordering::SeqCst) + 1;
    let Some(window) = app.get_webview_window(WINDOW_LABEL) else {
        log::warn!("feedback window unavailable");
        return;
    };

    position_on_active_monitor(&window);
    let payload = FeedbackPayload {
        tone,
        title,
        message,
    };
    match serde_json::to_string(&payload) {
        Ok(json) => {
            if let Err(error) = window.eval(&format!(
                "window.RadSpeedFeedback && window.RadSpeedFeedback.show({json})"
            )) {
                log::warn!("feedback update failed: {error}");
            }
        }
        Err(error) => log::warn!("feedback serialisation failed: {error}"),
    }
    if let Err(error) = window.show() {
        log::warn!("feedback show failed: {error}");
    }

    if let Some(delay) = hide_after {
        let app = app.clone();
        tauri::async_runtime::spawn(async move {
            tokio::time::sleep(delay).await;
            if MESSAGE_GENERATION.load(Ordering::SeqCst) == generation {
                if let Some(window) = app.get_webview_window(WINDOW_LABEL) {
                    let _ = window.hide();
                }
            }
        });
    }
}

fn position_on_active_monitor(window: &tauri::WebviewWindow) {
    let monitor = window
        .cursor_position()
        .ok()
        .and_then(|cursor| window.monitor_from_point(cursor.x, cursor.y).ok().flatten())
        .or_else(|| window.primary_monitor().ok().flatten());

    let Some(monitor) = monitor else {
        return;
    };
    let monitor_size = monitor.size();
    let monitor_origin = monitor.position();
    let window_width = window.outer_size().map(|size| size.width).unwrap_or(470);
    let x = monitor_origin.x + (monitor_size.width.saturating_sub(window_width) / 2) as i32;
    let y = monitor_origin.y + (24.0 * monitor.scale_factor()) as i32;
    let _ = window.set_position(Position::Physical(PhysicalPosition::new(x, y)));
}

pub fn friendly_error(error: &str) -> &'static str {
    let lower = error.to_ascii_lowercase();
    if lower.contains("clipboard empty") || lower.contains("no text selected") {
        "Select the FINDINGS text first, copy it, then press the hotkey again."
    } else if lower.contains("http 429") || lower.contains("rate limit") {
        "The hourly impression limit has been reached. Please try again later."
    } else if lower.contains("http 502") || lower.contains("http 503") || lower.contains("http 504")
    {
        "The AI service is temporarily unavailable. Please try again."
    } else if lower.contains("request failed")
        || lower.contains("timed out")
        || lower.contains("timeout")
    {
        "RadSpeed could not be reached. Check the internet connection and try again."
    } else {
        "The hotkey action could not be completed. Try again or open RadSpeed."
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn maps_server_failures_to_plain_language() {
        assert_eq!(
            friendly_error("fetch_impression: HTTP 502 Bad Gateway"),
            "The AI service is temporarily unavailable. Please try again."
        );
    }

    #[test]
    fn maps_empty_capture_to_actionable_guidance() {
        assert_eq!(
            friendly_error("capture_selection: clipboard empty"),
            "Select the FINDINGS text first, copy it, then press the hotkey again."
        );
    }

    #[test]
    fn does_not_echo_unexpected_internal_errors() {
        assert_eq!(
            friendly_error("secret provider detail"),
            "The hotkey action could not be completed. Try again or open RadSpeed."
        );
    }
}
