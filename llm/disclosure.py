"""AI-assistance disclosure line for signed reports.

Ahpra's guidance on AI in healthcare and the RANZCR Standards of Practice
(S9.3, R9.3) expect a practice to be transparent that a language model drafted
a report and that the radiologist remains the author of record. When
``RADSPEED_AI_DISCLOSURE_FOOTER`` is on (default in the practice profile) the
line below is appended to the report text at sign-off, so the HL7, DICOM SR
and FHIR copies all carry it. It is added once; re-signing or amending a
report that already carries the line does not duplicate it.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from config import practice

_MARKER = "AI-assisted draft"


def disclosure_line(radiologist: Optional[str], on: Optional[date] = None) -> str:
    template = practice.settings.ai_disclosure_text
    return template.format(
        radiologist=(radiologist or "the reporting radiologist").strip(),
        date=(on or date.today()).strftime("%d %b %Y"),
    ).strip()


def has_disclosure(report_text: str) -> bool:
    return _MARKER.lower() in (report_text or "").lower()


def append_disclosure(report_text: str, radiologist: Optional[str],
                      on: Optional[date] = None) -> str:
    """Return *report_text* with the disclosure line appended when enabled."""
    if not practice.settings.ai_disclosure_footer:
        return report_text
    if has_disclosure(report_text):
        return report_text
    body = (report_text or "").rstrip()
    return f"{body}\n\n{disclosure_line(radiologist, on)}\n"
