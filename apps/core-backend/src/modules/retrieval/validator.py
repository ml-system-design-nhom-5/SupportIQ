from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.modules.orchestration.models import EvidenceSnapshotModel
from src.modules.retrieval.models import KnowledgeDocumentVersionModel

async def verify_evidence_still_valid(
    session: AsyncSession,
    run_id: str,
    now: datetime,
) -> bool:
    curr_now = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    stmt = select(EvidenceSnapshotModel).where(EvidenceSnapshotModel.run_id == str(run_id))
    res = await session.execute(stmt)
    snapshots = res.scalars().all()
    if not snapshots:
        return True

    for snap in snapshots:
        v_stmt = (
            select(KnowledgeDocumentVersionModel)
            .where(KnowledgeDocumentVersionModel.document_id == snap.source_id)
            .order_by(KnowledgeDocumentVersionModel.version.desc())
        )
        v_res = await session.execute(v_stmt)
        version = v_res.scalars().first()
        if not version or version.status != "approved":
            return False
        v_to = version.valid_to if version.valid_to.tzinfo else version.valid_to.replace(tzinfo=timezone.utc)
        if v_to <= curr_now:
            return False

    return True
