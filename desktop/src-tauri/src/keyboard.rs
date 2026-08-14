//! Keyboard simulation via `enigo` + clipboard via `arboard`.
//!
//! Notes from the AHK helper iterations:
//!   - Always release every modifier explicitly. Lingering Ctrl turns later
//!     `Send` calls into shortcut activations (`v` becomes Ctrl+V repeats,
//!     letters become invisible bind activations, etc.).
//!   - Prefer Shift+Insert over Ctrl+V for paste. Most Windows text fields
//!     accept Shift+Insert and it sidesteps the modifier-collision class
//!     of bugs entirely.
//!   - Build the entire paste payload on the clipboard up front. Don't
//!     SendText the heading char-by-char — every char is another chance
//!     for a modifier to interfere.

use arboard::Clipboard;
use enigo::{Direction, Enigo, Key, Keyboard, Settings};
use std::collections::HashSet;
use std::fmt::Write;
use std::thread;
use std::time::Duration;

const MOD_SETTLE_MS: u64 = 30;
const CLIP_SETTLE_MS: u64 = 180;

fn new_enigo() -> Result<Enigo, String> {
    Enigo::new(&Settings::default()).map_err(|e| format!("enigo init: {e}"))
}

/// Save the current clipboard, simulate Ctrl+C to grab the active selection,
/// read the resulting clipboard, then restore the previous clipboard.
///
/// If Ctrl+C is blocked by UIPI (the target window runs at a higher integrity
/// level than RadSpeed, which is common for medical software like PowerScribe
/// One), the clipboard will be empty after our attempt.
///
/// `allow_stale_fallback` controls what happens then. In `goto_impression` mode
/// the user pre-copies the FINDINGS by design, so the pre-existing clipboard IS
/// the intended input (pass `true`). In the live-selection modes
/// (`after_selection` / `replace_selection` / `at_cursor`) falling back to the
/// old clipboard would feed a PREVIOUS patient's text into the report, so we
/// return an empty string instead (pass `false`) and let the caller error out.
pub fn capture_selection(allow_stale_fallback: bool) -> Result<String, String> {
    // Snapshot existing clipboard before we clear it.
    let saved = Clipboard::new().ok().and_then(|mut c| c.get_text().ok());

    // Clear so we can detect "nothing was selected / Ctrl+C was blocked".
    if let Ok(mut c) = Clipboard::new() {
        let _ = c.set_text("");
    }

    let mut enigo = new_enigo()?;
    enigo
        .key(Key::Control, Direction::Press)
        .map_err(|e| format!("ctrl press: {e}"))?;
    thread::sleep(Duration::from_millis(MOD_SETTLE_MS));
    enigo
        .key(Key::Unicode('c'), Direction::Click)
        .map_err(|e| format!("c click: {e}"))?;
    thread::sleep(Duration::from_millis(MOD_SETTLE_MS));
    enigo
        .key(Key::Control, Direction::Release)
        .map_err(|e| format!("ctrl release: {e}"))?;
    thread::sleep(Duration::from_millis(CLIP_SETTLE_MS));

    let captured = Clipboard::new()
        .ok()
        .and_then(|mut c| c.get_text().ok())
        .unwrap_or_default();

    if !captured.is_empty() {
        // Ctrl+C captured a live selection. Restore original clipboard and
        // return the captured text.
        if let Some(orig) = saved {
            if let Ok(mut c) = Clipboard::new() {
                let _ = c.set_text(orig);
            }
        }
        return Ok(captured);
    }

    // Ctrl+C produced nothing — either UIPI blocked it or nothing was
    // selected. Restore the saved clipboard so we don't leave it cleared.
    let fallback = saved.unwrap_or_default();
    if let Ok(mut c) = Clipboard::new() {
        let _ = c.set_text(&fallback);
    }
    if allow_stale_fallback {
        // goto_impression: pre-copied text is the intended input.
        Ok(fallback)
    } else {
        // Live-selection modes: never silently reuse the old clipboard.
        Ok(String::new())
    }
}

/// Write text to the clipboard without simulating any keystrokes.
/// Use this when the paste target may be running at a higher privilege level
/// (UIPI blocks SendInput but clipboard writes are cross-integrity).
pub fn set_clipboard(text: &str) -> Result<(), String> {
    Clipboard::new()
        .map_err(|e| format!("clipboard init: {e}"))?
        .set_text(text)
        .map_err(|e| format!("clipboard set: {e}"))
}

/// Build a compact RTF document for native Windows clipboard consumers.
/// PowerScribe reads this format but ignores Chromium's text/html clipboard
/// flavour. Lines identified by the web report renderer remain bold.
fn report_rtf(text: &str, bold_lines: &[String]) -> Vec<u8> {
    let bold: HashSet<&str> = bold_lines.iter().map(|line| line.trim()).collect();
    let mut rtf = String::from(r#"{\rtf1\ansi\deff0{\fonttbl{\f0 Arial;}}\viewkind4\uc1\f0\fs20 "#);

    for (index, line) in text
        .replace("\r\n", "\n")
        .replace('\r', "\n")
        .split('\n')
        .enumerate()
    {
        if index > 0 {
            rtf.push_str(r"\line ");
        }
        let trimmed = line.trim();
        let is_bold = !trimmed.is_empty() && bold.contains(trimmed);
        if is_bold {
            rtf.push_str(r"\b ");
        }
        for ch in line.chars() {
            match ch {
                '\\' => rtf.push_str(r"\\"),
                '{' => rtf.push_str(r"\{"),
                '}' => rtf.push_str(r"\}"),
                '\t' => rtf.push_str(r"\tab "),
                ch if ch.is_ascii() => rtf.push(ch),
                ch => {
                    let mut utf16 = [0; 2];
                    for unit in ch.encode_utf16(&mut utf16) {
                        let signed = *unit as i16;
                        let _ = write!(rtf, r"\u{signed}?");
                    }
                }
            }
        }
        if is_bold {
            rtf.push_str(r"\b0 ");
        }
    }
    rtf.push('}');
    rtf.push('\0');
    rtf.into_bytes()
}

/// Put both Unicode text and native RTF on the Windows clipboard. This gives
/// PowerScribe its preferred rich-text format while preserving a plain-text
/// fallback for every other target.
#[cfg(target_os = "windows")]
pub fn set_report_clipboard_rtf(text: &str, bold_lines: &[String]) -> Result<(), String> {
    use clipboard_win::{formats, raw, Clipboard as WindowsClipboard, Setter};

    let rtf_format = raw::register_format("Rich Text Format")
        .ok_or_else(|| "Windows did not register the RTF clipboard format".to_string())?;
    let _clipboard =
        WindowsClipboard::new_attempts(10).map_err(|e| format!("clipboard open: {e}"))?;
    raw::empty().map_err(|e| format!("clipboard clear: {e}"))?;
    formats::Unicode
        .write_clipboard(&text)
        .map_err(|e| format!("clipboard text set: {e}"))?;
    raw::set_without_clear(rtf_format.get(), &report_rtf(text, bold_lines))
        .map_err(|e| format!("clipboard RTF set: {e}"))
}

#[cfg(not(target_os = "windows"))]
pub fn set_report_clipboard_rtf(_text: &str, _bold_lines: &[String]) -> Result<(), String> {
    Err("PowerScribe RTF copy is available on Windows only".to_string())
}

/// Send a sequence like "tab", "tab tab", or "down enter" — space-separated
/// keystroke names. Used by goto_impression to navigate from FINDINGS to
/// the IMPRESSION field in PowerScribe One templates.
pub fn send_keys(spec: &str) -> Result<(), String> {
    let spec = spec.trim();
    if spec.is_empty() {
        return Ok(());
    }
    let mut enigo = new_enigo()?;
    for token in spec.split_whitespace() {
        let key = match token.to_lowercase().as_str() {
            "tab" => Key::Tab,
            "enter" | "return" => Key::Return,
            "down" => Key::DownArrow,
            "up" => Key::UpArrow,
            "right" => Key::RightArrow,
            "left" => Key::LeftArrow,
            "home" => Key::Home,
            "end" => Key::End,
            "pgdn" | "pagedown" => Key::PageDown,
            "pgup" | "pageup" => Key::PageUp,
            // Single character literal — useful for things like "f5" later.
            other if other.len() == 1 => Key::Unicode(other.chars().next().unwrap()),
            other => {
                log::warn!("unknown jump key: {other}");
                continue;
            }
        };
        enigo
            .key(key, Direction::Click)
            .map_err(|e| format!("send {token}: {e}"))?;
        thread::sleep(Duration::from_millis(20));
    }
    Ok(())
}

/// Place `payload` on the clipboard and trigger Shift+Insert to paste.
/// The previous clipboard is NOT restored automatically — call sites that
/// want preservation should snapshot beforehand.
pub fn paste_block(payload: &str) -> Result<(), String> {
    let mut clipboard = Clipboard::new().map_err(|e| format!("clipboard init: {e}"))?;
    clipboard
        .set_text(payload)
        .map_err(|e| format!("clipboard set: {e}"))?;
    thread::sleep(Duration::from_millis(CLIP_SETTLE_MS));

    let mut enigo = new_enigo()?;
    enigo
        .key(Key::Shift, Direction::Press)
        .map_err(|e| format!("shift press: {e}"))?;
    thread::sleep(Duration::from_millis(MOD_SETTLE_MS));
    enigo
        .key(Key::Insert, Direction::Click)
        .map_err(|e| format!("insert click: {e}"))?;
    thread::sleep(Duration::from_millis(MOD_SETTLE_MS));
    enigo
        .key(Key::Shift, Direction::Release)
        .map_err(|e| format!("shift release: {e}"))?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::report_rtf;

    #[test]
    fn report_rtf_bolds_only_named_lines_and_keeps_compact_breaks() {
        let rtf = report_rtf(
            "FINDINGS:\nMenisci\nMedial meniscus: Tear.\n\nIMPRESSION:\n1. Tear.",
            &["FINDINGS:".into(), "Menisci".into(), "IMPRESSION:".into()],
        );
        let value = String::from_utf8(rtf).unwrap();

        assert!(value.contains(r"\b FINDINGS:\b0 \line \b Menisci\b0 \line Medial meniscus: Tear."));
        assert!(value.contains(r"\line \line \b IMPRESSION:\b0 \line 1. Tear."));
        assert!(!value.contains(r"\b Medial meniscus"));
        assert!(value.ends_with("}\0"));
    }

    #[test]
    fn report_rtf_escapes_control_characters_and_unicode() {
        let value = String::from_utf8(report_rtf("A \\ {test} café", &[])).unwrap();

        assert!(value.contains(r"A \\ \{test\} caf\u233?"));
    }
}
