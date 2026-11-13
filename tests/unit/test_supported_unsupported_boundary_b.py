"""Boundary diagnostics: supported track_order/return_policy vs unsupported order_history/return_product_in_store.

Uses synthetic predictions only (no weights, no benchmark strings): the question is which runtime layer
can stop a confident-enough near-neighbour mistake. See docs/audits/2026-11-13-boundary-diagnosis-b.md.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from apps.ai_service.engine import Engine
from apps.core_backend.intent.routing import ESCALATED_34_INTENTS, decide_route
from apps.core_backend.intent.schemas import IntentPolicy, IntentPrediction, RoutingContext
from apps.core_backend.safety import evaluate_text_safety

POLICY = json.loads(
    (Path(__file__).resolve().parents[2] / "apps/core_backend/config/policies/intent_policy.v2.json").read_text("utf-8")
)
NEIGHBOUR_UNSUPPORTED = ["order_history", "return_product_in_store", "exchange_product_in_store", "return_product_online"]


class _Model:
    def __init__(self, intent, confidence, margin=0.5):
        self._p = {"intent": intent, "confidence": confidence, "margin": margin, "verified": True,
                   "top_k": [{"intent": intent, "probability": confidence}], "score_kind": "calibrated_probability"}

    def predict(self, message):
        return dict(self._p)


class _Retriever:
    relevance_threshold = 0.55
    eligible_versions = [SimpleNamespace(doc_id="D", version="1", metadata=SimpleNamespace(valid_from="2025-01-01", valid_to=None))]

    def retrieve(self, query, intent, **kw):
        ev = [{"document_id": "D", "version": "1", "title": "Policy", "excerpt": "Returns within 30 days.", "score": 0.9}]
        return {"evidence": ev, "has_conflict": False, "reason_codes": []}


class _NoLLM:
    def generate(self, *a, **k):
        raise AssertionError("LLM must not be reached")


def _engine_rec(intent, conf, message="Can you help with this?"):
    eng = Engine(model=_Model(intent, conf), retriever=_Retriever(), llm=_NoLLM(), versions={}, policy=POLICY)
    req = {"message": message, "as_of": datetime(2026, 6, 1, tzinfo=timezone.utc).isoformat(), "order_context": {}}
    return eng.analyse(req)["routing"]


def _bare(intent, conf, slots=None):
    pred = IntentPrediction(intent=intent, confidence=conf, margin=0.5, model_version="t")
    ctx = RoutingContext(ticket_customer_id="c1", extracted_slots=slots or {})
    return decide_route(pred, ctx, IntentPolicy.model_validate(POLICY))


@pytest.mark.parametrize("conf", [0.651, 0.664, 0.80, 0.99])
def test_bare_route_blocks_neighbour_track_order_only_via_slot_guard(conf):
    # Just above the 0.65 threshold the confidence gate passes; the missing-order-id slot is the only barrier.
    assert POLICY["confidence_thresholds"]["track_order"] == 0.65
    dec = _bare("track_order", conf)
    assert (dec.action, dec.reason_codes) == ("clarify", ["missing_order_id"])
    assert _bare("track_order", conf, {"order_id": "ORD-1"}).action == "retrieve_draft"


def test_bare_route_has_no_barrier_for_return_policy_neighbour_above_threshold():
    # Characterization: no slot, no text net, no rejector -> confidence alone decides. Model must supply the rejection.
    assert _bare("return_policy", 0.60).action == "clarify"
    assert _bare("return_policy", 0.68).action == "retrieve_draft"


@pytest.mark.parametrize("intent", NEIGHBOUR_UNSUPPORTED)
@pytest.mark.parametrize("conf", [0.2, 0.66, 0.99])
def test_negative_control_recognised_unsupported_never_reaches_draft(intent, conf):
    assert intent in ESCALATED_34_INTENTS
    assert _bare(intent, conf).action == "escalate"
    assert _engine_rec(intent, conf)["recommendation"] == "escalate"


def test_engine_has_no_slot_guard_parity_with_decide_route():
    # Engine is the exposed surface (apps/backend -> ai_service). Characterization of the reachable leak:
    # same track_order prediction that decide_route clarifies on (missing_order_id) is drafted here.
    assert _bare("track_order", 0.664).action == "clarify"
    assert _engine_rec("track_order", 0.664)["recommendation"] == "draft"


@pytest.mark.xfail(strict=True, reason="proposed shared guard: Engine must apply decide_route's order_id slot gate")
def test_engine_should_not_draft_track_order_without_order_id():
    assert _engine_rec("track_order", 0.664)["recommendation"] != "draft"


@pytest.mark.parametrize("text", [
    "Where is my parcel right now?",
    "How many days do I have to send an item back?",
    "Can customers return goods bought on the website?",
])
def test_negative_control_supported_paraphrases_not_blocked_by_text_safety(text):
    assert evaluate_text_safety(text)["action"] is None


@pytest.mark.parametrize("text, blocked", [
    ("Can I bring my online order back to one of your shops?", False),   # no lexical net for in-store returns
    ("Could I show my full purchase record for the last two years?", False),  # none for order history either
    ("Please arrange a postal pickup for my return parcel", True),       # only postal pickup has a pattern
])
def test_lexical_safety_covers_only_postal_pickup_boundary(text, blocked):
    assert evaluate_text_safety(text)["outside_product_scope"] is blocked

