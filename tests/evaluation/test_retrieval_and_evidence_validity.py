from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4
import pytest

from src.contracts import AccessScope
from src.modules.retrieval.service import retrieve_evidence
from src.modules.retrieval.models import KnowledgeDocumentModel, KnowledgeDocumentVersionModel
from src.modules.orchestration.models import PipelineRunModel, ReleaseManifestModel

class MockRedisClient:
    def __init__(self):
        self._store: dict[str, tuple[str, datetime | None]] = {}

    async def get(self, key: str) -> str | None:
        item = self._store.get(key)
        if not item:
            return None
        val, exp = item
        if exp is not None and datetime.now(timezone.utc) > exp:
            del self._store[key]
            return None
        return val

    async def setex(self, key: str, time: int, value: str):
        exp = datetime.now(timezone.utc) + timedelta(seconds=time)
        self._store[key] = (value, exp)

    async def delete(self, key: str):
        self._store.pop(key, None)

@pytest.fixture
def redis_client():
    return MockRedisClient()

@pytest.fixture
def agent_scope():
    return AccessScope(
        actor_id=uuid4(),
        session_id=uuid4(),
        role="agent",
        role_version=1,
    )

@pytest.fixture
async def active_release(db_session):
    rel = ReleaseManifestModel(
        id=str(uuid4()),
        release_tag=f"rel-{uuid4()}",
        intent_model_name="bitext-intent-classifier",
        intent_model_version="v1.0.0",
        embedding_model_name="text-embedding-3-small",
        embedding_model_version="v1.0.0",
        llm_model_name="gpt-4o-mini",
        prompt_template_hash="a"*64,
        active=True,
    )
    db_session.add(rel)
    await db_session.commit()
    return rel

@pytest.fixture
async def seeded_kb_with_short_expiry(db_session):
    t0 = datetime(2026, 10, 29, 9, 0, 0, tzinfo=timezone.utc)
    doc_id = str(uuid4())
    doc = KnowledgeDocumentModel(
        id=doc_id,
        title="Standard Return Policy",
        category="policy",
    )
    db_session.add(doc)

    doc_ver = KnowledgeDocumentVersionModel(
        id=str(uuid4()),
        document_id=doc_id,
        version=1,
        policy_key="return_window",
        normalized_rule_value="30_days",
        valid_from=t0 - timedelta(days=1),
        valid_to=t0 + timedelta(seconds=20),
        status="approved",
        allowed_roles=["agent", "staff", "manager", "admin"],
        content_hash="hash_return_window_30d",
        sanitized_excerpt="Customers may return products within 30 days of receipt in original packaging.",
    )
    db_session.add(doc_ver)

    run1 = PipelineRunModel(
        id=str(uuid4()),
        ticket_id=str(uuid4()),
        customer_id=str(uuid4()),
        status="queued",
        stage="pipeline",
        deadline_at=t0 + timedelta(minutes=5),
    )
    run2 = PipelineRunModel(
        id=str(uuid4()),
        ticket_id=str(uuid4()),
        customer_id=str(uuid4()),
        status="queued",
        stage="pipeline",
        deadline_at=t0 + timedelta(minutes=5),
    )
    db_session.add(run1)
    db_session.add(run2)
    await db_session.commit()

    return SimpleNamespace(run1_id=run1.id, run2_id=run2.id, doc_id=doc_id)

@pytest.fixture
async def seeded_conflicting_kb(db_session):
    t0 = datetime(2026, 10, 29, 9, 0, 0, tzinfo=timezone.utc)
    doc1_id = str(uuid4())
    doc2_id = str(uuid4())

    doc1 = KnowledgeDocumentModel(id=doc1_id, title="Refund Policy Normal", category="policy")
    doc2 = KnowledgeDocumentModel(id=doc2_id, title="Refund Policy Promo", category="policy")
    db_session.add(doc1)
    db_session.add(doc2)

    doc_ver1 = KnowledgeDocumentVersionModel(
        id=str(uuid4()),
        document_id=doc1_id,
        version=1,
        policy_key="refund_window",
        normalized_rule_value="14_days",
        valid_from=t0 - timedelta(days=5),
        valid_to=t0 + timedelta(days=30),
        status="approved",
        allowed_roles=["agent", "staff", "manager", "admin"],
        content_hash="hash_refund_14d",
        sanitized_excerpt="Refund requests are accepted within 14 days of purchase.",
    )
    doc_ver2 = KnowledgeDocumentVersionModel(
        id=str(uuid4()),
        document_id=doc2_id,
        version=1,
        policy_key="refund_window",
        normalized_rule_value="30_days",
        valid_from=t0 - timedelta(days=5),
        valid_to=t0 + timedelta(days=30),
        status="approved",
        allowed_roles=["agent", "staff", "manager", "admin"],
        content_hash="hash_refund_30d",
        sanitized_excerpt="Special promotion refund requests accepted within 30 days.",
    )
    db_session.add(doc_ver1)
    db_session.add(doc_ver2)

    run = PipelineRunModel(
        id=str(uuid4()),
        ticket_id=str(uuid4()),
        customer_id=str(uuid4()),
        status="queued",
        stage="pipeline",
        deadline_at=t0 + timedelta(minutes=5),
    )
    db_session.add(run)
    await db_session.commit()

    return SimpleNamespace(run_id=run.id)

@pytest.mark.asyncio
async def test_retrieval_cache_hit_rechecks_document_validity_and_scope(
    db_session, redis_client, seeded_kb_with_short_expiry, agent_scope, active_release
):
    t0 = datetime(2026, 10, 29, 9, 0, 0, tzinfo=timezone.utc)
    # First call populates 60s Redis cache while document is valid (valid_to = t0 + 20s)
    res1 = await retrieve_evidence(
        db_session, redis_client, run_id=seeded_kb_with_short_expiry.run1_id,
        sanitized_query="What is the return window?", final_intent="return_policy",
        scope=agent_scope, release=active_release, now=t0
    )
    assert res1.reason_codes == []
    assert len(res1.evidence) >= 1

    # Second call 30s later hits the 60s Redis cache, but document valid_to has now passed!
    t1 = t0 + timedelta(seconds=30)
    res2 = await retrieve_evidence(
        db_session, redis_client, run_id=seeded_kb_with_short_expiry.run2_id,
        sanitized_query="What is the return window?", final_intent="return_policy",
        scope=agent_scope, release=active_release, now=t1
    )
    assert "expired_evidence" in res2.reason_codes

@pytest.mark.asyncio
async def test_conflicting_policy_documents_flagged(
    db_session, redis_client, seeded_conflicting_kb, agent_scope, active_release
):
    now = datetime(2026, 10, 29, 9, 0, 0, tzinfo=timezone.utc)
    res = await retrieve_evidence(
        db_session, redis_client, run_id=seeded_conflicting_kb.run_id,
        sanitized_query="How many days for refund?", final_intent="refund_policy",
        scope=agent_scope, release=active_release, now=now
    )
    assert "conflicting_evidence" in res.reason_codes
