"""Statutory advisory ingestion service (ICR G5).

ingest → recommend → Registry accepts. ``ingest`` parses a pasted/uploaded advisory into a
deterministic diff against the current effective pack and stores it for review. ``accept``
materialises the proposed pack as a new active :class:`StatutorySpecVersion` (superseding any
prior active one for that code+year); from then on the resolver serves it to every consumer.
Nothing here scrapes anything — a Registry owner (``reports.signoff``) is always the one who
accepts, exactly as they sign off a return.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, ValidationAppError
from app.modules.exports.advisory_parser import parse_advisory
from app.modules.exports.constants import AdvisoryStatus, SpecVersionStatus
from app.modules.exports.models import StatutoryAdvisory, StatutorySpecVersion
from app.modules.exports.spec_resolver import resolve_fields, resolve_rules
from app.modules.exports.specs import spec_pack


class _DirectiveExtraction(BaseModel):
    """Shape the AI ``read`` layer fills when an advisory is free prose, not directives."""
    directives: list[str] = []


def _now() -> datetime:
    return datetime.now(timezone.utc)


class AdvisoryService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # --- ingest -----------------------------------------------------------

    async def ingest(
        self,
        *,
        pack_code: str,
        academic_year: str | None,
        title: str,
        raw_text: str,
        source: str = "paste",
        created_by: uuid.UUID | None = None,
    ) -> StatutoryAdvisory:
        base_fields = await resolve_fields(self.session, pack_code)
        base_rules = await resolve_rules(self.session, pack_code)
        if not base_fields:
            raise ValidationAppError(f"No spec pack is registered for '{pack_code}'")

        parsed = parse_advisory(raw_text, base_fields, base_rules)
        parse_source = "directive"

        # Free-prose advisory (no directives recognised)? Let the AI read-layer try to extract
        # directives, then re-run the SAME deterministic parser. Model off → empty → we keep the
        # deterministic (empty) result and a warning; acceptance never depends on the model.
        if parsed.directive_count == 0:
            extracted = await self._ai_extract_directives(raw_text)
            if extracted:
                reparsed = parse_advisory(extracted, base_fields, base_rules)
                if reparsed.directive_count > 0:
                    parsed = reparsed
                    parse_source = "model"

        year = academic_year or parsed.academic_year
        if not year:
            raise ValidationAppError(
                "Advisory must state a target academic year (a YEAR: directive or the academicYear field)"
            )

        base_version = await self._current_version(pack_code, year)

        advisory = StatutoryAdvisory(
            pack_code=pack_code,
            academic_year=year,
            title=title.strip() or f"{pack_code} advisory {year}",
            raw_text=raw_text,
            source=source,
            status=AdvisoryStatus.ingested,
            base_version=base_version,
            parse_source=parse_source,
            changes=parsed.changes,
            proposed_fields=parsed.proposed_fields,
            proposed_rules=parsed.proposed_rules,
            created_by=created_by,
        )
        self.session.add(advisory)
        await self.session.commit()
        await self.session.refresh(advisory)
        # Surface parse warnings to the caller without persisting them (they're advisory only) —
        # a plain, non-mapped instance attribute the router reads back.
        advisory.parse_warnings = parsed.warnings  # type: ignore[attr-defined]
        return advisory

    async def _ai_extract_directives(self, text: str) -> str:
        """Best-effort: turn prose into directive lines via the AI read shape. '' on any failure."""
        try:
            from app.ai import read  # imported lazily so the module loads with AI off
        except Exception:
            return ""
        try:
            result = await read(
                text=text,
                schema=_DirectiveExtraction,
                hint=(
                    "Extract statutory-return change directives, one per line, using exactly this "
                    "grammar: 'ADD FIELD NAME \"desc\" coding=[a,b]', 'REMOVE FIELD NAME', "
                    "'CODING NAME = [a,b]', 'DESC NAME \"desc\"', "
                    "'RULE order F1 F2 \"message\"'. Copy field codes verbatim."
                ),
            )
        except Exception:
            return ""
        directives = (result.fields or {}).get("directives") or []
        return "\n".join(str(d) for d in directives if str(d).strip())

    async def _current_version(self, pack_code: str, year: str) -> int:
        """Highest known version for this code+year: latest active DB row, else baseline pack, else 1."""
        db_version = (
            await self.session.execute(
                select(StatutorySpecVersion.version)
                .where(
                    StatutorySpecVersion.pack_code == pack_code,
                    StatutorySpecVersion.academic_year == year,
                )
                .order_by(StatutorySpecVersion.version.desc())
            )
        ).scalars().first()
        if db_version:
            return db_version
        baseline = spec_pack(f"{pack_code}:{year}")
        return baseline["version"] if baseline else 1

    # --- read -------------------------------------------------------------

    async def get(self, advisory_id: uuid.UUID) -> StatutoryAdvisory:
        advisory = await self.session.get(StatutoryAdvisory, advisory_id)
        if advisory is None:
            raise NotFoundError("Advisory not found")
        return advisory

    async def list_recent(self, *, limit: int = 50) -> list[StatutoryAdvisory]:
        return list(
            (
                await self.session.execute(
                    select(StatutoryAdvisory)
                    .order_by(StatutoryAdvisory.created_at.desc())
                    .limit(limit)
                )
            ).scalars().all()
        )

    # --- decide -----------------------------------------------------------

    async def accept(
        self, advisory_id: uuid.UUID, *, user_id: uuid.UUID | None, note: str | None = None
    ) -> StatutorySpecVersion:
        advisory = await self.get(advisory_id)
        if advisory.status is not AdvisoryStatus.ingested:
            raise ValidationAppError(f"Advisory is already {advisory.status.value}")
        if not advisory.changes:
            raise ValidationAppError("Advisory proposes no changes to accept")

        # Supersede any active version for the same code+year, then write the new active one.
        actives = (
            await self.session.execute(
                select(StatutorySpecVersion).where(
                    StatutorySpecVersion.pack_code == advisory.pack_code,
                    StatutorySpecVersion.academic_year == advisory.academic_year,
                    StatutorySpecVersion.status == SpecVersionStatus.active,
                )
            )
        ).scalars().all()
        for prior in actives:
            prior.status = SpecVersionStatus.superseded

        new_version = advisory.base_version + 1
        baseline = spec_pack(f"{advisory.pack_code}:{advisory.academic_year}")
        name = baseline["name"] if baseline else advisory.pack_code

        version = StatutorySpecVersion(
            pack_code=advisory.pack_code,
            academic_year=advisory.academic_year,
            version=new_version,
            name=name,
            status=SpecVersionStatus.active,
            fields=advisory.proposed_fields,
            rules=advisory.proposed_rules,
            source_advisory_id=advisory.id,
            accepted_by=user_id,
        )
        self.session.add(version)

        advisory.status = AdvisoryStatus.accepted
        advisory.decided_by = user_id
        advisory.decided_at = _now()
        advisory.decision_note = note
        await self.session.commit()
        await self.session.refresh(version)
        return version

    async def reject(
        self, advisory_id: uuid.UUID, *, user_id: uuid.UUID | None, note: str | None = None
    ) -> StatutoryAdvisory:
        advisory = await self.get(advisory_id)
        if advisory.status is not AdvisoryStatus.ingested:
            raise ValidationAppError(f"Advisory is already {advisory.status.value}")
        advisory.status = AdvisoryStatus.rejected
        advisory.decided_by = user_id
        advisory.decided_at = _now()
        advisory.decision_note = note
        await self.session.commit()
        await self.session.refresh(advisory)
        return advisory
