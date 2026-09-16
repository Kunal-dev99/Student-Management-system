"""Assisted advisory ingest — fetch a published HESA document and turn it into text (ICR G5).

The Registry points the platform at the source (a URL, or an uploaded PDF/notice); this module
pulls the readable text out of it. That text is then handed to the ordinary ingest pipeline, where
the AI read-layer drafts the change directives and the deterministic parser produces the diff — and
a human still accepts. Nothing here decides anything; it only turns bytes into text.
"""
from __future__ import annotations

import html as _html
import re

import httpx

from app.core.errors import ValidationAppError

# Cap on the text handed downstream (to the model): a full spec PDF can be huge, and the change
# advisory is near the top. Keeps the extraction call bounded.
MAX_TEXT_CHARS = 20000


def _pdf_text(data: bytes) -> str:
    from io import BytesIO

    from pypdf import PdfReader

    try:
        reader = PdfReader(BytesIO(data))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception as exc:  # noqa: BLE001 - surface a clean message, not a stack trace
        raise ValidationAppError(f"Could not read the PDF: {exc}") from exc


def _html_to_text(markup: str) -> str:
    markup = re.sub(r"(?is)<(script|style|head)[^>]*>.*?</\1>", " ", markup)
    text = re.sub(r"(?s)<[^>]+>", " ", markup)
    text = _html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n\s*\n\s*\n+", "\n\n", text).strip()


def extract_text(data: bytes, *, content_type: str = "", filename: str = "") -> str:
    """Best-effort plain text from an uploaded/fetched document (PDF, HTML or text)."""
    ct = (content_type or "").lower()
    name = (filename or "").lower()

    if "pdf" in ct or name.endswith(".pdf") or data[:5] == b"%PDF-":
        text = _pdf_text(data)
    else:
        decoded = data.decode("utf-8", errors="replace")
        looks_html = "html" in ct or name.endswith((".html", ".htm")) or "<html" in decoded[:2000].lower()
        text = _html_to_text(decoded) if looks_html else decoded

    text = text.strip()
    return text[:MAX_TEXT_CHARS]


async def fetch_url(url: str) -> tuple[bytes, str]:
    """GET a URL and return (body, content-type). Only http/https; admin-triggered."""
    if not url.lower().startswith(("http://", "https://")):
        raise ValidationAppError("URL must start with http:// or https://")
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=20.0) as client:
            resp = await client.get(url, headers={"User-Agent": "PGR-Platform/1.0 (advisory ingest)"})
            resp.raise_for_status()
            return resp.content, resp.headers.get("content-type", "")
    except httpx.HTTPStatusError as exc:
        raise ValidationAppError(f"The source returned {exc.response.status_code} for that URL") from exc
    except httpx.HTTPError as exc:
        raise ValidationAppError(f"Could not fetch that URL: {exc}") from exc
