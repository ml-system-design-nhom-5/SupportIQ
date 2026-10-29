import json
from datetime import datetime, timezone
from uuid import uuid4
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.contracts import AccessScope
from src.modules.retrieval.models import KnowledgeDocumentModel, KnowledgeDocumentVersionModel
from src.modules.retrieval.schemas import Evidence, RetrievalResult
from src.modules.orchestration.models import EvidenceSnapshotModel

async def retrieve_evidence(
    session: AsyncSession,
    redis: Any,
    run_id: str,
    sanitized_query: str,
    final_intent: str,
    scope: AccessScope,
    release: Any,
    now: datetime,
) -> RetrievalResult:
    cache_key = f"retrieval:{final_intent}:{sanitized_query.strip().lower()}"

    # 1. Check Redis Cache
    if redis is not None:
        try:
            cached_val = await redis.get(cache_key)
            if cached_val:
                items = json.loads(cached_val)
                cached_evidence = [Evidence(**item) for item in items]
                reason_codes: list[str] = []

                curr_now = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
                for ev in cached_evidence:
                    if ev.valid_to:
                        ev_to = ev.valid_to if ev.valid_to.tzinfo else ev.valid_to.replace(tzinfo=timezone.utc)
                        if ev_to <= curr_now:
                            reason_codes.append("expired_evidence")
                    if scope.role not in ev.allowed_roles:
                        reason_codes.append("unauthorized_evidence")

                if reason_codes:
                    return RetrievalResult(evidence=cached_evidence, reason_codes=list(set(reason_codes)))

                # Persist snapshot if valid cache hit
                for ev in cached_evidence:
                    snap = EvidenceSnapshotModel(
                        id=str(uuid4()),
                        run_id=str(run_id),
                        citation_id=ev.citation_id,
                        source_id=ev.source_id,
                        snippet=ev.snippet,
                        title=ev.title,
                        created_at=now,
                    )
                    session.add(snap)
                await session.commit()
                return RetrievalResult(evidence=cached_evidence, reason_codes=[])
        except Exception:
            pass

    # 2. Database query
    stmt = (
        select(KnowledgeDocumentVersionModel)
        .options(selectinload(KnowledgeDocumentVersionModel.document))
        .where(KnowledgeDocumentVersionModel.status == "approved")
    )
    res = await session.execute(stmt)
    versions = res.scalars().all()

    curr_now = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    query_words = set(sanitized_query.lower().replace("?", "").replace(".", "").split())
    intent_words = set(final_intent.lower().split("_"))

    matching_versions: list[KnowledgeDocumentVersionModel] = []
    for v in versions:
        # Check role permission
        if scope.role not in (v.allowed_roles or []):
            continue

        # Check date validity
        v_from = v.valid_from if v.valid_from.tzinfo else v.valid_from.replace(tzinfo=timezone.utc)
        v_to = v.valid_to if v.valid_to.tzinfo else v.valid_to.replace(tzinfo=timezone.utc)
        if not (v_from <= curr_now < v_to):
            continue

        # Check keyword / intent relevance
        text_to_match = f"{v.policy_key} {v.document.title if v.document else ''} {v.sanitized_excerpt}".lower()
        if any(w in text_to_match for w in query_words if len(w) > 3) or any(w in text_to_match for w in intent_words if len(w) > 3):
            matching_versions.append(v)

    # 3. Check for conflicting policy documents
    policy_groups: dict[str, set[str]] = {}
    for v in matching_versions:
        policy_groups.setdefault(v.policy_key, set()).add(v.normalized_rule_value)

    has_conflict = any(len(rules) > 1 for rules in policy_groups.values())
    if has_conflict:
        return RetrievalResult(evidence=[], reason_codes=["conflicting_evidence"])

    # 4. Build Evidence objects
    evidence_list: list[Evidence] = []
    for v in matching_versions[:3]:  # Top-3 ranking
        ev = Evidence(
            citation_id=f"cit_{v.document_id[:8]}_v{v.version}",
            source_id=v.document_id,
            snippet=v.sanitized_excerpt,
            title=v.document.title if v.document else None,
            policy_key=v.policy_key,
            normalized_rule_value=v.normalized_rule_value,
            valid_to=v.valid_to,
            allowed_roles=v.allowed_roles,
        )
        evidence_list.append(ev)

        snap = EvidenceSnapshotModel(
            id=str(uuid4()),
            run_id=str(run_id),
            citation_id=ev.citation_id,
            source_id=ev.source_id,
            snippet=ev.snippet,
            title=ev.title,
            created_at=now,
        )
        session.add(snap)

    if evidence_list:
        await session.commit()
        if redis is not None:
            try:
                cached_data = [ev.model_dump(mode="json") for ev in evidence_list]
                await redis.setex(cache_key, 60, json.dumps(cached_data))
            except Exception:
                pass

    return RetrievalResult(evidence=evidence_list, reason_codes=[])
