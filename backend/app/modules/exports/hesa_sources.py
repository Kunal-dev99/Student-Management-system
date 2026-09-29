"""Curated real HESA sources for the assisted advisory ingest (ICR G5).

These are the genuine HESA (Jisc) Student-record coding-manual entry points. HESA protects its
site with an automated-access (bot) wall, so the platform cannot fetch them server-side — the
Registry opens the link in their own browser, downloads or copies the relevant page/PDF, and then
uploads or pastes it into the ingest. This catalog just gives them the right, current links so they
are not hunting for URLs; the ingest → AI-draft → diff → accept pipeline does the rest.

`bot_protected=True` tells the UI to lead with "open + upload" rather than a server fetch.
"""
from __future__ import annotations


# Student-record collection codes are CxxYY1 where xx = the start year (24 = 2024/25). Field pages
# live under a collection at `/a/<FIELDCODE>` (e.g. .../c24051/a/SEXID).
HESA_SOURCES: list[dict] = [
    {
        "id": "hesa_student_2025_26",
        "packCode": "HESA_STUDENT",
        "academicYear": "2025/26",
        "name": "HESA Student record 2025/26 — coding manual",
        "url": "https://www.hesa.ac.uk/collection/c25051",
        "kind": "coding_manual",
        "botProtected": True,
        "description": "The live Student-record collection. Open it, find the field(s) the advisory "
                       "changes (e.g. /a/SEXID), and upload or paste that page.",
    },
    {
        "id": "hesa_student_2024_25",
        "packCode": "HESA_STUDENT",
        "academicYear": "2024/25",
        "name": "HESA Student record 2024/25 — coding manual",
        "url": "https://www.hesa.ac.uk/collection/c24051",
        "kind": "coding_manual",
        "botProtected": True,
        "description": "Previous year's collection — useful for diffing what changed year-on-year.",
    },
    {
        "id": "hesa_collections_index",
        "packCode": "HESA_STUDENT",
        "academicYear": None,
        "name": "HESA collections index (all returns & years)",
        "url": "https://www.hesa.ac.uk/collection",
        "kind": "index",
        "botProtected": True,
        "description": "Every HESA collection and year — the starting point if you need a different "
                       "return or a newer coding manual than the ones listed here.",
    },
    {
        "id": "hesa_data_futures_changes",
        "packCode": "HESA_STUDENT",
        "academicYear": None,
        "name": "HESA Data Futures — changes & release notes",
        "url": "https://www.hesa.ac.uk/innovation/data-futures",
        "kind": "changes",
        "botProtected": True,
        "description": "HESA's programme for changes to the model — where forthcoming advisories and "
                       "release notes are published.",
    },
]


def list_sources() -> list[dict]:
    return HESA_SOURCES


def find_source(source_id: str) -> dict | None:
    return next((s for s in HESA_SOURCES if s["id"] == source_id), None)
