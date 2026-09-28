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

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum ReportListKind {
    Ordered,
    Bullet,
}

#[derive(Debug)]
struct ReportListRun {
    kind: ReportListKind,
    start: u32,
}

#[derive(Debug)]
struct ReportRtfLine {
    original: String,
    content: String,
    list: Option<(usize, ReportListKind, u32)>,
}

fn ordered_list_item(line: &str) -> Option<(u32, &str)> {
    let trimmed = line.trim_start();
    let digit_count = trimmed.chars().take_while(|ch| ch.is_ascii_digit()).count();
    if digit_count == 0 {
        return None;
    }
    let (digits, suffix) = trimmed.split_at(digit_count);
    let suffix = suffix
        .strip_prefix('.')
        .or_else(|| suffix.strip_prefix(')'))?;
    if !suffix.starts_with(char::is_whitespace) {
        return None;
    }
    let content = suffix.trim_start();
    if content.is_empty() {
        return None;
    }
    Some((digits.parse().ok()?, content))
}

fn bullet_list_item(line: &str) -> Option<&str> {
    let trimmed = line.trim_start();
    for marker in ["-", "*", "\u{2022}"] {
        if let Some(suffix) = trimmed.strip_prefix(marker) {
            if suffix.starts_with(char::is_whitespace) {
                let content = suffix.trim_start();
                if !content.is_empty() {
                    return Some(content);
                }
            }
        }
    }
    None
}

fn parse_rtf_lines(text: &str) -> (Vec<ReportRtfLine>, Vec<ReportListRun>) {
    let normalised = text.replace("\r\n", "\n").replace('\r', "\n");
    let mut lines = Vec::new();
    let mut runs = Vec::new();
    let mut active_run: Option<(usize, ReportListKind)> = None;

    for line in normalised.split('\n') {
        let parsed = if let Some((number, content)) = ordered_list_item(line) {
            Some((ReportListKind::Ordered, number, content))
        } else {
            bullet_list_item(line).map(|content| (ReportListKind::Bullet, 1, content))
        };

        if let Some((kind, number, content)) = parsed {
            let run_index = match active_run {
                Some((run_index, active_kind)) if active_kind == kind => run_index,
                _ => {
                    let run_index = runs.len();
                    runs.push(ReportListRun {
                        kind,
                        start: number,
                    });
                    active_run = Some((run_index, kind));
                    run_index
                }
            };
            lines.push(ReportRtfLine {
                original: line.to_string(),
                content: content.to_string(),
                list: Some((run_index, kind, number)),
            });
        } else {
            active_run = None;
            lines.push(ReportRtfLine {
                original: line.to_string(),
                content: line.to_string(),
                list: None,
            });
        }
    }
    (lines, runs)
}

fn push_rtf_text(rtf: &mut String, text: &str) {
    for ch in text.chars() {
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
}

fn push_html_text(html: &mut String, text: &str) {
    for ch in text.chars() {
        match ch {
            '&' => html.push_str("&amp;"),
            '<' => html.push_str("&lt;"),
            '>' => html.push_str("&gt;"),
            '"' => html.push_str("&quot;"),
            '\'' => html.push_str("&#39;"),
            '\t' => html.push_str("&emsp;"),
            _ => html.push(ch),
        }
    }
}

fn matching_bold_prefix<'a>(line: &str, bold_prefixes: &'a [String]) -> Option<&'a str> {
    let trimmed = line.trim_start();
    bold_prefixes
        .iter()
        .map(|prefix| prefix.trim())
        .filter(|prefix| !prefix.is_empty() && trimmed.starts_with(prefix) && trimmed != *prefix)
        .max_by_key(|prefix| prefix.len())
}

fn push_html_line(html: &mut String, line: &str, bold_prefixes: &[String]) {
    let Some(prefix) = matching_bold_prefix(line, bold_prefixes) else {
        push_html_text(html, line);
        return;
    };
    let start = line.len() - line.trim_start().len();
    push_html_text(html, &line[..start]);
    html.push_str("<b>");
    push_html_text(html, prefix);
    html.push_str("</b>");
    push_html_text(html, &line[start + prefix.len()..]);
}

fn report_html_fragment(text: &str, bold_lines: &[String], bold_prefixes: &[String]) -> String {
    let bold: HashSet<&str> = bold_lines.iter().map(|line| line.trim()).collect();
    let normalised = text.replace("\r\n", "\n").replace('\r', "\n");
    let mut html = String::from(r#"<span style="font-family:Arial,sans-serif;font-size:10pt">"#);
    for (index, line) in normalised.split('\n').enumerate() {
        if index > 0 {
            html.push_str("<br>");
        }
        let trimmed = line.trim();
        let is_bold = !trimmed.is_empty() && bold.contains(trimmed);
        if is_bold {
            html.push_str("<b>");
        }
        if is_bold {
            push_html_text(&mut html, line);
        } else {
            push_html_line(&mut html, line, bold_prefixes);
        }
        if is_bold {
            html.push_str("</b>");
        }
    }
    html.push_str("</span>");
    html
}

/// Build the Windows CF_HTML payload used by Office-style rich-text editors.
/// Byte offsets are required because reports can contain non-ASCII characters.
fn report_cf_html(text: &str, bold_lines: &[String], bold_prefixes: &[String]) -> Vec<u8> {
    const START_MARKER: &str = "<!--StartFragment-->";
    const END_MARKER: &str = "<!--EndFragment-->";
    const HEADER_TEMPLATE: &str = concat!(
        "Version:0.9\r\n",
        "StartHTML:0000000000\r\n",
        "EndHTML:0000000000\r\n",
        "StartFragment:0000000000\r\n",
        "EndFragment:0000000000\r\n",
    );

    let fragment = report_html_fragment(text, bold_lines, bold_prefixes);
    let document = format!(
        "<html><body>{START_MARKER}{fragment}{END_MARKER}</body></html>"
    );
    let start_html = HEADER_TEMPLATE.len();
    let start_fragment = start_html + document.find(START_MARKER).unwrap() + START_MARKER.len();
    let end_fragment = start_html + document.find(END_MARKER).unwrap();
    let end_html = start_html + document.len();
    let header = format!(
        "Version:0.9\r\nStartHTML:{start_html:010}\r\nEndHTML:{end_html:010}\r\nStartFragment:{start_fragment:010}\r\nEndFragment:{end_fragment:010}\r\n"
    );
    debug_assert_eq!(header.len(), HEADER_TEMPLATE.len());

    let mut payload = format!("{header}{document}").into_bytes();
    payload.push(0);
    payload
}

fn push_rtf_list_tables(rtf: &mut String, runs: &[ReportListRun]) {
    if runs.is_empty() {
        return;
    }

    rtf.push_str(r"{\*\listtable");
    for (index, run) in runs.iter().enumerate() {
        let list_id = 1000 + index;
        let template_id = 2000 + index;
        let _ = write!(
            rtf,
            r"{{\list\listtemplateid{template_id}\listhybrid{{\listlevel"
        );
        match run.kind {
            ReportListKind::Ordered => {
                let _ = write!(
                    rtf,
                    r"\levelnfc0\levelnfcn0\leveljc0\leveljcn0\levelfollow0\levelstartat{}\levelspace0\levelindent0{{\leveltext\leveltemplateid{template_id}\'02\'00.;}}{{\levelnumbers\'01;}}\fi-360\li720\lin720\tx720",
                    run.start
                );
            }
            ReportListKind::Bullet => {
                rtf.push_str(
                    r"\levelnfc23\levelnfcn23\leveljc0\leveljcn0\levelfollow0\levelstartat1\levelspace0\levelindent0{\leveltext\leveltemplateid",
                );
                let _ = write!(
                    rtf,
                    r"{template_id}\'01\u8226 ?;}}{{\levelnumbers;}}\fi-360\li720\lin720\tx720"
                );
            }
        }
        let _ = write!(rtf, r"}}{{\listname ;}}\listid{list_id}}}");
    }
    rtf.push('}');

    rtf.push_str(r"{\*\listoverridetable");
    for (index, _) in runs.iter().enumerate() {
        let list_id = 1000 + index;
        let list_number = index + 1;
        let _ = write!(
            rtf,
            r"{{\listoverride\listid{list_id}\listoverridecount0\ls{list_number}}}"
        );
    }
    rtf.push('}');
}

/// Build a compact RTF document for native Windows clipboard consumers.
/// PowerScribe reads this format but ignores Chromium's text/html clipboard
/// flavour. Markdown-style list lines become native Rich Edit list paragraphs,
/// so adding or removing an item keeps PowerScribe's numbering correct.
fn push_rtf_line(rtf: &mut String, line: &str, bold_prefixes: &[String]) {
    let Some(prefix) = matching_bold_prefix(line, bold_prefixes) else {
        push_rtf_text(rtf, line);
        return;
    };
    let start = line.len() - line.trim_start().len();
    push_rtf_text(rtf, &line[..start]);
    rtf.push_str(r"\b ");
    push_rtf_text(rtf, prefix);
    rtf.push_str(r"\b0 ");
    push_rtf_text(rtf, &line[start + prefix.len()..]);
}

fn report_rtf(text: &str, bold_lines: &[String], bold_prefixes: &[String]) -> Vec<u8> {
    let bold: HashSet<&str> = bold_lines.iter().map(|line| line.trim()).collect();
    let (lines, list_runs) = parse_rtf_lines(text);
    let mut rtf = String::from(r#"{\rtf1\ansi\deff0{\fonttbl{\f0 Arial;}}\viewkind4\uc1"#);
    push_rtf_list_tables(&mut rtf, &list_runs);

    for (index, line) in lines.iter().enumerate() {
        if index > 0 {
            rtf.push_str(r"\par ");
        }
        rtf.push_str(r"\pard\plain\sa0\sb0\f0\fs20 ");
        if let Some((run_index, kind, number)) = line.list {
            let list_number = run_index + 1;
            let _ = write!(
                rtf,
                r"\ls{list_number}\ilvl0\fi-360\li720\lin720\tx720{{\listtext\pard\plain\f0\fs20 "
            );
            match kind {
                ReportListKind::Ordered => {
                    let _ = write!(rtf, "{number}.\\tab");
                }
                ReportListKind::Bullet => rtf.push_str(r"\u8226?\tab"),
            }
            rtf.push_str("} ");
        }
        let trimmed = line.original.trim();
        let is_bold = !trimmed.is_empty() && bold.contains(trimmed);
        if is_bold {
            rtf.push_str(r"\b ");
        }
        if is_bold {
            push_rtf_text(&mut rtf, &line.content);
        } else {
            push_rtf_line(&mut rtf, &line.content, bold_prefixes);
        }
        if is_bold {
            rtf.push_str(r"\b0 ");
        }
    }
    rtf.push('}');
    rtf.push('\0');
    rtf.into_bytes()
}

/// Put Unicode text plus both native RTF and CF_HTML on the Windows clipboard.
/// PowerScribe versions differ in which rich format they accept, so matching
/// the formats offered by Office gives each version a compatible choice.
#[cfg(target_os = "windows")]
pub fn set_report_clipboard_rtf(
    text: &str,
    bold_lines: &[String],
    bold_prefixes: &[String],
) -> Result<(), String> {
    use clipboard_win::{formats, raw, Clipboard as WindowsClipboard, Setter};

    let rtf_format = raw::register_format("Rich Text Format")
        .ok_or_else(|| "Windows did not register the RTF clipboard format".to_string())?;
    let html_format = raw::register_format("HTML Format")
        .ok_or_else(|| "Windows did not register the HTML clipboard format".to_string())?;
    let _clipboard =
        WindowsClipboard::new_attempts(10).map_err(|e| format!("clipboard open: {e}"))?;
    raw::empty().map_err(|e| format!("clipboard clear: {e}"))?;
    formats::Unicode
        .write_clipboard(&text)
        .map_err(|e| format!("clipboard text set: {e}"))?;
    raw::set_without_clear(
        html_format.get(),
        &report_cf_html(text, bold_lines, bold_prefixes),
    )
        .map_err(|e| format!("clipboard HTML set: {e}"))?;
    raw::set_without_clear(
        rtf_format.get(),
        &report_rtf(text, bold_lines, bold_prefixes),
    )
        .map_err(|e| format!("clipboard RTF set: {e}"))
}

#[cfg(not(target_os = "windows"))]
pub fn set_report_clipboard_rtf(
    _text: &str,
    _bold_lines: &[String],
    _bold_prefixes: &[String],
) -> Result<(), String> {
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
#[cfg(target_os = "windows")]
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

#[cfg(not(target_os = "windows"))]
pub fn paste_block(_payload: &str) -> Result<(), String> {
    Err("PowerScribe paste is available on Windows only".to_string())
}

#[cfg(test)]
mod tests {
    use super::{report_cf_html, report_rtf};

    #[test]
    fn report_rtf_bolds_only_named_lines_and_keeps_compact_breaks() {
        let rtf = report_rtf(
            "FINDINGS:\nMenisci\nMedial meniscus: Tear.\n\nIMPRESSION:\n1. Tear.",
            &["FINDINGS:".into(), "Menisci".into(), "IMPRESSION:".into()],
            &["Medial meniscus:".into()],
        );
        let value = String::from_utf8(rtf).unwrap();

        assert!(value.contains(r"\b FINDINGS:\b0 \par \pard\plain\sa0\sb0\f0\fs20 \b Menisci\b0"));
        assert!(value.contains(r"\b Medial meniscus:\b0  Tear."));
        assert!(value.contains(r"\par \pard\plain\sa0\sb0\f0\fs20 \par \pard\plain\sa0\sb0\f0\fs20 \b IMPRESSION:\b0 \par \pard\plain\sa0\sb0\f0\fs20 \ls1\ilvl0"));
        assert!(value.contains(r"{\listtext\pard\plain\f0\fs20 1.\tab} Tear."));
        assert!(value.ends_with("}\0"));
    }

    #[test]
    fn report_rtf_escapes_control_characters_and_unicode() {
        let value = String::from_utf8(report_rtf("A \\ {test} café", &[], &[])).unwrap();

        assert!(value.contains(r"A \\ \{test\} caf\u233?"));
    }

    #[test]
    fn report_rtf_emits_native_numbered_and_bulleted_lists() {
        let value = String::from_utf8(report_rtf(
            "IMPRESSION:\n1. First finding.\n2. Second finding.\n\nNOTES:\n- First note.\n- Second note.",
            &["IMPRESSION:".into(), "NOTES:".into()],
            &[],
        ))
        .unwrap();

        assert!(value.contains(r"{\*\listtable"));
        assert!(value.contains(r"\levelnfc0\levelnfcn0"));
        assert!(value.contains(r"\leveltext\leveltemplateid2000\'02\'00.;"));
        assert!(value.contains(r"\levelnfc23\levelnfcn23"));
        assert!(value.contains(r"\leveltext\leveltemplateid2001\'01\u8226 ?;"));
        assert!(value.contains(r"{\listoverride\listid1000\listoverridecount0\ls1}"));
        assert!(value.contains(r"{\listoverride\listid1001\listoverridecount0\ls2}"));
        assert!(value.contains(r"\ls1\ilvl0\fi-360\li720\lin720\tx720{\listtext\pard\plain\f0\fs20 1.\tab} First finding."));
        assert!(value.contains(r"\ls1\ilvl0\fi-360\li720\lin720\tx720{\listtext\pard\plain\f0\fs20 2.\tab} Second finding."));
        assert!(value.contains(r"\ls2\ilvl0\fi-360\li720\lin720\tx720{\listtext\pard\plain\f0\fs20 \u8226?\tab} First note."));
        assert!(!value.contains("1. First finding."));
        assert!(!value.contains("- First note."));
    }

    #[test]
    fn report_rtf_restarts_separate_numbered_lists() {
        let value = String::from_utf8(report_rtf(
            "1. First.\n2. Second.\n\n1. New first.\n2. New second.",
            &[],
            &[],
        ))
        .unwrap();

        assert!(value.contains(r"\listid1000"));
        assert!(value.contains(r"\listid1001"));
        assert!(value.contains(r"\ls1\ilvl0"));
        assert!(value.contains(r"\ls2\ilvl0"));
    }

    #[test]
    fn report_cf_html_has_valid_byte_offsets_and_bold_headings() {
        let bytes = report_cf_html(
            "FINDINGS:\nMenisci\nCafé intact.\n\nIMPRESSION:\nNo tear.",
            &["FINDINGS:".into(), "Menisci".into(), "IMPRESSION:".into()],
            &[],
        );
        let value = String::from_utf8(bytes[..bytes.len() - 1].to_vec()).unwrap();
        let offset = |name: &str| -> usize {
            value
                .lines()
                .find(|line| line.starts_with(name))
                .unwrap()
                .split_once(':')
                .unwrap()
                .1
                .parse()
                .unwrap()
        };

        let start_html = offset("StartHTML");
        let end_html = offset("EndHTML");
        let start_fragment = offset("StartFragment");
        let end_fragment = offset("EndFragment");
        assert_eq!(&value.as_bytes()[start_html..start_html + 6], b"<html>");
        assert_eq!(&value.as_bytes()[end_html - 7..end_html], b"</html>");
        let fragment = std::str::from_utf8(&value.as_bytes()[start_fragment..end_fragment]).unwrap();
        assert!(fragment.contains("<b>FINDINGS:</b><br><b>Menisci</b>"));
        assert!(fragment.contains("Café intact.<br><br><b>IMPRESSION:</b>"));
    }

    #[test]
    fn report_formats_inline_subheading_prefixes_without_bolding_findings() {
        let text = "FINDINGS:\nMedial meniscus: Oblique tear.\nACL and PCL: Intact.";
        let prefixes = &["Medial meniscus:".into(), "ACL and PCL:".into()];
        let rtf = String::from_utf8(report_rtf(
            text,
            &["FINDINGS:".into()],
            prefixes,
        ))
        .unwrap();
        let html_bytes = report_cf_html(text, &["FINDINGS:".into()], prefixes);
        let html = String::from_utf8(html_bytes[..html_bytes.len() - 1].to_vec()).unwrap();

        assert!(rtf.contains(r"\b Medial meniscus:\b0  Oblique tear."));
        assert!(rtf.contains(r"\b ACL and PCL:\b0  Intact."));
        assert!(!rtf.contains(r"\b Oblique tear"));
        assert!(html.contains("<b>Medial meniscus:</b> Oblique tear."));
        assert!(html.contains("<b>ACL and PCL:</b> Intact."));
    }
}
