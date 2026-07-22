"""Radiologist-owned follow-up register.

Suggestions are deliberately deterministic and advisory.  RadSpeed never
creates a clinical follow-up task from model output without the radiologist
explicitly confirming it in the UI.
"""
from __future__ import annotations

import re
from typing import Optional

from web.auth_oauth import _conn


FOLLOWUP_STATUSES = ("open", "completed", "dismissed")
_RECOMMENDATION_RE = re.compile(
    r"\b(?:follow[ -]?up|recommend(?:ed|ation)?|surveillance|"
    r"further\s+(?:imaging|assessment|evaluation)|repeat\s+(?:imaging|scan|"
    r"ultrasound|mri|ct|radiograph)|interval\s+(?:imaging|scan|assessment))\b",
    re.IGNORECASE,
)
_NO_FOLLOWUP_RE = re.compile(
    r"\b(?:no|not)\s+(?:further\s+)?follow[ -]?up\s+(?:is\s+)?(?:required|needed|recommended)\b",
    re.IGNORECASE,
)


def init_followup_db() -> None:
    """Create the follow-up table and indexes idempotently."""
    with _conn() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS followups (
                id              INTEGER PRIMARY KEY,
                user_id         INTEGER NOT NULL REFERENCES users(id),
                report_id       INTEGER REFERENCES reports(id),
                patient_id      TEXT,
                patient_name    TEXT,
                accession       TEXT,
                finding         TEXT,
                recommendation  TEXT NOT NULL,
                due_date        TEXT,
                status          TEXT NOT NULL DEFAULT 'open',
                notes           TEXT,
                completed_at    TEXT,
                created_at      TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at      TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        db.execute(
            "CREATE INDEX IF NOT EXISTS followups_user_status_idx "
            "ON followups(user_id, status, due_date)"
        )
        db.execute(
            "CREATE INDEX IF NOT EXISTS followups_accession_idx "
            "ON followups(accession)"
        )
        db.commit()


def _serialise(row) -> dict:
    return {
        "id": row[0],
        "user_id": row[1],
        "report_id": row[2],
        "patient_id": row[3],
        "patient_name": row[4],
        "accession": row[5],
        "finding": row[6],
        "recommendation": row[7],
        "due_date": row[8],
        "status": row[9],
        "notes": row[10],
        "completed_at": row[11],
        "created_at": row[12],
        "updated_at": row[13],
    }


_COLS = (
    "id, user_id, report_id, patient_id, patient_name, accession, finding, "
    "recommendation, due_date, status, notes, completed_at, created_at, updated_at"
)


def suggest_followups(report_text: str, limit: int = 5) -> list[dict]:
    """Return report sentences that look like actionable recommendations.

    This is intentionally conservative: it finds explicit recommendation
    language and excludes explicit statements that no follow-up is required.
    It does not infer an interval or decide whether follow-up is clinically
    appropriate.
    """
    if not report_text:
        return []
    # Headings and bullets often separate recommendations without full stops.
    chunks = re.split(r"(?<=[.!?])\s+|[\r\n]+|\s+[•]\s+", report_text)
    out: list[dict] = []
    seen: set[str] = set()
    for raw in chunks:
        sentence = re.sub(r"^[\s#>*\-\d.)]+", "", raw).strip()
        sentence = re.sub(r"\*+", "", sentence).strip()
        if not sentence or _NO_FOLLOWUP_RE.search(sentence):
            continue
        if not _RECOMMENDATION_RE.search(sentence):
            continue
        key = sentence.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append({"recommendation": sentence[:1000]})
        if len(out) >= max(1, int(limit)):
            break
    return out


def create_followup(
    *,
    user_id: int,
    recommendation: str,
    report_id: Optional[int] = None,
    patient_id: Optional[str] = None,
    patient_name: Optional[str] = None,
    accession: Optional[str] = None,
    finding: Optional[str] = None,
    due_date: Optional[str] = None,
    notes: Optional[str] = None,
) -> dict:
    if not recommendation or not recommendation.strip():
        raise ValueError("recommendation required")
    with _conn() as db:
        cur = db.execute(
            "INSERT INTO followups "
            "(user_id, report_id, patient_id, patient_name, accession, finding, "
            " recommendation, due_date, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                user_id, report_id, patient_id, patient_name, accession, finding,
                recommendation.strip(), due_date, notes,
            ),
        )
        row_id = int(cur.lastrowid)
        db.commit()
        row = db.execute(f"SELECT {_COLS} FROM followups WHERE id = ?", (row_id,)).fetchone()
    return _serialise(row)


def list_followups(user_id: int, status: Optional[str] = "open", limit: int = 200) -> list[dict]:
    args: list = [user_id]
    sql = f"SELECT {_COLS} FROM followups WHERE user_id = ?"
    if status:
        if status not in FOLLOWUP_STATUSES:
            raise ValueError("invalid status")
        sql += " AND status = ?"
        args.append(status)
    sql += " ORDER BY CASE WHEN due_date IS NULL OR due_date = '' THEN 1 ELSE 0 END, due_date, id DESC LIMIT ?"
    args.append(min(max(int(limit), 1), 1000))
    with _conn() as db:
        rows = db.execute(sql, args).fetchall()
    return [_serialise(row) for row in rows]


def update_followup(
    followup_id: int,
    user_id: int,
    *,
    status: Optional[str] = None,
    due_date: Optional[str] = None,
    notes: Optional[str] = None,
) -> Optional[dict]:
    if status is not None and status not in FOLLOWUP_STATUSES:
        raise ValueError("invalid status")
    sets: list[str] = []
    args: list = []
    if status is not None:
        sets.append("status = ?")
        args.append(status)
        sets.append("completed_at = CASE WHEN ? = 'completed' THEN CURRENT_TIMESTAMP ELSE NULL END")
        args.append(status)
    if due_date is not None:
        sets.append("due_date = ?")
        args.append(due_date or None)
    if notes is not None:
        sets.append("notes = ?")
        args.append(notes or None)
    if not sets:
        with _conn() as db:
            row = db.execute(
                f"SELECT {_COLS} FROM followups WHERE id = ? AND user_id = ?",
                (followup_id, user_id),
            ).fetchone()
        return _serialise(row) if row else None
    sets.append("updated_at = CURRENT_TIMESTAMP")
    args.extend([followup_id, user_id])
    with _conn() as db:
        cur = db.execute(
            f"UPDATE followups SET {', '.join(sets)} WHERE id = ? AND user_id = ?",
            args,
        )
        if cur.rowcount == 0:
            return None
        db.commit()
        row = db.execute(f"SELECT {_COLS} FROM followups WHERE id = ?", (followup_id,)).fetchone()
    return _serialise(row)
