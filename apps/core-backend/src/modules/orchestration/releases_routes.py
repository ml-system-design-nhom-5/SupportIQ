from uuid import UUID
from typing import Literal
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from src.db import get_db_session
from src.contracts import AccessScope
from src.errors import AppError
from src.modules.auth.routes import get_current_user_scope
from src.modules.auth.service import authorize
from src.modules.orchestration.models import ReleaseManifestModel

router = APIRouter(prefix="/api/v1/releases", tags=["releases"])

class SetCurrentReleaseRequest(BaseModel):
    release_id: str
    expected_current_release_id: str | None = None
    offline_gate: Literal["passed", "failed"] = "passed"

@router.get("", status_code=status.HTTP_200_OK)
async def list_releases(
    scope: AccessScope = Depends(get_current_user_scope),
    db: AsyncSession = Depends(get_db_session),
):
    authorize(scope, ["admin", "staff", "manager", "lead", "agent"])
    stmt = select(ReleaseManifestModel).order_by(ReleaseManifestModel.created_at.desc())
    res = await db.execute(stmt)
    releases = res.scalars().all()
    return {
        "data": [
            {
                "id": str(r.id),
                "release_tag": r.release_tag,
                "intent_model_name": r.intent_model_name,
                "intent_model_version": r.intent_model_version,
                "embedding_model_name": r.embedding_model_name,
                "embedding_model_version": r.embedding_model_version,
                "llm_model_name": r.llm_model_name,
                "prompt_template_hash": r.prompt_template_hash,
                "active": r.active,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in releases
        ]
    }

@router.put("/current", status_code=status.HTTP_200_OK)
async def set_current_release(
    payload: SetCurrentReleaseRequest,
    scope: AccessScope = Depends(get_current_user_scope),
    db: AsyncSession = Depends(get_db_session),
):
    authorize(scope, ["admin"])

    if payload.offline_gate != "passed":
        raise AppError(
            status=400,
            code="invalid_offline_gate",
            title="Invalid Offline Gate",
            detail="Offline validation gate must be 'passed' before activating a release manifest.",
        )

    stmt = select(ReleaseManifestModel).where(ReleaseManifestModel.active == True)
    res = await db.execute(stmt)
    current_active = res.scalars().first()

    current_active_id = str(current_active.id) if current_active else None

    # Atomic CAS verification
    if payload.expected_current_release_id is not None:
        if current_active_id != str(payload.expected_current_release_id):
            raise AppError(
                status=409,
                code="release_manifest_conflict",
                title="Release Manifest Conflict",
                detail=f"Current release ID ({current_active_id}) does not match expected_current_release_id ({payload.expected_current_release_id}).",
            )

    target_stmt = select(ReleaseManifestModel).where(ReleaseManifestModel.id == payload.release_id)
    target_res = await db.execute(target_stmt)
    target_release = target_res.scalars().first()

    if not target_release:
        raise AppError(
            status=404,
            code="release_not_found",
            title="Release Not Found",
            detail=f"Release manifest with ID {payload.release_id} not found.",
        )

    await db.execute(
        update(ReleaseManifestModel).where(ReleaseManifestModel.active == True).values(active=False)
    )
    target_release.active = True
    await db.commit()
    await db.refresh(target_release)

    return {
        "data": {
            "id": str(target_release.id),
            "release_tag": target_release.release_tag,
            "intent_model_name": target_release.intent_model_name,
            "intent_model_version": target_release.intent_model_version,
            "embedding_model_name": target_release.embedding_model_name,
            "embedding_model_version": target_release.embedding_model_version,
            "llm_model_name": target_release.llm_model_name,
            "prompt_template_hash": target_release.prompt_template_hash,
            "active": target_release.active,
            "created_at": target_release.created_at.isoformat() if target_release.created_at else None,
        }
    }
