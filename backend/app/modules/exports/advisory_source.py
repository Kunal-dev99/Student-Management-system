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


# Markers that mean a bot-protection interstitial (Cloudflare et al.) was served instead of the
# real document. Feeding this to the AI would produce nonsense, so we detect and refuse it with an
# actionable message. HESA's coding manual is Cloudflare-protected, so a server fetch hits this.
_BOT_WALL_MARKERS = (
    "just a moment",
    "performing security verification",
    "enable javascript and cookies to continue",
    "attention required",
    "cf-chl",
    "__cf_chl",
    "cf-browser-verification",
    "checking your browser before accessing",
)


def looks_bot_blocked(text: str) -> bool:
    low = (text or "")[:2000].lower()
    return any(m in low for m in _BOT_WALL_MARKERS)


def _html_to_text(markup: str) -> str:
    markup = re.sub(r"(?is)<(script|style|head|nav|footer)[^>]*>.*?</\1>", " ", markup)
    # Preserve document structure: block elements and table/list cells become line breaks, so a
    # coding-manual "valid entries" table survives as one line per code instead of a run-on blob.
    markup = re.sub(r"(?i)<br\s*/?>", "\n", markup)
    markup = re.sub(r"(?i)</(p|div|li|tr|h[1-6]|section|article)\s*>", "\n", markup)
    markup = re.sub(r"(?i)</(td|th)\s*>", " \t ", markup)
    text = re.sub(r"(?s)<[^>]+>", " ", markup)
    text = _html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
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
    if looks_bot_blocked(text):
        raise ValidationAppError(
            "That source is protected by an automated-access (bot) wall, so only a security "
            "check page was returned — not the document. Open the link in your browser, then "
            "upload the saved page (or its PDF) or paste the text here instead."
        )
    return text[:MAX_TEXT_CHARS]


async def fetch_url(url: str) -> tuple[bytes, str]:
    """GET a URL and return (body, content-type). Only http/https; admin-triggered."""
    if not url.lower().startswith(("http://", "https://")):
        raise ValidationAppError("URL must start with http:// or https://")
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=20.0) as client:
            resp = await client.get(url, headers={"User-Agent": "PGR-Platform/1.0 (advisory ingest)"})
            resp.raise_for_status()
            body, ctype = resp.content, resp.headers.get("content-type", "")
    except httpx.HTTPStatusError as exc:
        # A bot wall (Cloudflare et al.) commonly answers with 403/429/503 AND a challenge body.
        # Detect that and give the actionable "open it and upload" message instead of a bare code.
        status = exc.response.status_code
        challenge = looks_bot_blocked(exc.response.text) if exc.response is not None else False
        if challenge or status in (403, 429, 503):
            raise ValidationAppError(
                "That source blocks automated access (a bot wall answered instead of the document). "
                "Open the link in your browser, then upload the saved page or its PDF here — or paste "
                "the text into 'Paste directives'."
            ) from exc
        raise ValidationAppError(f"The source returned {status} for that URL") from exc
    except httpx.HTTPError as exc:
        raise ValidationAppError(f"Could not fetch that URL: {exc}") from exc

    if looks_bot_blocked(body.decode("utf-8", errors="replace")):
        raise ValidationAppError(
            "That source blocks automated access (a bot wall answered instead of the document). "
            "Open the link in your browser, then upload the saved page or its PDF here — or paste "
            "the text into 'Paste directives'."
        )
    return body, ctype
