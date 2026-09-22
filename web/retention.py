"""Scheduled purge of stored patient data.

Australian Privacy Principle 11.2 requires health information to be destroyed
or de-identified once it is no longer needed. RadSpeed is a drafting tool: the
practice's RIS holds the report of record, so RadSpeed's own copies only need
to live long enough to support amendments and audit review.

Two controls, both off (0 days) unless set or unless the practice profile is
active:

``RADSPEED_RETENTION_DAYS``
    Report rows older than this are *scrubbed*: the report text and the
    patient identifiers are replaced, but the row, its hash, its version chain
    and every audit event are kept. The audit chain therefore still verifies.
    Completed or dismissed follow-ups older than this are scrubbed too.

``RADSPEED_OUTBOX_RETENTION_DAYS``
    HL7, DICOM SR, FHIR and worklist files in the working directory older than
    this are deleted. The integration engine has long since consumed them.

``run_once()`` performs one pass and records a ``retention_purge`` audit event
with the counts. The web app schedules it in the background.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

from config.config import config
from config import practice
from web.audit import _conn, log_event

logger = logging.getLogger(__name__)

PURGED_TEXT = "[purged under retention policy]"
_OUTBOX_SUFFIXES = (".hl7", ".dcm", ".json")
_OUTBOX_SUBDIRS = ("hl7_outbox", "sr_outbox", "hl7_inbox", "hl7_inbox/archive", "hl7_inbox/quarantine")


def _cutoff(days: int, now: Optional[datetime] = None) -> str:
    now = now or datetime.now(timezone.utc)
    return (now - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")


def scrub_reports(days: int, now: Optional[datetime] = None) -> int:
    """Replace report text and identifiers on rows older than *days*."""
    if days <= 0:
        return 0
    cutoff = _cutoff(days, now)
    with _conn() as db:
        cur = db.execute(
            """
            UPDATE reports
               SET report_text = ?, patient_name = NULL, patient_dob = NULL,
                   patient_id = NULL, referring = NULL
             WHERE created_at < ? AND report_text != ?
            """,
            (PURGED_TEXT, cutoff, PURGED_TEXT),
        )
        count = cur.rowcount or 0
        db.commit()
    return count


def scrub_followups(days: int, now: Optional[datetime] = None) -> int:
    """Scrub closed follow-ups older than *days*; open ones are still work."""
    if days <= 0:
        return 0
    cutoff = _cutoff(days, now)
    with _conn() as db:
        try:
            cur = db.execute(
                """
                UPDATE followups
                   SET patient_name = NULL, patient_id = NULL, finding = NULL,
                       notes = NULL, recommendation = ?
                 WHERE status != 'open' AND updated_at < ? AND recommendation != ?
                """,
                (PURGED_TEXT, cutoff, PURGED_TEXT),
            )
            count = cur.rowcount or 0
        except Exception as exc:  # table may not exist in minimal installs
            logger.debug("[retention] followups scrub skipped: %s", exc)
            count = 0
        db.commit()
    return count


def _candidate_dirs() -> list[str]:
    dirs: list[str] = []
    base = config.save_directory
    if base:
        dirs.append(base)
        for sub in _OUTBOX_SUBDIRS:
            dirs.append(os.path.join(base, sub))
    for explicit in (config.hl7_outbox_path, config.hl7_inbox_path, config.dicom_sr_outbox_path):
        if explicit:
            dirs.append(explicit)
    seen: list[str] = []
    for d in dirs:
        if d not in seen and os.path.isdir(d):
            seen.append(d)
    return seen


def _is_export_file(name: str) -> bool:
    lower = name.lower()
    if not lower.endswith(_OUTBOX_SUFFIXES):
        return False
    if lower.endswith(".json"):
        # Only RadSpeed's own exports and worklist drops, never settings files.
        return lower.endswith("_report.json") or lower.startswith("mwl_")
    return True


def purge_outboxes(days: int, now_ts: Optional[float] = None,
                   directories: Optional[Iterable[str]] = None) -> int:
    """Delete export files older than *days* from the working directories."""
    if days <= 0:
        return 0
    now_ts = now_ts or time.time()
    cutoff_ts = now_ts - days * 86400
    removed = 0
    for directory in (directories if directories is not None else _candidate_dirs()):
        try:
            entries = os.listdir(directory)
        except OSError:
            continue
        for name in entries:
            if not _is_export_file(name):
                continue
            path = os.path.join(directory, name)
            try:
                if os.path.isfile(path) and os.path.getmtime(path) < cutoff_ts:
                    os.remove(path)
                    removed += 1
            except OSError as exc:
                logger.warning("[retention] could not remove %s: %s", path, exc)
    return removed


def run_once(*, user_id: Optional[int] = None, now: Optional[datetime] = None) -> dict:
    """Run every retention control once and audit the result."""
    s = practice.settings
    result = {
        "reports_scrubbed": scrub_reports(s.retention_days, now),
        "followups_scrubbed": scrub_followups(s.retention_days, now),
        "files_removed": purge_outboxes(s.outbox_retention_days),
        "retention_days": s.retention_days,
        "outbox_retention_days": s.outbox_retention_days,
    }
    if any(result[k] for k in ("reports_scrubbed", "followups_scrubbed", "files_removed")):
        log_event(user_id=user_id, event_type="retention_purge", metadata=result)
        logger.info("[retention] %s", result)
    return result


def enabled() -> bool:
    s = practice.settings
    return s.retention_days > 0 or s.outbox_retention_days > 0
