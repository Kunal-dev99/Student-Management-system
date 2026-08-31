"""F4 — Award pipeline: classification workflow and certificate PDF.

Classification is a small state machine: draft → proposed → confirmed → published.
Only a published award can graduate. Publishing renders the certificate PDF into the object
store and attaches it to the award via ``certificate_document_id``.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from io import BytesIO
from typing import Iterable

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError, WorkflowError
from app.core.storage import get_object_store
from app.modules.completion.models import Award, Completion
from app.modules.documents.models import Document
from app.modules.person.models import Person
from app.modules.student_record.models import Student


CLASSIFICATIONS = {
    "PhD": "Doctor of Philosophy",
    "PhD-with-corrections": "Doctor of Philosophy — awarded following corrections",
    "PhD-with-major-corrections": "Doctor of Philosophy — awarded following major corrections",
    "MPhil": "Master of Philosophy",
    "MRes": "Master of Research",
}


class ClassificationService:
    """Chair proposes → exam board confirms (a different user) → Registry publishes."""

    ALLOWED_STATES = {"draft", "proposed", "confirmed", "published"}

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _award_for(self, student_id: uuid.UUID, *, create_if_missing: bool = False) -> Award:
        row = (await self.session.execute(
            select(Award).where(Award.student_id == student_id)
        )).scalar_one_or_none()
        if row is None:
            if not create_if_missing:
                raise NotFoundError("No draft award for this student — propose a classification first")
            row = Award(student_id=student_id, title="Doctor of Philosophy",
                        award_type="PhD", classification_state="draft")
            self.session.add(row)
            await self.session.flush()
        return row

    async def propose(
        self, student_id: uuid.UUID, *, classification: str,
        proposed_by_user_id: uuid.UUID | None,
    ) -> Award:
        if classification not in CLASSIFICATIONS:
            raise WorkflowError(
                f"Unknown classification '{classification}'. Allowed: {', '.join(sorted(CLASSIFICATIONS))}"
            )
        award = await self._award_for(student_id, create_if_missing=True)
        if award.classification_state == "published":
            raise ConflictError("Award is already published — cannot re-propose")
        award.classification = classification
        award.classification_state = "proposed"
        award.proposed_by_user_id = proposed_by_user_id
        await self.session.commit()
        await self.session.refresh(award)
        return award

    async def confirm(
        self, student_id: uuid.UUID, *, confirmed_by_user_id: uuid.UUID | None,
    ) -> Award:
        award = await self._award_for(student_id)
        if award.classification_state != "proposed":
            raise WorkflowError(f"Only a proposed classification can be confirmed (currently {award.classification_state})")
        # Approver separation — the confirmer must not be the proposer.
        if (award.proposed_by_user_id is not None
                and confirmed_by_user_id is not None
                and award.proposed_by_user_id == confirmed_by_user_id):
            raise WorkflowError("Approver separation: the confirmer must differ from the proposer")
        award.classification_state = "confirmed"
        award.confirmed_by_user_id = confirmed_by_user_id
        await self.session.commit()
        await self.session.refresh(award)
        return award

    async def publish(self, student_id: uuid.UUID) -> tuple[Award, Document]:
        award = await self._award_for(student_id)
        if award.classification_state != "confirmed":
            raise WorkflowError(f"Only a confirmed classification can be published (currently {award.classification_state})")

        # Render the certificate PDF and store it as a Document.
        student = (await self.session.execute(
            select(Student).where(Student.id == award.student_id)
        )).scalar_one()
        person = (await self.session.execute(
            select(Person).where(Person.id == student.person_id)
        )).scalar_one()

        pdf_bytes = _render_certificate(
            given_name=person.given_name,
            family_name=person.family_name,
            classification=award.classification or award.award_type or "PhD",
            title_line=CLASSIFICATIONS.get(award.classification or "", award.title),
        )

        store = get_object_store()
        key, digest, size = store.save(pdf_bytes, suffix=".pdf")
        doc = Document(
            owner_type="award", owner_id=award.id,
            doc_type="certificate",
            filename=f"certificate-{student.student_ref}.pdf",
            content_type="application/pdf",
            size_bytes=size, checksum_sha256=digest, storage_key=key,
        )
        self.session.add(doc)
        await self.session.flush()

        award.classification_state = "published"
        award.published_at = datetime.now(timezone.utc)
        award.certificate_document_id = doc.id
        await self.session.commit()
        await self.session.refresh(award)
        return award, doc


def _render_certificate(*, given_name: str, family_name: str, classification: str, title_line: str) -> bytes:
    """Simple, brandable A4 certificate. Kept minimal; institution will style later."""
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=2.5*cm, rightMargin=2.5*cm,
                            topMargin=3*cm, bottomMargin=3*cm)
    NAVY = colors.HexColor("#15171A")
    GOLD = colors.HexColor("#B8860B")
    from reportlab.lib.enums import TA_CENTER
    H = ParagraphStyle("H", fontName="Helvetica-Bold", fontSize=36, leading=40,
                       alignment=TA_CENTER, textColor=NAVY)
    S = ParagraphStyle("S", fontName="Helvetica", fontSize=16, leading=22,
                       alignment=TA_CENTER, textColor=NAVY)
    G = ParagraphStyle("G", fontName="Helvetica-Bold", fontSize=22, leading=28,
                       alignment=TA_CENTER, textColor=GOLD)
    D = ParagraphStyle("D", fontName="Helvetica-Oblique", fontSize=11, leading=14,
                       alignment=TA_CENTER, textColor=NAVY)
    story = []
    story.append(Spacer(1, 3*cm))
    story.append(Paragraph("PGR Institution", H))
    story.append(Spacer(1, 1.5*cm))
    story.append(Paragraph("This is to certify that", S))
    story.append(Spacer(1, 0.8*cm))
    story.append(Paragraph(f"<b>{given_name} {family_name}</b>", G))
    story.append(Spacer(1, 0.8*cm))
    story.append(Paragraph("has satisfied the requirements for the degree of", S))
    story.append(Spacer(1, 0.6*cm))
    story.append(Paragraph(title_line, G))
    story.append(Spacer(1, 2*cm))
    story.append(Paragraph(f"Awarded on {datetime.now(timezone.utc).strftime('%d %B %Y')}", D))
    doc.build(story)
    return buf.getvalue()
