"""Document intelligence — versioned extraction + Research Change Radar.

Phase 4 ships the metadata pipeline and a deterministic comparator. LLM-driven
semantic diff sits behind the same schema; when the LLM is off, only findings the
deterministic diff surfaces are emitted, and each finding always carries both source
spans + a review disposition slot.
"""
from __future__ import annotations

import hashlib
import re
import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.intelligence.ai_bridge import intelligence_read
from app.intelligence.models_p4 import ChangeFinding, DocumentChunk, DocumentVersion


class _SemanticDiffFinding(BaseModel):
    """Schema the LLM extracts one finding into on a shared changed section."""
    change_type: str = Field(description="One of: scope_changed, method_changed, "
                                          "sample_size_changed, ethical_shift, other")
    severity: str = Field(description="One of: notice, urgent")
    summary: str = Field(description="One sentence, ≤ 28 words, describing the change.")


EXTRACTOR_VERSION = "det.v1"

_HEADING_RE = re.compile(r"^\s*(?:(?:\d+(?:\.\d+)*[.)]?)\s+)?([A-Z][A-Za-z0-9 ,\-]{3,80})\s*$",
                          re.MULTILINE)


def _hash(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


class DocumentPipeline:
    """Register a document version + extract structured chunks (deterministic)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def register_version(
        self, document_ref: str, object_key: str, content: str,
        student_id: uuid.UUID | None = None, mime_type: str | None = None,
        uploaded_by_user_id: uuid.UUID | None = None,
    ) -> DocumentVersion:
        version = DocumentVersion(
            document_ref=document_ref,
            student_id=student_id,
            object_key=object_key,
            content_hash=_hash(content),
            mime_type=mime_type,
            uploaded_at=datetime.now(timezone.utc),
            uploaded_by_user_id=uploaded_by_user_id,
            extraction_status="pending",
        )
        self.session.add(version)
        await self.session.flush()
        # Extract synchronously here; worker version arrives when we wire the queue.
        await self._extract(version, content)
        return version

    async def _extract(self, version: DocumentVersion, content: str) -> None:
        # Section headings become chunk boundaries; falls back to paragraphs.
        boundaries = [m.start() for m in _HEADING_RE.finditer(content)] + [len(content)]
        if len(boundaries) <= 1:
            paragraphs = [p for p in re.split(r"\n{2,}", content) if p.strip()]
            offset = 0
            for para in paragraphs:
                chunk = para.strip()[:7000]
                self.session.add(DocumentChunk(
                    version_id=version.id,
                    page_number=None,
                    section_heading=None,
                    char_start=offset,
                    char_end=offset + len(chunk),
                    span_hash=_hash(chunk),
                    text=chunk,
                ))
                offset += len(para) + 2
        else:
            for i, start in enumerate(boundaries[:-1]):
                end = boundaries[i + 1]
                span = content[start:end].strip()
                if not span:
                    continue
                heading_match = _HEADING_RE.match(content[start:end])
                heading = heading_match.group(1).strip() if heading_match else None
                body = span[:8000]
                self.session.add(DocumentChunk(
                    version_id=version.id,
                    section_heading=heading,
                    char_start=start,
                    char_end=end,
                    span_hash=_hash(body),
                    text=body,
                ))
        version.extraction_status = "extracted"
        version.extractor_version = EXTRACTOR_VERSION
        await self.session.flush()


class ChangeRadar:
    """Compare two document versions and produce ChangeFindings."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def compare(self, version_a_id: uuid.UUID,
                       version_b_id: uuid.UUID, *,
                       include_semantic: bool = False) -> list[ChangeFinding]:
        va = await self.session.get(DocumentVersion, version_a_id)
        vb = await self.session.get(DocumentVersion, version_b_id)
        if va is None or vb is None:
            raise NotFoundError("One of the document versions was not found.")

        chunks_a = (await self.session.execute(
            select(DocumentChunk).where(DocumentChunk.version_id == va.id)
        )).scalars().all()
        chunks_b = (await self.session.execute(
            select(DocumentChunk).where(DocumentChunk.version_id == vb.id)
        )).scalars().all()

        heads_a = {(c.section_heading or "").lower(): c for c in chunks_a}
        heads_b = {(c.section_heading or "").lower(): c for c in chunks_b}

        findings: list[ChangeFinding] = []

        # Sections added or removed.
        for h in heads_b.keys() - heads_a.keys():
            if not h:
                continue
            findings.append(ChangeFinding(
                version_a_id=va.id, version_b_id=vb.id,
                change_type="scope_changed",
                severity_for_review="notice",
                source_b_ref={"section_heading": h, "chunk_id": str(heads_b[h].id)},
                summary=f"Section '{h}' added in the newer version.",
            ))
        for h in heads_a.keys() - heads_b.keys():
            if not h:
                continue
            findings.append(ChangeFinding(
                version_a_id=va.id, version_b_id=vb.id,
                change_type="scope_changed",
                severity_for_review="notice",
                source_a_ref={"section_heading": h, "chunk_id": str(heads_a[h].id)},
                summary=f"Section '{h}' removed in the newer version.",
            ))

        # Method / population heuristic detection on shared sections.
        method_pat = re.compile(r"\b(qualitative|quantitative|mixed methods?)\b", re.IGNORECASE)
        pop_pat = re.compile(r"\b(\d{1,4})\s+(participants?|subjects?|students?)\b", re.IGNORECASE)
        for h in heads_a.keys() & heads_b.keys():
            if not h:
                continue
            ca, cb = heads_a[h], heads_b[h]
            if ca.span_hash == cb.span_hash:
                continue  # section unchanged
            a_method = {m.group(1).lower() for m in method_pat.finditer(ca.text)}
            b_method = {m.group(1).lower() for m in method_pat.finditer(cb.text)}
            if a_method != b_method and (a_method or b_method):
                findings.append(ChangeFinding(
                    version_a_id=va.id, version_b_id=vb.id,
                    change_type="method_changed",
                    severity_for_review="urgent",
                    source_a_ref={"section_heading": h, "chunk_id": str(ca.id),
                                   "detected": sorted(a_method)},
                    source_b_ref={"section_heading": h, "chunk_id": str(cb.id),
                                   "detected": sorted(b_method)},
                    summary=(f"Methodology changed in section '{h}': "
                             f"{sorted(a_method) or 'unspecified'} → "
                             f"{sorted(b_method) or 'unspecified'}."),
                ))
            a_n = [int(m.group(1)) for m in pop_pat.finditer(ca.text)]
            b_n = [int(m.group(1)) for m in pop_pat.finditer(cb.text)]
            if a_n and b_n and max(a_n) != max(b_n):
                findings.append(ChangeFinding(
                    version_a_id=va.id, version_b_id=vb.id,
                    change_type="sample_size_changed",
                    severity_for_review="notice",
                    source_a_ref={"section_heading": h, "chunk_id": str(ca.id),
                                   "detected": max(a_n)},
                    source_b_ref={"section_heading": h, "chunk_id": str(cb.id),
                                   "detected": max(b_n)},
                    summary=(f"Sample size changed in section '{h}': {max(a_n)} → {max(b_n)}."),
                ))

        # Optional LLM-augmented semantic diff on sections the deterministic layer
        # touched but couldn't fully classify (unchanged sections are skipped). Deterministic
        # findings above are authoritative; LLM findings are additive and never overwrite.
        if include_semantic:
            det_covered_headings = {(f.source_b_ref or f.source_a_ref or {}).get("section_heading")
                                      for f in findings}
            for h in heads_a.keys() & heads_b.keys():
                if not h or h in det_covered_headings:
                    continue
                ca, cb = heads_a[h], heads_b[h]
                if ca.span_hash == cb.span_hash:
                    continue
                combined = (f"Section: {h}\n\n"
                            f"OLD:\n{ca.text[:2000]}\n\n"
                            f"NEW:\n{cb.text[:2000]}")
                result = await intelligence_read(
                    feature="change_radar",
                    text=combined,
                    schema=_SemanticDiffFinding,
                    hint="Compare the OLD and NEW passages and describe any material change.",
                )
                if result.needs_manual:
                    continue
                ct = result.fields.get("change_type") or "other"
                sev = result.fields.get("severity") or "notice"
                summary = result.fields.get("summary")
                if not summary:
                    continue
                findings.append(ChangeFinding(
                    version_a_id=va.id, version_b_id=vb.id,
                    change_type=ct if ct in ("scope_changed", "method_changed",
                                              "sample_size_changed", "ethical_shift",
                                              "other") else "other",
                    severity_for_review=sev if sev in ("notice", "urgent") else "notice",
                    source_a_ref={"section_heading": h, "chunk_id": str(ca.id),
                                   "engine": "llm"},
                    source_b_ref={"section_heading": h, "chunk_id": str(cb.id),
                                   "engine": "llm"},
                    summary=summary,
                ))

        for f in findings:
            self.session.add(f)
        await self.session.flush()
        return findings
