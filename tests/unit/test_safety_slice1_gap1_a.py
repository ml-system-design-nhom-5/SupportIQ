"""TDD tests for System Safety Slice 1 (Gap 1a: RetrievalAdapter + Gap 1b: safety capability/channel scope)."""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import httpx
import numpy as np
import pytest

from apps.ai_service.engine import Engine
from apps.backend.tickets.jobs import validate_analysis
from apps.core_backend.intent.client import IntentClient
from apps.core_backend.intent.schemas import RoutingContext
from apps.core_backend.orchestration.pipeline_runner import PipelineRunner
from apps.core_backend.orchestration.store import PersistentStore
from apps.core_backend.retrieval.adapter import RetrievalAdapter
from apps.core_backend.safety import evaluate_evidence_scope, policy_scope_requires_review


REPO_ROOT = Path(__file__).resolve().parents[2]
APPROVED_KB_V2 = REPO_ROOT / "data" / "knowledge" / "approved_kb.v2.json"
KB_RELEASE_PATH = REPO_ROOT / "apps" / "ai_service" / "kb-release.json"
INTENT_POLICY_PATH = REPO_ROOT / "apps" / "core_backend" / "config" / "policies" / "intent_policy.v2.json"

AS_OF_2026 = datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc)


def _norm(vec: list[float]) -> list[float]:
    arr = np.asarray(vec, dtype=np.float32)
    n = float(np.linalg.norm(arr))
    return (arr / n).tolist() if n > 0 else arr.tolist()


class ControlledEncoder:
    """Deterministic unit-vector encoder for exact cosine/rank/threshold testing."""

    def __init__(self, doc_vectors: dict[str, list[float]], query_vectors: dict[str, list[float]]):
        self.doc_vectors = doc_vectors
        self.query_vectors = query_vectors

    def _encode_one(self, text: str, mapping: dict[str, list[float]]) -> np.ndarray:
        for key, vec in mapping.items():
            if key in text:
                return np.asarray(_norm(vec), dtype=np.float32)
        return np.asarray(_norm([0.0, 0.0, 0.0, 1.0]), dtype=np.float32)

    def encode_passages(self, texts: list[str]) -> np.ndarray:
        return np.vstack([self._encode_one(t, self.doc_vectors) for t in texts]).astype(np.float32)

    def encode_queries(self, texts: list[str]) -> np.ndarray:
        return np.vstack([self._encode_one(t, self.query_vectors) for t in texts]).astype(np.float32)


def _kb_entry(
    doc_id: str,
    title: str,
    content: str,
    supported_intents=None,
    include_supported_intents: bool = True,
    answer_capabilities=None,
    policy_key: str | None = None,
    version: str = "1.0",
) -> dict:
    entry = {
        "doc_id": doc_id,
        "document_id": doc_id,
        "version": version,
        "title": title,
        "category": "policy",
        "content": content,
        "status": "approved",
        "approved_by": "qa_reviewer",
        "approved_at": "2026-01-01T00:00:00Z",
        "valid_from": "2026-01-01T00:00:00Z",
        "valid_to": "2026-12-31T23:59:59Z",
        "allowed_roles": ["agent", "customer"],
        "answer_capabilities": answer_capabilities if answer_capabilities is not None else ["general_policy"],
    }
    if policy_key is not None:
        entry["policy_key"] = policy_key
    if include_supported_intents:
        entry["supported_intents"] = supported_intents
    return entry


def _make_crowdout_adapter(tmp_path: Path, aligned_score: float = 0.62, words_per_distractor: int = 600) -> RetrievalAdapter:
    """Build KB where 3 wrong-intent docs outrank and exceed 1500 tokens ahead of 1 aligned doc."""
    pad = " ".join(["filler"] * words_per_distractor)
    kb = [
        _kb_entry("DIST-1", "Shipping D1", f"dist_one {pad}", supported_intents=["shipping_costs"], policy_key="k1"),
        _kb_entry("DIST-2", "Shipping D2", f"dist_two {pad}", supported_intents=["shipping_costs"], policy_key="k2"),
        _kb_entry("DIST-3", "Shipping D3", f"dist_three {pad}", supported_intents=["shipping_costs"], policy_key="k3"),
        _kb_entry(
            "POL-RET-ALIGNED",
            "Aligned Return Doc",
            "aligned_ret return window is 30 days via courier pickup",
            supported_intents=["return_policy"],
            answer_capabilities=["return_window"],
            policy_key="return_window",
        ),
    ]
    kb_path = tmp_path / "kb.json"
    kb_path.write_text(json.dumps(kb), encoding="utf-8")

    # Query aligns with e0 = [1, 0, 0, 0].
    # Distractors score 0.95, 0.90, 0.85 against e0.
    # Aligned doc scores exact `aligned_score` against e0 while remaining unit length.
    rem = math.sqrt(max(0.0, 1.0 - aligned_score * aligned_score))
    enc = ControlledEncoder(
        doc_vectors={
            "dist_one": [0.95, math.sqrt(1 - 0.95**2), 0.0, 0.0],
            "dist_two": [0.90, math.sqrt(1 - 0.90**2), 0.0, 0.0],
            "dist_three": [0.85, math.sqrt(1 - 0.85**2), 0.0, 0.0],
            "aligned_ret": [aligned_score, 0.0, rem, 0.0],
        },
        query_vectors={"q_crowdout": [1.0, 0.0, 0.0, 0.0]},
    )
    return RetrievalAdapter(kb_path=str(kb_path), encoder=enc, relevance_threshold=0.55)


# ---------------------------------------------------------------------------
# Sub-gap 1a: RetrievalAdapter invariants
# ---------------------------------------------------------------------------


def test_gap1a_top3_and_token_budget_crowdout_recovers_aligned_doc(tmp_path: Path):
    adapter = _make_crowdout_adapter(tmp_path, aligned_score=0.62, words_per_distractor=600)
    res = adapter.retrieve("q_crowdout return item", intent="return_policy", current_time=AS_OF_2026)

    assert res["status"] == "success"
    doc_ids = [item["document_id"] for item in res["evidence"]]
    assert doc_ids == ["POL-RET-ALIGNED"]


def test_gap1a_false_confident_wrong_intent_and_subthreshold_boost_blocked(tmp_path: Path):
    # Aligned doc has raw_score=0.45 (< 0.55 threshold); even +0.15 boost (0.60) MUST NOT pass!
    # Meanwhile DIST-1..3 have 0.85..0.95 for wrong intent and MUST NOT be returned.
    adapter = _make_crowdout_adapter(tmp_path, aligned_score=0.45, words_per_distractor=20)
    res = adapter.retrieve("q_crowdout unrelated or OOD", intent="return_policy", current_time=AS_OF_2026)

    assert res["status"] == "no_match"
    assert res["evidence"] == []
    assert "below_relevance_threshold" in res.get("reason_codes", [])


def test_gap1a_never_attaches_unrelated_docs_alongside_aligned_doc(tmp_path: Path):
    # Ensure mixed pool only returns passing docs aligned to requested intent, never POL-ORD-003 style hitchhikers.
    kb = [
        _kb_entry("POL-RET-001", "Return Rules", "ret_txt 30 day return", supported_intents=["return_policy"], policy_key="ret"),
        _kb_entry("POL-ORD-003", "Order Modification", "ord_txt modify address", supported_intents=["change_order"], policy_key="ord"),
    ]
    kb_path = tmp_path / "kb_mixed.json"
    kb_path.write_text(json.dumps(kb), encoding="utf-8")
    enc = ControlledEncoder(
        doc_vectors={"ret_txt": [0.80, 0.60, 0.0, 0.0], "ord_txt": [0.90, 0.43589, 0.0, 0.0]},
        query_vectors={"q_ret": [1.0, 0.0, 0.0, 0.0]},
    )
    adapter = RetrievalAdapter(kb_path=str(kb_path), encoder=enc, relevance_threshold=0.55)
    res = adapter.retrieve("q_ret return policy", intent="return_policy", current_time=AS_OF_2026)

    assert res["status"] == "success"
    assert [e["document_id"] for e in res["evidence"]] == ["POL-RET-001"]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"include_supported_intents": False},
        {"include_supported_intents": True, "supported_intents": []},
        {"include_supported_intents": True, "supported_intents": "return_policy"},
        {"include_supported_intents": True, "supported_intents": [""]},
        {"include_supported_intents": True, "supported_intents": None},
    ],
)
def test_gap1a_missing_empty_or_malformed_supported_intents_fail_closed(tmp_path: Path, kwargs: dict):
    kb = [_kb_entry("DOC-UNANNOTATED", "Generic Doc", "univ_txt return policy", **kwargs)]
    kb_path = tmp_path / "kb_unannotated.json"
    kb_path.write_text(json.dumps(kb), encoding="utf-8")
    enc = ControlledEncoder(
        doc_vectors={"univ_txt": [1.0, 0.0, 0.0, 0.0]},
        query_vectors={"q_univ": [1.0, 0.0, 0.0, 0.0]},
    )
    adapter = RetrievalAdapter(kb_path=str(kb_path), encoder=enc, relevance_threshold=0.55)
    res = adapter.retrieve("q_univ return policy", intent="return_policy", current_time=AS_OF_2026)

    assert res["status"] in ("no_match", "empty_kb")
    assert res["evidence"] == []


@pytest.mark.parametrize("bad_intent", ["", "   ", None, 123, "unknown_made_up_intent"])
def test_gap1a_empty_whitespace_nonstring_or_unknown_intent_fails_closed(tmp_path: Path, bad_intent):
    kb = [
        _kb_entry("POL-RET-001", "Return Rules", "ret_txt return 30 days", supported_intents=["return_policy"]),
    ]
    kb_path = tmp_path / "kb_intent_edge.json"
    kb_path.write_text(json.dumps(kb), encoding="utf-8")
    enc = ControlledEncoder(
        doc_vectors={"ret_txt": [1.0, 0.0, 0.0, 0.0]},
        query_vectors={"q_edge": [1.0, 0.0, 0.0, 0.0]},
    )
    adapter = RetrievalAdapter(kb_path=str(kb_path), encoder=enc, relevance_threshold=0.55)
    res = adapter.retrieve("q_edge return", intent=bad_intent, current_time=AS_OF_2026)

    assert res["status"] == "no_match"
    assert res["evidence"] == []

    res_human = adapter.retrieve("q_edge human", intent="human_agent", current_time=AS_OF_2026)
    assert res_human["status"] == "human_agent_escalation"
    assert res_human["evidence"] == []


def test_gap1a_allowed_document_versions_release_isolation(tmp_path: Path):
    kb = [
        _kb_entry("POL-RET-001", "Return Rules", "ret_txt return 30 days", supported_intents=["return_policy"], version="2.0"),
    ]
    kb_path = tmp_path / "kb_rel.json"
    kb_path.write_text(json.dumps(kb), encoding="utf-8")
    enc = ControlledEncoder(
        doc_vectors={"ret_txt": [1.0, 0.0, 0.0, 0.0]},
        query_vectors={"q_rel": [1.0, 0.0, 0.0, 0.0]},
    )
    # Wrong release version ("1.0" instead of "2.0") must fail closed.
    adapter = RetrievalAdapter(
        kb_path=str(kb_path),
        encoder=enc,
        allowed_document_versions={("POL-RET-001", "1.0")},
        relevance_threshold=0.55,
    )
    res = adapter.retrieve("q_rel return", intent="return_policy", current_time=AS_OF_2026)
    assert res["status"] in ("no_match", "empty_kb")
    assert res["evidence"] == []


# ---------------------------------------------------------------------------
# Sub-gap 1b: KB-evidence-checked capability/channel scope (Engine + PipelineRunner)
# ---------------------------------------------------------------------------


def _load_real_kb_and_release() -> tuple[list[dict], set[tuple[str, str]], dict]:
    kb_docs = json.loads(APPROVED_KB_V2.read_text(encoding="utf-8"))
    release = json.loads(KB_RELEASE_PATH.read_text(encoding="utf-8"))
    allowed = {(d["document_id"], str(d["version"])) for d in release["documents"]}
    policy = json.loads(INTENT_POLICY_PATH.read_text(encoding="utf-8"))
    return kb_docs, allowed, policy


class StaticIntentModel:
    def __init__(self, intent: str):
        self.intent = intent

    def predict(self, text: str) -> dict:
        return {
            "intent": self.intent,
            "confidence": 0.96,
            "margin": 0.85,
            "score_kind": "calibrated_temperature",
            "top_k": [{"intent": self.intent, "probability": 0.96}],
            "model_version": "slice1-test-model",
        }


class StubLLM:
    configured = False

    def generate(self, *args, **kwargs):
        sources = kwargs.get("sources")
        if sources is None and len(args) >= 3 and isinstance(args[2], list):
            sources = [
                {
                    "source_id": f"S{idx + 1}",
                    "source_type": item.get("source_type", "policy"),
                    "document_id": item.get("document_id") or item.get("doc_id"),
                    "version": str(item.get("version", "")),
                    "title": item.get("title", ""),
                    "excerpt": item.get("excerpt", ""),
                }
                for idx, item in enumerate(args[2])
            ]
        return {
            "body": "Please follow our official Tiki policy. [S1]",
            "input_snapshot": {"sources": sources or []},
        }


class StaticScopeRetriever:
    """Offline retriever backed by real approved_kb.v2.json docs + kb-release.json."""

    def __init__(self, doc_ids_by_intent: dict[str, list[str]]):
        kb_docs, allowed, _ = _load_real_kb_and_release()
        self.eligible_versions = []
        self._docs_by_id = {}
        for d in kb_docs:
            key = (d["document_id"], str(d["version"]))
            if key not in allowed:
                continue
            pv = SimpleNamespace(
                doc_id=d["document_id"],
                version=str(d["version"]),
                title=d["title"],
                content=d["content"],
                metadata=SimpleNamespace(
                    status=d["status"],
                    valid_from=d["valid_from"],
                    valid_to=d["valid_to"],
                    supported_intents=d["supported_intents"],
                    answer_capabilities=d["answer_capabilities"],
                    policy_key=d.get("policy_key"),
                ),
            )
            self.eligible_versions.append(pv)
            self._docs_by_id[d["document_id"]] = pv
        self.doc_ids_by_intent = doc_ids_by_intent

    def retrieve(self, query: str, intent: str = "", role: str = "customer", current_time=None):
        ids = self.doc_ids_by_intent.get(intent, [])
        evidence = []
        for did in ids:
            pv = self._docs_by_id[did]
            evidence.append(
                {
                    "source_type": "policy",
                    "document_id": pv.doc_id,
                    "doc_id": pv.doc_id,
                    "version": pv.version,
                    "title": pv.title,
                    "excerpt": pv.content,
                    "capabilities": list(pv.metadata.answer_capabilities),
                    "score": 0.92,
                }
            )
        return {"status": "success" if evidence else "no_match", "evidence": evidence, "has_conflict": False}


def _build_engine_and_runner(
    tmp_path: Path, intent: str, doc_ids: list[str], fake_llm=None
) -> tuple[Engine, PipelineRunner]:
    _, _, policy = _load_real_kb_and_release()
    retriever = StaticScopeRetriever({intent: doc_ids})
    manifest = {"release_id": "slice1-test-release"}
    engine = Engine(StaticIntentModel(intent), retriever, StubLLM(), manifest, policy=policy)

    def ok_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "intent": intent,
                "confidence": 0.96,
                "margin": 0.85,
                "top_k": [{"intent": intent, "probability": 0.96}],
                "model_version": "v1.0.0",
                "verified": True,
            },
        )

    intent_client = IntentClient(
        base_url="http://ml.local",
        http_client=httpx.Client(transport=httpx.MockTransport(ok_handler), trust_env=False),
    )
    store = PersistentStore(db_path=str(tmp_path / f"store_{intent}.sqlite3"))
    runner = PipelineRunner(
        intent_client=intent_client,
        store=store,
        llm_client=fake_llm if fake_llm is not None else StubLLM(),
        retrieval_adapter=retriever,
    )
    return engine, runner


def _assert_both_escalate(
    tmp_path: Path,
    text: str,
    intent: str,
    doc_ids: list[str],
    ctx: RoutingContext | None = None,
):
    engine, runner = _build_engine_and_runner(tmp_path, intent, doc_ids)
    eng_res = engine.analyse({"message": text, "as_of": AS_OF_2026.isoformat()})
    assert eng_res["routing"]["recommendation"] == "escalate", f"Engine failed to escalate: {text}"
    assert "insufficient_evidence" in eng_res["routing"]["reason_codes"]
    assert validate_analysis(eng_res) is eng_res

    run_ctx = ctx or RoutingContext(ticket_customer_id="demo-customer", is_personal_lookup=False)
    run_res = runner.run(text, run_ctx)
    assert run_res["action"] == "escalate", f"PipelineRunner failed to escalate: {text} -> {run_res}"
    assert "insufficient_evidence" in run_res["reason_codes"]


def _assert_both_allow(
    tmp_path: Path,
    text: str,
    intent: str,
    doc_ids: list[str],
    ctx: RoutingContext | None = None,
    fake_llm=None,
):
    engine, runner = _build_engine_and_runner(tmp_path, intent, doc_ids, fake_llm=fake_llm)
    eng_res = engine.analyse({"message": text, "as_of": AS_OF_2026.isoformat()})
    assert eng_res["routing"]["recommendation"] != "escalate", f"Engine false-escalated: {text}"

    ctx = ctx or RoutingContext(ticket_customer_id="demo-customer", is_personal_lookup=False)
    run_res = runner.run(text, ctx)
    assert run_res["action"] == "retrieve_draft", f"PipelineRunner false-blocked: {text} -> {run_res}"


@pytest.mark.parametrize(
    "query",
    [
        "Can I return this sweater in store?",
        "Where is your nearest retail branch to drop off a return?",
        "I want to exchange this defective charger at a physical shopfront counter.",
        "Can I bring the item back in stroe instead of waiting for pickup?",
        "Why can't I return an online purchase at your retail outlet?",
        "Can I 'return in store' if I live nearby?",
        "How do I return via courier pickup or bring it into a brick-and-mortar store?",
    ],
)
def test_gap1b_unsupported_physical_store_channel_escalates_in_both_paths(tmp_path: Path, query: str):
    _assert_both_escalate(tmp_path, query, "return_product", ["POL-RET-002", "POL-RET-001"])


@pytest.mark.parametrize(
    "query",
    [
        "Where can I print a prepaid return shipping label?",
        "Please generate and email me a downloadable return label PDF.",
        "Where is the self-service return label portal on the website?",
        "Can I initiate a return on the app and print my own prepaid shipping label?",
        "Why is there no prepaid return label option for my return?",
    ],
)
def test_gap1b_unsupported_prepaid_return_label_escalates_in_both_paths(tmp_path: Path, query: str):
    _assert_both_escalate(tmp_path, query, "return_product", ["POL-RET-002"])


@pytest.mark.parametrize(
    "query,ctx",
    [
        (
            "What is the policy on downloading full order history or purchase logs?",
            RoutingContext(
                ticket_customer_id="demo-customer",
                verified_scope="ticket:read order:read",
                is_personal_lookup=False,
                extracted_slots={"order_id": "ORD-1001"},
            ),
        ),
        (
            "Show me my full account order history.",
            RoutingContext(
                ticket_customer_id="demo-customer",
                verified_scope="ticket:read order:read",
                is_personal_lookup=True,
                extracted_slots={"order_id": "ORD-1001"},
            ),
        ),
        (
            "Can I export a list of all my past purchases on Tiki?",
            RoutingContext(
                ticket_customer_id="demo-customer",
                verified_scope="ticket:read order:read",
                is_personal_lookup=True,
                extracted_slots={"order_id": "ORD-1001"},
            ),
        ),
        (
            "Check ORD-1001 and also send me my entire purchase history list.",
            RoutingContext(
                ticket_customer_id="demo-customer",
                verified_scope="ticket:read order:read",
                is_personal_lookup=True,
                extracted_slots={"order_id": "ORD-1001"},
            ),
        ),
        (
            "I want to see every order I have ever placed in my account.",
            RoutingContext(
                ticket_customer_id="demo-customer",
                verified_scope="ticket:read order:read",
                is_personal_lookup=True,
                extracted_slots={"order_id": "ORD-1001"},
            ),
        ),
        (
            "Can I download my complete order history from last year?",
            RoutingContext(
                ticket_customer_id="demo-customer",
                verified_scope="ticket:read order:read",
                is_personal_lookup=True,
                extracted_slots={"order_id": "ORD-1001"},
            ),
        ),
    ],
)
def test_gap1b_unsupported_full_order_history_escalates_in_both_paths(
    tmp_path: Path, query: str, ctx: RoutingContext | None
):
    _assert_both_escalate(tmp_path, query, "track_order", ["POL-ORD-001"], ctx=ctx)


@pytest.mark.parametrize(
    "text,intent,doc_ids,ctx",
    [
        (
            "Can I drop off my return package at a designated Tiki partner post office?",
            "return_product",
            ["POL-RET-002"],
            None,
        ),
        (
            "Will a shipping courier pick up my return item from my address for free?",
            "return_product",
            ["POL-RET-002"],
            None,
        ),
        (
            "I bought this item in store yesterday — how do I request an online courier return?",
            "return_product",
            ["POL-RET-002"],
            None,
        ),
        (
            "I purchased a gift in stroe, can courier pick up my return?",
            "return_product",
            ["POL-RET-002"],
            None,
        ),
        (
            "Can I receive store credit when returning via courier pickup?",
            "return_product",
            ["POL-RET-002"],
            None,
        ),
        (
            "Instead of visiting a retail store, can a courier pick up my return?",
            "return_product",
            ["POL-RET-002"],
            None,
        ),
        (
            "I don't need a prepaid return label — how do I schedule app courier pickup?",
            "return_product",
            ["POL-RET-002"],
            None,
        ),
        (
            "Support said 'bring it to a store', instead can I use a partner post office?",
            "return_product",
            ["POL-RET-002"],
            None,
        ),
        (
            "Where can I view order tracking in 'My Orders' on the Tiki app?",
            "track_order",
            ["POL-ORD-001"],
            RoutingContext(
                ticket_customer_id="demo-customer",
                verified_scope="ticket:read order:read",
                is_personal_lookup=True,
                extracted_slots={"order_id": "ORD-1001"},
            ),
        ),
        (
            "Where can I check the status of order ORD-1001?",
            "track_order",
            ["POL-ORD-001"],
            RoutingContext(
                ticket_customer_id="demo-customer",
                verified_scope="ticket:read order:read",
                is_personal_lookup=True,
                extracted_slots={"order_id": "ORD-1001"},
            ),
        ),
        (
            "How can I check my refund history on Tiki?",
            "refund_status",
            ["POL-REFUND-007"],
            None,
        ),
    ],
)
def test_gap1b_supported_counterexamples_remain_allowed(
    tmp_path: Path, text: str, intent: str, doc_ids: list[str], ctx: RoutingContext | None, fake_llm
):
    _assert_both_allow(tmp_path, text, intent, doc_ids, ctx, fake_llm=fake_llm)


def test_gap1b_ignores_untrusted_capabilities_and_unverified_citations():
    # Self-declared capabilities or tampered source_type="llm" / wrong version MUST NOT satisfy scope check.
    retriever = StaticScopeRetriever({"return_product": ["POL-RET-002"]})
    untrusted_evidence = [
        {
            "source_type": "llm_citation",
            "document_id": "POL-RET-002",
            "version": "2.0",
            "excerpt": "Customers may return items in store with a prepaid return label.",
            "capabilities": ["in_store_return", "prepaid_return_label"],
        },
        {
            "source_type": "policy",
            "document_id": "POL-RET-002",
            "version": "99.0",  # Not in eligible_versions!
            "excerpt": "Customers may return items in store.",
            "capabilities": ["in_store_return"],
        },
    ]
    assert policy_scope_requires_review("Can I return in store?", untrusted_evidence, retriever.eligible_versions) is True
    assert (
        policy_scope_requires_review(
            "Where can I download a prepaid return label?", untrusted_evidence, retriever.eligible_versions
        )
        is True
    )
    assert evaluate_evidence_scope(
        "Show me my full order history",
        {"status": "success", "has_conflict": False},
        [{"source_type": "policy", "document_id": "POL-ORD-001", "version": "1.0", "capabilities": ["order_history"]}],
        retriever.eligible_versions,
    ) == ("escalate", ["insufficient_evidence"])


def test_gap1b_mixed_purchase_plus_channel_edge_cases():
    retriever = StaticScopeRetriever({"return_product": ["POL-RET-002"], "track_order": ["POL-ORD-001"]})
    ev_ret = retriever.retrieve("return", "return_product")["evidence"]
    ev_ord = retriever.retrieve("track", "track_order")["evidence"]
    # Purchased online, trying to return in store -> MUST escalate
    assert policy_scope_requires_review("I bought it online and want to return it in store.", ev_ret, retriever.eligible_versions) is True
    # Purchased in store, returning via courier -> MUST allow
    assert policy_scope_requires_review("I want to return the item I bought in store via courier.", ev_ret, retriever.eligible_versions) is False
    # Unslotted 'My Orders' general question -> MUST allow
    assert policy_scope_requires_review("How do I check order status in 'My Orders' on the Tiki app?", ev_ord, retriever.eligible_versions) is False


def test_gap1b_non_transposition_typo_residual_documented_behavior():
    # Non-transposition substitution/deletion typos (e.g. "in storr") are explicitly NOT heuristic-patched
    # to avoid false-positive English homograph collisions.
    retriever = StaticScopeRetriever({"return_product": ["POL-RET-002"]})
    ev = retriever.retrieve("return", "return_product")["evidence"]
    assert policy_scope_requires_review("Can I return this in storr?", ev, retriever.eligible_versions) is False


@pytest.mark.parametrize(
    "query",
    [
        "Can I drop off my online return at a local physical shop branch?",
        "Does your physical shop counter accept returns from web orders?",
        "Do your local storefronts accept in-person product returns?",
        "Can I bring my online order back to one of your shops?",
        "Do mall storefronts accept returns?",
        "Are retail shops open for walk-in exchanges?",
        "Can I return this at a Tiki shop?",
        "Could a brick-and-mortar Tiki shop take this return in person?",
        "I bought this shirt in store and want to take it back in store.",
    ],
)
def test_gap1b_review_blockers_physical_shop_and_take_back_escalate(tmp_path: Path, query: str):
    _assert_both_escalate(tmp_path, query, "return_product", ["POL-RET-002", "POL-RET-001"])


@pytest.mark.parametrize(
    "query",
    [
        "Show all historical orders I have ever placed with my login.",
        "Can I track ORD-1001 and also see every historical order from my account?",
        "Export every past purchase under my login.",
    ],
)
def test_gap1b_review_blockers_historical_orders_escalate(tmp_path: Path, query: str):
    ctx = RoutingContext(
        ticket_customer_id="demo-customer",
        verified_scope="ticket:read order:read",
        is_personal_lookup=True,
        extracted_slots={"order_id": "ORD-1001"},
    )
    _assert_both_escalate(tmp_path, query, "track_order", ["POL-ORD-001"], ctx=ctx)


@pytest.mark.parametrize(
    "query",
    [
        "Where can I print my own return label at home?",
        "Where is the portal to download a printable shipping label?",
    ],
)
def test_gap1b_review_blockers_self_print_label_escalates(tmp_path: Path, query: str):
    _assert_both_escalate(tmp_path, query, "return_product", ["POL-RET-002"])


@pytest.mark.parametrize(
    "text,intent,doc_ids,ctx",
    [
        (
            "Please send me a return shipping label for my item.",
            "return_product",
            ["POL-RET-002"],
            None,
        ),
        (
            "Does the courier bring a return label when picking up my return?",
            "return_product",
            ["POL-RET-002"],
            None,
        ),
        (
            "I checked my order history for ORD-1001 and it shows In Transit — when does ORD-1001 arrive?",
            "track_order",
            ["POL-ORD-001"],
            RoutingContext(
                ticket_customer_id="demo-customer",
                verified_scope="ticket:read order:read",
                is_personal_lookup=True,
                extracted_slots={"order_id": "ORD-1001"},
            ),
        ),
        (
            "I bought this shirt in store and want to take it back via courier pickup.",
            "return_product",
            ["POL-RET-002"],
            None,
        ),
        (
            "The local shop sent me a defective kettle — how do I initiate a courier return?",
            "return_product",
            ["POL-RET-002"],
            None,
        ),
        (
            "Will the driver pick up my return in person from my address?",
            "return_product",
            ["POL-RET-002"],
            None,
        ),
        (
            "My friend asked 'do your shops take returns', instead I just want a courier pickup at my home.",
            "return_product",
            ["POL-RET-002"],
            None,
        ),
    ],
)
def test_gap1b_review_counterexamples_and_ordinary_labels_remain_allowed(
    tmp_path: Path, text: str, intent: str, doc_ids: list[str], ctx: RoutingContext | None, fake_llm
):
    _assert_both_allow(tmp_path, text, intent, doc_ids, ctx, fake_llm=fake_llm)


@pytest.mark.parametrize(
    "text,intent,doc_ids",
    [
        (
            "I do not want to go to a physical store; can I schedule courier pickup for my return instead?",
            "return_product",
            ["POL-RET-002", "POL-RET-001"],
        ),
        (
            "I cannot travel to a retail store branch — how does Tiki's free courier pickup work for defective items?",
            "return_product",
            ["POL-RET-002", "POL-RET-001"],
        ),
        (
            "We're unable to drive to a physical store branch — can a courier pick up the return instead?",
            "return_product",
            ["POL-RET-002"],
        ),
        (
            "I can’t walk to a retail store, how do I drop off at a partner post office?",
            "return_product",
            ["POL-RET-002"],
        ),
        (
            "We won't head into a local shop; please arrange courier return pickup.",
            "return_product",
            ["POL-RET-002"],
        ),
        (
            "I'd rather not travel to a storefront counter, can I use the Tiki app for pickup?",
            "return_product",
            ["POL-RET-002"],
        ),
        (
            "Instead of going to a retail store, can I drop the parcel off at a partner post office?",
            "return_product",
            ["POL-RET-002"],
        ),
        (
            "I do not need to print a prepaid return label — I just want courier pickup from my address.",
            "return_product",
            ["POL-RET-002"],
        ),
    ],
)
def test_gap1b_negated_modal_and_motion_declining_physical_channel_remains_allowed(
    tmp_path: Path, text: str, intent: str, doc_ids: list[str], fake_llm
):
    _assert_both_allow(tmp_path, text, intent, doc_ids, fake_llm=fake_llm)


@pytest.mark.parametrize(
    "query",
    [
        "I cannot visit today but want return in store tomorrow.",
        "I cannot visit today and want to return in store tomorrow.",
        "I cannot wait for a courier so I want to return in store.",
        "Not courier but physical store return please.",
        "Instead of courier — physical store return please.",
        "I do not want to go to a physical store today, so can I drop it off at a local shop tomorrow?",
        "Why can't I travel to a retail store branch to return this?",
        "Online order — I cannot print a return label at home, can I drop it off at a physical store?",
        "Can a customer 'go to a physical store' to return an item?",
    ],
)
def test_gap1b_compound_contradictions_and_negated_wrong_object_still_escalate(tmp_path: Path, query: str):
    _assert_both_escalate(tmp_path, query, "return_product", ["POL-RET-002", "POL-RET-001"])


@pytest.mark.parametrize(
    "text,intent,doc_ids",
    [
        (
            "We will not bring the faulty headset into a local store; instead, please explain the 1-2 business day courier pickup process.",
            "return_product",
            ["POL-RET-002", "POL-RET-001"],
        ),
        (
            "I won't take my damaged laptop into a physical store; please schedule courier pickup.",
            "return_product",
            ["POL-RET-002"],
        ),
        (
            "We are not returning the big broken OLED monitor to a retail branch — how does courier pickup work?",
            "return_product",
            ["POL-RET-002"],
        ),
        (
            "We do not plan to drop off the heavy microwave at a local storefront; please share post office steps.",
            "return_product",
            ["POL-RET-002"],
        ),
        (
            "I'm not going to carry this bulky wireless printer into a retail outlet — can a courier pick it up?",
            "return_product",
            ["POL-RET-002"],
        ),
        (
            "We won't hand the defective keyboard in at a physical shop; let's use partner post office drop-off.",
            "return_product",
            ["POL-RET-002"],
        ),
        (
            "Without bringing the faulty headset into a local store, how do I book courier pickup?",
            "return_product",
            ["POL-RET-002"],
        ),
        (
            "A friend joked 'just walk into a retail store', though I actually plan to drop the box at a designated partner post office.",
            "return_product",
            ["POL-RET-002", "POL-RET-001"],
        ),
        (
            'My coworker joked: "drop it off at a physical branch" — instead, how do I schedule courier pickup?',
            "return_product",
            ["POL-RET-002"],
        ),
        (
            "A friend joked, 'go into a local shop', rather than doing that I want courier pickup from my condo.",
            "return_product",
            ["POL-RET-002"],
        ),
        (
            "Support suggested 'return at a local store' by mistake, please help me arrange courier pickup.",
            "return_product",
            ["POL-RET-002"],
        ),
        (
            "An old forum post claimed 'walk into any retail outlet', instead how do I return online?",
            "return_product",
            ["POL-RET-002"],
        ),
    ],
)
def test_gap1c_transitive_negated_action_and_quoted_speech_remain_allowed(
    tmp_path: Path, text: str, intent: str, doc_ids: list[str], fake_llm
):
    _assert_both_allow(tmp_path, text, intent, doc_ids, fake_llm=fake_llm)


@pytest.mark.parametrize(
    "query",
    [
        "I joked before, but now I want to go to a physical store.",
        "I joked 'never going to a store' before, but now I want to go to a physical store.",
        "A friend joked 'just walk into a retail store', though can I still drop my shoes off at a local store?",
        "The FAQ claims 'online pickup is standard', yet can I personally walk into a brick-and-mortar store to return shoes?",
        "Can I 'just walk into a retail store'?",
        "We will not bring the faulty headset today — can I drop it off into a local store tomorrow?",
        "We won't bring a receipt -- can we bring the faulty headset into a local store?",
        "I cannot print a return label to bring this headset into a local store.",
        "Without a home printer may I bring the microwave directly to a local storefront?",
        "Without bringing a receipt I will go into a local store.",
        "We will not wait for pickup and will take the headset into a local store instead.",
        "We will not bring a box so I want to bring the faulty headset into a local store.",
    ],
)
def test_gap1c_quote_positive_controls_and_unrelated_negation_still_escalate(tmp_path: Path, query: str):
    _assert_both_escalate(tmp_path, query, "return_product", ["POL-RET-002", "POL-RET-001"])


def test_gap1c_multichannel_negated_single_order_plus_full_history_escalates(tmp_path: Path):
    ctx = RoutingContext(
        ticket_customer_id="demo-customer",
        verified_scope="ticket:read order:read",
        is_personal_lookup=True,
        extracted_slots={"order_id": "ORD-1001"},
    )
    _assert_both_escalate(
        tmp_path,
        "I do not only want order ORD-1001; please send a full spreadsheet of all historical orders from my account.",
        "track_order",
        ["POL-ORD-001"],
        ctx=ctx,
    )


class _PreLLMSpy(StubLLM):
    configured = True

    def __init__(self):
        self.calls: list[tuple] = []

    def generate(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return super().generate(*args, **kwargs)


def _assert_pre_llm_escalate(tmp_path: Path, query: str, retriever) -> None:
    _, _, policy = _load_real_kb_and_release()
    manifest = {"release_id": "slice1-test-release"}

    eng_spy = _PreLLMSpy()
    engine = Engine(StaticIntentModel("return_product"), retriever, eng_spy, manifest, policy=policy)
    eng_res = engine.analyse({"message": query, "as_of": AS_OF_2026.isoformat()})
    assert eng_res["routing"]["recommendation"] == "escalate", f"Engine leaked pre-LLM draft: {query} -> {eng_res}"
    assert "insufficient_evidence" in eng_res["routing"]["reason_codes"]
    assert eng_spy.calls == [], f"Engine invoked provider LLM before scope escalation: {query}"
    assert validate_analysis(eng_res) is eng_res

    def ok_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "intent": "return_product",
                "confidence": 0.96,
                "margin": 0.85,
                "top_k": [{"intent": "return_product", "probability": 0.96}],
                "model_version": "v1.0.0",
                "verified": True,
            },
        )

    intent_client = IntentClient(
        base_url="http://ml.local",
        http_client=httpx.Client(transport=httpx.MockTransport(ok_handler), trust_env=False),
    )
    run_spy = _PreLLMSpy()
    runner = PipelineRunner(
        intent_client=intent_client,
        store=PersistentStore(db_path=str(tmp_path / "store_spy.sqlite3")),
        llm_client=run_spy,
        retrieval_adapter=retriever,
    )
    run_res = runner.run(query, RoutingContext(ticket_customer_id="demo-customer", is_personal_lookup=False))
    assert run_res["action"] == "escalate", f"PipelineRunner leaked: {query} -> {run_res}"
    assert "insufficient_evidence" in run_res["reason_codes"]
    assert run_spy.calls == [], f"PipelineRunner invoked provider LLM before scope escalation: {query}"


@pytest.mark.parametrize(
    "query",
    [
        # Worker B 6 end-to-end FAIL-OPEN repros (+ deliver leak)
        "I can't return this item except at a physical store",
        "I cannot return the opened TV without stopping by a physical store",
        "I won't return my item instead head to a retail shop",
        "I cannot ship my parcel home deliver it at a physical shop",
        "Without bringing the box to a physical store, can I still return my headphones?",
        "I asked, 'can I walk into a physical shop to return this?'",
        "Could support advise, 'bring it to a physical shop', and can I do that now?",
        # Structural & clause paraphrases for exception, contrast, unqualified without/negation, and quote traps
        "I can't return it except at a retail shop.",
        "Instead of courier, I can't return this item except at a physical store.",
        "We won't drop our parcel off only return at a physical shop.",
        "I will not return my item unless at a physical store.",
        "Without visiting a physical store, can I still return my headphones?",
        "We will not go to a physical store; can I still return this defective item?",
        "We asked, 'can we walk into a physical shop to return this?'",
        "Can someone advise, 'bring it to a physical shop', and can I do that now?",
        "My friend joked 'just walk into a retail store', and can I do that now?",
        "My friend joked 'just walk into a retail store' — can I do that or schedule courier pickup?",
        "A friend joked 'use courier or walk into a retail store'?",
    ],
)
def test_gap1d_fail_open_exception_unqualified_and_quote_traps_block_pre_llm(tmp_path: Path, query: str):
    retriever = StaticScopeRetriever({"return_product": ["POL-RET-002", "POL-RET-001"]})
    _assert_pre_llm_escalate(tmp_path, query, retriever)


@pytest.fixture(scope="module")
def real_scope_retriever() -> RetrievalAdapter:
    _, allowed, _ = _load_real_kb_and_release()
    return RetrievalAdapter(kb_path=str(APPROVED_KB_V2), allowed_document_versions=allowed)


@pytest.mark.parametrize(
    "query",
    [
        # Worker B 9 end-to-end FAIL-OPEN leaks (Engine='draft', Runner calls==1 on c466ffaa)
        "I won't return this excluding at a physical store, can I use a courier?",
        "I can't return it besides at a physical store, or can I use a courier?",
        "I won't return my item save at a physical store, or can I book a courier?",
        "My friend said 'walk into a physical store to return it' — is that an option, or courier pickup?",
        "Someone told me 'return it in-store' — does that work, or should I use the app?",
        "A friend said 'bring it to a physical store', should I go ahead with that or use courier?",
        "Can I use the option 'return at a physical store' to send back my order?",
        "Where do I click the button 'drop off at a physical store' so I can return this?",
        "I am not using the app, and without visiting a physical store, can I still return this?",
        # Metamorphic structural traps (unknown endorsement, bare contrast, UI modal, rejected courier, barring)
        "I won't return my item barring at a physical store, or can I book a courier?",
        "Support told me 'visit a physical branch' — is doing so fine if I prefer courier pickup?",
        "My friend said 'walk into a physical store', but can I do that?",
        "My friend said 'walk into a physical store', but can I do that or use courier pickup?",
        "A friend said 'drop off at a retail store', however does that work with the app?",
        "Should the user tap the tab 'return at a retail outlet' to get a refund?",
        "We are unable to use courier pickup, so without visiting a physical store, can I return this?",
        "Instead of 'return in store', can I still get a refund without visiting a physical shop?",
    ],
)
def test_gap1e_b_nine_leaks_and_structural_traps_block_pre_llm_with_real_retrieval(
    tmp_path: Path, real_scope_retriever: RetrievalAdapter, query: str
):
    real_ret = real_scope_retriever.retrieve(query, intent="return_product", current_time=AS_OF_2026)
    if real_ret["status"] == "success":
        _assert_pre_llm_escalate(tmp_path, query, real_scope_retriever)
    else:
        _assert_pre_llm_escalate(
            tmp_path, query, StaticScopeRetriever({"return_product": ["POL-RET-002", "POL-RET-001"]})
        )


@pytest.mark.parametrize(
    "text,intent,doc_ids",
    [
        (
            "The marketplace seller wrongly told me 'go to a physical store', but I want Tiki courier pickup through the app instead.",
            "return_product",
            ["POL-RET-002", "POL-RET-001"],
        ),
        (
            "Instead of 'return in store', how do I book a courier pickup?",
            "return_product",
            ["POL-RET-002"],
        ),
        (
            "Support wrote 'bring it to a physical branch' by mistake, instead please explain partner post office drop-off.",
            "return_product",
            ["POL-RET-002"],
        ),
        (
            "An old page shows the option 'return at a physical store', instead how do I return through the Tiki app?",
            "return_product",
            ["POL-RET-002"],
        ),
    ],
)
def test_gap1e_valid_third_party_quote_rejections_and_contrastive_ui_remain_allowed(
    tmp_path: Path, text: str, intent: str, doc_ids: list[str], fake_llm
):
    _assert_both_allow(tmp_path, text, intent, doc_ids, fake_llm=fake_llm)


@pytest.mark.parametrize(
    "query",
    [
        # Worker B's 8 exact end-to-end FAIL-OPEN leaks against 717ac038
        "My friend joked 'walk into a physical store to return it', and I want to do that along with the app.",
        "My friend joked 'walk into a physical store to return it' — please tell me I can do that before booking a courier.",
        "My friend joked 'walk into a physical store to return it' and I plan to go there instead of waiting for a courier.",
        "My friend joked 'walk into a physical store to return it' — is going there fine too, alongside booking a courier?",
        "My friend joked 'just walk into a retail store' — is visiting allowed before booking courier?",
        "Instead of buying online, a friend told me 'return at a physical store' — please confirm if visiting is okay when I use the app.",
        "My friend joked yesterday, anyway support told me 'bring it to a physical store', let's check via the app.",
        "Because courier isn't available, without visiting a physical store, can I still return this?",
        # Additional declarative/unreported/ambiguous/3rd-person negative alternative traps
        "My friend joked 'walk into a physical store', I'd like to do that.",
        "The FAQ says 'return at a physical store' — can you check courier pickup or how do I visit?",
        "Courier doesn't work in my area; without visiting a physical store, can I still return this?",
        "My friend joked 'walk into a physical store', how does courier pickup work?",
    ],
)
def test_gap1f_worker_b_eight_leaks_and_structural_traps_block_pre_llm(
    tmp_path: Path, real_scope_retriever: RetrievalAdapter, query: str
):
    real_ret = real_scope_retriever.retrieve(query, intent="return_product", current_time=AS_OF_2026)
    retriever = (
        real_scope_retriever
        if real_ret["status"] == "success"
        else StaticScopeRetriever({"return_product": ["POL-RET-002", "POL-RET-001"]})
    )
    _assert_pre_llm_escalate(tmp_path, query, retriever)


@pytest.mark.parametrize(
    "base_query",
    [
        "My friend joked 'walk into a physical store to return it' — I'd like to do that before booking a courier.",
        "Support told me 'visit a physical branch' — I want to go there after trying the app.",
        "A coworker said 'drop off at a physical store' — I plan to try that and use courier.",
        "An old page shows 'return at a physical store' — tell me that works instead of waiting for a courier.",
    ],
)
def test_gap1f_property_declarative_without_question_mark_never_unlocks(
    tmp_path: Path, real_scope_retriever: RetrievalAdapter, base_query: str
):
    # Invariant: stripping '?' or phrasing as a declarative statement must never bypass scope escalation.
    for idx, variant in enumerate((base_query, base_query.rstrip(".") + "?")):
        _assert_pre_llm_escalate(
            tmp_path / f"v{idx}",
            variant,
            StaticScopeRetriever({"return_product": ["POL-RET-002", "POL-RET-001"]}),
        )


@pytest.mark.parametrize(
    "unrelated_rejection,unsupported_quote",
    [
        ("Instead of buying online,", "a friend told me 'return at a physical store' via the app."),
        ("My friend joked yesterday;", "support told me 'bring it to a physical store' for courier pickup."),
        ("I didn't generate a label by mistake.", "Support wrote 'drop it at a physical shop' when booking courier."),
        ("No need for wrapping paper;", "my coworker said 'visit a physical store' after booking courier."),
    ],
)
def test_gap1f_property_unrelated_rejection_elsewhere_never_authorizes_quote(
    tmp_path: Path, unrelated_rejection: str, unsupported_quote: str
):
    # Invariant: inserting a rejection/contrast/joked token in an earlier clause must not grant a waiver to another quote.
    retriever = StaticScopeRetriever({"return_product": ["POL-RET-002", "POL-RET-001"]})
    _assert_pre_llm_escalate(tmp_path / "bare", unsupported_quote, retriever)
    _assert_pre_llm_escalate(tmp_path / "with_prefix", f"{unrelated_rejection} {unsupported_quote}", retriever)


@pytest.mark.parametrize(
    "negated_alt_query",
    [
        "Because courier isn't available, without visiting a physical store, can I return this?",
        "Since courier pickup is unavailable, without visiting a physical store, what should I do?",
        "Courier doesn't work here; no need to visit a physical store?",
        "I am going there instead of waiting for a courier, without visiting a physical store.",
        "Instead of waiting for a courier, my friend joked 'walk into a physical store', so can I return it?",
    ],
)
def test_gap1f_property_negating_covered_alternative_never_unlocks(tmp_path: Path, negated_alt_query: str):
    retriever = StaticScopeRetriever({"return_product": ["POL-RET-002", "POL-RET-001"]})
    _assert_pre_llm_escalate(tmp_path, negated_alt_query, retriever)


@pytest.mark.parametrize(
    "multi_quote_query",
    [
        "Support wrongly said 'go to a physical store', instead courier pickup; also a friend told me 'visit a retail store' when returning.",
        "My coworker wrote 'bring it to a physical shop' by mistake, instead how do I book courier pickup? My sibling also asked 'drop off at a physical branch' for my item?",
        "Instead of 'return in store', how do I schedule courier pickup, and why did a banner say 'walk into a physical store' too?",
        "Support suggested 'go to a physical store' by mistake; meanwhile another page says 'return at a local storefront' via the app.",
    ],
)
def test_gap1f_property_multiple_quotes_evaluated_independently(tmp_path: Path, multi_quote_query: str):
    # Invariant: one validly disavowed quote must not leak a waiver to a second un-disavowed quote in the same prompt.
    retriever = StaticScopeRetriever({"return_product": ["POL-RET-002", "POL-RET-001"]})
    _assert_pre_llm_escalate(tmp_path, multi_quote_query, retriever)


@pytest.mark.parametrize(
    "text,intent,doc_ids,ctx",
    [
        (
            "The marketplace seller wrongly told me 'go to a physical store', but I want Tiki courier pickup through the app instead.",
            "return_product",
            ["POL-RET-002", "POL-RET-001"],
            None,
        ),
        (
            "A friend joked 'just walk into a retail store', though I actually plan to drop the box at a designated partner post office.",
            "return_product",
            ["POL-RET-002", "POL-RET-001"],
            None,
        ),
        (
            "Instead of 'return in store', how do I book a courier pickup?",
            "return_product",
            ["POL-RET-002"],
            None,
        ),
        (
            "Where can I click 'My Orders' to track order ORD-1001?",
            "track_order",
            ["POL-ORD-001"],
            RoutingContext(
                ticket_customer_id="demo-customer",
                verified_scope="ticket:read order:read",
                is_personal_lookup=True,
                extracted_slots={"order_id": "ORD-1001"},
            ),
        ),
    ],
)
def test_gap1f_positive_local_rejection_with_exclusive_courier_and_safe_ui_allowed(
    tmp_path: Path, text: str, intent: str, doc_ids: list[str], ctx: RoutingContext | None, fake_llm
):
    _assert_both_allow(tmp_path, text, intent, doc_ids, ctx, fake_llm=fake_llm)
