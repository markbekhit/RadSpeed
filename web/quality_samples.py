"""Opt-in, de-identified quality samples stored in RadSpeed's user database."""

from __future__ import annotations

import re
from typing import Optional

from web.auth_oauth import _conn


RETENTION_DAYS = 365
_MAX_TEXT_CHARS = 100_000

_IDENTIFIER_KEYS = {
    "patient_name": "[PATIENT_NAME]",
    "patient_dob": "[DATE]",
    "patient_id": "[PATIENT_ID]",
    "accession": "[ACCESSION]",
    "referring_physician": "[REFERRER]",
}

_LABELLED_IDENTIFIER_RE = re.compile(
    r"(?im)\b(name|patient\s*name|dob|date\s+of\s+birth|mrn|medical\s+record\s+number|"
    r"patient\s*id|accession(?:\s+number)?|referrer|referring\s+physician|address)"
    r"\s*[:#=-]\s*([^\n;]{2,100})"
)
_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
_PHONE_RE = re.compile(r"(?<!\w)(?:\+\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?){2,4}\d{3,4}(?!\w)")
_MEDICARE_RE = re.compile(r"(?<!\d)\d{4}[ -]?\d{5}[ -]?\d(?!\d)")
_STREET_ADDRESS_RE = re.compile(
    r"\b\d{1,5}\s+[A-Za-z][A-Za-z .'-]{1,60}\s+"
    r"(?:street|st|road|rd|avenue|ave|drive|dr|lane|ln|court|ct|place|pl|"
    r"boulevard|blvd|terrace|tce|crescent|cres)\b[^.\n,;]*",
    re.I,
)
_NUMERIC_DATE_RE = re.compile(
    r"\b(?:\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4})\b"
)
_WRITTEN_DATE_RE = re.compile(
    r"\b(?:\d{1,2}\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|"
    r"Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|"
    r"Nov(?:ember)?|Dec(?:ember)?)|(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|"
    r"Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|"
    r"Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2},?)\s+\d{4}\b",
    re.I,
)


def init_quality_samples() -> None:
    with _conn() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS quality_samples (
                id            INTEGER PRIMARY KEY,
                user_id       INTEGER NOT NULL REFERENCES users(id),
                kind          TEXT NOT NULL,
                source_text   TEXT NOT NULL,
                output_text   TEXT NOT NULL,
                feedback_text TEXT,
                template_name TEXT,
                model_name    TEXT,
                source_kind   TEXT,
                created_at    TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        db.execute(
            "CREATE INDEX IF NOT EXISTS idx_quality_samples_user_created "
            "ON quality_samples(user_id, created_at)"
        )
        db.commit()


def deidentify_text(text: Optional[str], patient_context: Optional[dict] = None) -> str:
    """Remove known and common free-text identifiers without using AI."""
    cleaned = str(text or "")[:_MAX_TEXT_CHARS]
    cleaned = _LABELLED_IDENTIFIER_RE.sub(lambda match: f"{match.group(1)}: [REDACTED]", cleaned)
    cleaned = _EMAIL_RE.sub("[EMAIL]", cleaned)
    cleaned = _PHONE_RE.sub("[PHONE]", cleaned)
    cleaned = _MEDICARE_RE.sub("[MEDICARE]", cleaned)
    cleaned = _STREET_ADDRESS_RE.sub("[ADDRESS]", cleaned)
    cleaned = _NUMERIC_DATE_RE.sub("[DATE]", cleaned)
    cleaned = _WRITTEN_DATE_RE.sub("[DATE]", cleaned)
    for key, placeholder in _IDENTIFIER_KEYS.items():
        value = str((patient_context or {}).get(key) or "").strip()
        if len(value) >= 2:
            cleaned = re.sub(re.escape(value), placeholder, cleaned, flags=re.I)
            if key in {"patient_id", "accession"}:
                compact = re.sub(r"[^A-Za-z0-9]", "", value)
                if len(compact) >= 4:
                    flexible = r"[\s-]*".join(re.escape(char) for char in compact)
                    cleaned = re.sub(flexible, placeholder, cleaned, flags=re.I)
            elif key in {"patient_name", "referring_physician"}:
                for part in re.findall(r"[A-Za-z][A-Za-z'-]{2,}", value):
                    cleaned = re.sub(r"\b" + re.escape(part) + r"\b", placeholder, cleaned, flags=re.I)
    return cleaned.strip()


def purge_quality_samples(user_id: Optional[int] = None) -> int:
    """Delete expired samples for one user, or for all users."""
    init_quality_samples()
    with _conn() as db:
        if user_id is None:
            cursor = db.execute(
                "DELETE FROM quality_samples WHERE created_at < datetime('now', ?)",
                (f"-{RETENTION_DAYS} days",),
            )
        else:
            cursor = db.execute(
                "DELETE FROM quality_samples "
                "WHERE user_id = ? AND created_at < datetime('now', ?)",
                (user_id, f"-{RETENTION_DAYS} days"),
            )
        db.commit()
        return max(cursor.rowcount, 0)


def delete_quality_samples(user_id: int) -> int:
    """Delete all retained samples when a user withdraws opt-in."""
    with _conn() as db:
        cursor = db.execute("DELETE FROM quality_samples WHERE user_id = ?", (user_id,))
        db.commit()
        return max(cursor.rowcount, 0)


def set_quality_retention(user_id: int, enabled: bool) -> int:
    """Change consent and delete withdrawn samples in one transaction."""
    init_quality_samples()
    with _conn() as db:
        db.execute(
            """INSERT INTO user_settings (user_id, retain_deidentified_samples)
               VALUES (?, ?)
               ON CONFLICT(user_id) DO UPDATE SET
                   retain_deidentified_samples = excluded.retain_deidentified_samples""",
            (user_id, int(bool(enabled))),
        )
        removed = 0
        if not enabled:
            cursor = db.execute("DELETE FROM quality_samples WHERE user_id = ?", (user_id,))
            removed = max(cursor.rowcount, 0)
        db.commit()
    return removed


def save_quality_sample(
    *,
    user_id: Optional[int],
    enabled: bool,
    kind: str,
    source_text: str,
    output_text: str,
    feedback_text: Optional[str] = None,
    patient_context: Optional[dict] = None,
    template_name: Optional[str] = None,
    model_name: Optional[str] = None,
    source_kind: Optional[str] = None,
) -> bool:
    if not enabled or user_id is None:
        return False
    source = deidentify_text(source_text, patient_context)
    output = deidentify_text(output_text, patient_context)
    feedback = deidentify_text(feedback_text, patient_context) if feedback_text else None
    if not source or not output:
        return False
    purge_quality_samples(user_id)
    with _conn() as db:
        cursor = db.execute(
            """INSERT INTO quality_samples (
                   user_id, kind, source_text, output_text, feedback_text,
                   template_name, model_name, source_kind
               )
               SELECT ?, ?, ?, ?, ?, ?, ?, ?
                 FROM user_settings
                WHERE user_id = ? AND retain_deidentified_samples = 1""",
            (
                user_id, kind, source, output, feedback,
                template_name, model_name, source_kind, user_id,
            ),
        )
        db.commit()
    return cursor.rowcount == 1
