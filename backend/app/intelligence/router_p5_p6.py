"""AI-P5 (Institutional Memory) + P6 (Policy Compiler) endpoints."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_permission
from app.core.principal import Principal
from app.db.session import get_read_session, get_session
from app.intelligence.memory import InstitutionalMemoryService
from app.intelligence.models_p6 import PolicyProposal, PolicyVersion
from app.intelligence.policy import PolicyCompiler

router_p5_p6 = APIRouter(prefix="/intelligence", tags=["intelligence"])


# ---- P5 — Institutional Memory ----------------------------------------------

class SimilarCasesIn(BaseModel):
    case_class: str
    subject: dict[str, Any]
    limit: int = 8


@router_p5_p6.post("/cases/similar", summary="Structural precedent retrieval (Institutional Memory)")
async def similar_cases(
    body: SimilarCasesIn,
    session: AsyncSession = Depends(get_read_session),
    principal: Principal = Depends(require_permission("student.read")),
) -> dict[str, Any]:
    return await InstitutionalMemoryService(session, principal).similar_cases(
        subject=body.subject, case_class=body.case_class, limit=body.limit,
    )


# ---- P6 — Policy Compiler ---------------------------------------------------

class RegisterPolicyIn(BaseModel):
    policy_ref: str
    version_label: str
    document_version_id: uuid.UUID | None = None


class ProposeIn(BaseModel):
    policy_version_id: uuid.UUID
    policy_text: str
    enable_llm: bool = False


class ReviewIn(BaseModel):
    disposition: str


@router_p5_p6.post("/policy/versions", status_code=201,
                    summary="Register an approved policy document version")
async def register_policy_version(
    body: RegisterPolicyIn,
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(require_permission("admin.configure")),
) -> dict[str, Any]:
    row = PolicyVersion(
        policy_ref=body.policy_ref,
        version_label=body.version_label,
        approved_at=datetime.now(timezone.utc),
        document_version_id=body.document_version_id,
    )
    session.add(row)
    await session.commit()
    return {"id": str(row.id), "policy_ref": row.policy_ref,
             "version_label": row.version_label}


@router_p5_p6.post("/policy/proposals", status_code=201,
                    summary="Compile allow-listed configuration proposals from a policy version")
async def create_policy_proposal(
    body: ProposeIn,
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(require_permission("admin.configure")),
) -> dict[str, Any]:
    proposal = await PolicyCompiler(session).propose(
        body.policy_version_id, body.policy_text, enable_llm=body.enable_llm,
    )
    await session.commit()
    return {
        "id": str(proposal.id),
        "source_version_id": str(proposal.source_version_id),
        "status": proposal.status,
        "rule_candidates": proposal.rule_candidates,
        "config_candidates": proposal.config_candidates,
        "simulation_result": proposal.simulation_result,
    }


@router_p5_p6.get("/policy/proposals/{proposal_id}", summary="Read a policy proposal")
async def get_policy_proposal(
    proposal_id: uuid.UUID,
    session: AsyncSession = Depends(get_read_session),
    _: Principal = Depends(require_permission("admin.configure")),
) -> dict[str, Any]:
    row = await session.get(PolicyProposal, proposal_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Proposal not found")
    return {
        "id": str(row.id),
        "status": row.status,
        "rule_candidates": row.rule_candidates,
        "config_candidates": row.config_candidates,
        "simulation_result": row.simulation_result,
        "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
        "published_at": row.published_at.isoformat() if row.published_at else None,
    }


@router_p5_p6.post("/policy/proposals/{proposal_id}/review",
                    summary="Review or publish a proposal (governed transition)")
async def review_policy_proposal(
    proposal_id: uuid.UUID,
    body: ReviewIn,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("admin.configure")),
) -> dict[str, Any]:
    row = await PolicyCompiler(session).review(
        proposal_id, disposition=body.disposition,
        reviewed_by_user_id=principal.user_id,
    )
    await session.commit()
    return {"id": str(row.id), "status": row.status,
             "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None}
