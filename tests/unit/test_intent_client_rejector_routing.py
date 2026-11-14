"""Focused regression tests for MockTransport -> IntentClient -> IntentPrediction -> decide_route."""

import math
import httpx
import pytest
from pydantic import ValidationError

from apps.core_backend.intent.client import IntentClient
from apps.core_backend.intent.routing import decide_route, load_policy_v2
from apps.core_backend.intent.schemas import IntentPrediction, RoutingContext


def _make_client(payload_or_fn, expected_model_version: str = "v1.0.0") -> IntentClient:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/predict"
        if callable(payload_or_fn):
            return payload_or_fn(request)
        return httpx.Response(200, json=payload_or_fn)

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    return IntentClient(
        base_url="http://127.0.0.1:8001",
        expected_model_version=expected_model_version,
        http_client=http_client,
    )


def test_http_absent_rejector_fields_preserve_default_routing():
    client = _make_client({
        "intent": "return_policy",
        "confidence": 0.95,
        "margin": 0.80,
        "model_version": "v1.0.0",
    })
    try:
        pred = client.classify_intent("What is your return policy?", request_id="req-absent-1")
    finally:
        client.close()

    assert pred.error is None
    assert pred.score_kind == "uncalibrated_softmax"
    assert pred.selective_accepted is None
    assert pred.rejected_by_experimental_adapter is None
    assert pred.rejector_decision is None
    assert pred.raw_confidence is None
    assert pred.calibration_temperature is None

    policy = load_policy_v2()
    ctx = RoutingContext(verified_scope="ticket:read", ticket_customer_id="cust_1")
    decision = decide_route(pred, ctx, policy)
    assert decision.action == "retrieve_draft"
    assert decision.final_intent == "return_policy"
    assert decision.target_queue == "standard"
    assert decision.reason_codes == []


def test_http_retains_raw_calibration_and_accepted_rejector_metadata_with_immutable_probs():
    payload = {
        "request_id": "req-acc-1",
        "intent": "return_policy",
        "confidence": 0.92,
        "margin": 0.85,
        "top_k": [
            {"intent": "return_policy", "probability": 0.92},
            {"intent": "refund_policy", "probability": 0.07},
        ],
        "score_kind": "calibrated_probability",
        "model_version": "v1.0.0",
        "model_checksum": "mdl-sha256",
        "tokenizer_checksum": "tok-sha256",
        "model_mode": "trained",
        "verified": True,
        "raw_confidence": 0.96,
        "raw_margin": 0.91,
        "raw_score_kind": "uncalibrated_softmax",
        "calibration_temperature": 1.45,
        "calibration_schema_version": "selective_calibration.v1",
        "calibration_checksum": "cal-sha256",
        "selective_accepted": True,
        "selective_score": 0.88,
        "selective_threshold": 0.50,
        "rejected_by_experimental_adapter": False,
        "rejector_decision": "accept",
    }
    client = _make_client(payload)
    try:
        pred = client.classify_intent("What is your return policy?", request_id="req-acc-1")
    finally:
        client.close()

    assert pred.error is None
    assert pred.request_id == "req-acc-1"
    assert pred.model_checksum == "mdl-sha256"
    assert pred.tokenizer_checksum == "tok-sha256"
    assert pred.model_mode == "trained"
    assert pred.verified is True
    assert pred.score_kind == "calibrated_probability"
    assert pred.raw_confidence == pytest.approx(0.96)
    assert pred.raw_margin == pytest.approx(0.91)
    assert pred.raw_score_kind == "uncalibrated_softmax"
    assert pred.calibration_temperature == pytest.approx(1.45)
    assert pred.calibration_schema_version == "selective_calibration.v1"
    assert pred.calibration_checksum == "cal-sha256"
    assert pred.selective_accepted is True
    assert pred.selective_score == pytest.approx(0.88)
    assert pred.selective_threshold == pytest.approx(0.50)
    assert pred.rejected_by_experimental_adapter is False
    assert pred.rejector_decision == "accept"

    policy = load_policy_v2()
    ctx = RoutingContext(verified_scope="ticket:read", ticket_customer_id="cust_1")
    decision = decide_route(pred, ctx, policy)
    assert decision.action == "retrieve_draft"
    assert pred.confidence == pytest.approx(0.92)
    assert pred.margin == pytest.approx(0.85)
    assert pred.raw_confidence == pytest.approx(0.96)
    assert pred.raw_margin == pytest.approx(0.91)
    assert pred.selective_score == pytest.approx(0.88)


def test_accepted_rejector_never_bypasses_existing_gates():
    policy = load_policy_v2()
    base = {
        "intent": "track_order",
        "confidence": 0.95,
        "margin": 0.80,
        "model_version": "v1.0.0",
        "selective_accepted": True,
        "rejected_by_experimental_adapter": False,
    }

    # 1. Low confidence still clarifies
    low_client = _make_client({**base, "confidence": 0.40, "margin": 0.05})
    try:
        low_pred = low_client.classify_intent("Where is my order?")
    finally:
        low_client.close()
    dec_low = decide_route(low_pred, RoutingContext(ticket_customer_id="c1"), policy)
    assert dec_low.action == "clarify"
    assert "low_confidence" in dec_low.reason_codes

    # 2. Missing order_id slot still clarifies
    slot_client = _make_client(base)
    try:
        slot_pred = slot_client.classify_intent("Where is my order?")
    finally:
        slot_client.close()
    dec_slot = decide_route(
        slot_pred,
        RoutingContext(ticket_customer_id="c1", is_personal_lookup=True, extracted_slots={}),
        policy,
    )
    assert dec_slot.action == "clarify"
    assert dec_slot.reason_codes == ["missing_order_id"]

    # 3. Unapproved policy still fails closed to manual_fallback
    unapproved = policy.model_copy(update={"approved": False})
    dec_unapproved = decide_route(
        slot_pred,
        RoutingContext(ticket_customer_id="c1", extracted_slots={"order_id": "ORD-1"}),
        unapproved,
    )
    assert dec_unapproved.action == "manual_fallback"
    assert dec_unapproved.reason_codes == ["policy_not_approved"]

    # 4. Sensitive intent retains manager authority queue
    sens_client = _make_client({**base, "intent": "request_refund"})
    try:
        sens_pred = sens_client.classify_intent("Refund my order")
    finally:
        sens_client.close()
    dec_sens = decide_route(
        sens_pred,
        RoutingContext(ticket_customer_id="c1", extracted_slots={"order_id": "ORD-1"}),
        policy,
    )
    assert dec_sens.action == "retrieve_draft"
    assert dec_sens.target_queue == "manager"
    assert "requires_authority" in dec_sens.reason_codes
    assert dec_sens.must_human_approve is True
    assert dec_sens.can_execute_transaction is False


@pytest.mark.parametrize(
    "reject_fields",
    [
        {"selective_accepted": False},
        {"rejected_by_experimental_adapter": True},
        {"rejector_decision": "reject"},
        {"rejector_decision": "REJECT"},
        {"selective_accepted": True, "rejected_by_experimental_adapter": True},
    ],
)
def test_http_explicit_rejector_vetoes_before_retrieve_draft(reject_fields):
    payload = {
        "intent": "return_policy",
        "confidence": 0.96,
        "margin": 0.90,
        "model_version": "v1.0.0",
        "score_kind": "calibrated_probability",
        "raw_confidence": 0.98,
        "raw_margin": 0.94,
        "selective_score": 0.12,
        "selective_threshold": 0.50,
        **reject_fields,
    }
    client = _make_client(payload)
    try:
        pred = client.classify_intent("Can I deduct this on my income tax return?")
    finally:
        client.close()

    assert pred.error is None
    policy = load_policy_v2()
    ctx = RoutingContext(verified_scope="ticket:read", ticket_customer_id="cust_1")
    decision = decide_route(pred, ctx, policy)

    assert decision.action == "manual_fallback"
    assert decision.action != "retrieve_draft"
    assert "selective_rejected" in decision.reason_codes
    assert pred.confidence == pytest.approx(0.96)
    assert pred.raw_confidence == pytest.approx(0.98)
    assert pred.selective_score == pytest.approx(0.12)


def test_rejected_sensitive_intent_retains_manager_authority():
    client = _make_client({
        "intent": "request_refund",
        "confidence": 0.95,
        "margin": 0.85,
        "model_version": "v1.0.0",
        "selective_accepted": False,
        "rejected_by_experimental_adapter": True,
    })
    try:
        pred = client.classify_intent("Refund my purchase")
    finally:
        client.close()

    policy = load_policy_v2()
    ctx = RoutingContext(
        verified_scope="ticket:read",
        ticket_customer_id="cust_1",
        extracted_slots={"order_id": "ORD-1"},
    )
    decision = decide_route(pred, ctx, policy)
    assert decision.action == "manual_fallback"
    assert decision.target_queue == "manager"
    assert "selective_rejected" in decision.reason_codes
    assert "requires_authority" in decision.reason_codes


@pytest.mark.parametrize(
    "malformed_fields",
    [
        {"selective_accepted": "false"},
        {"selective_accepted": "true"},
        {"selective_accepted": 1},
        {"selective_accepted": 0},
        {"rejected_by_experimental_adapter": "false"},
        {"rejected_by_experimental_adapter": 0},
        {"verified": "false"},
        {"rejector_decision": "maybe"},
        {"rejector_decision": ""},
        {"rejector_decision": False},
        {"selective_score": 1.2},
        {"selective_score": -0.1},
        {"selective_score": "0.9"},
        {"selective_score": True},
        {"selective_threshold": 1.5},
        {"raw_confidence": -0.05},
        {"raw_margin": 1.5},
        {"calibration_temperature": 0.0},
        {"calibration_temperature": -1.0},
        {"confidence": 1.5},
        {"confidence": True},
        {"margin": "0.5"},
    ],
)
def test_malformed_http_control_fields_fail_closed(malformed_fields):
    payload = {
        "intent": "return_policy",
        "confidence": 0.95,
        "margin": 0.80,
        "model_version": "v1.0.0",
        **malformed_fields,
    }
    client = _make_client(payload)
    try:
        pred = client.classify_intent("What is your return policy?")
    finally:
        client.close()

    assert pred.error is not None
    assert pred.intent == "unknown"
    assert pred.confidence == 0.0

    policy = load_policy_v2()
    ctx = RoutingContext(verified_scope="ticket:read", ticket_customer_id="cust_1")
    decision = decide_route(pred, ctx, policy)
    assert decision.action == "manual_fallback"
    assert decision.reason_codes == ["ml_unavailable"]


def test_non_finite_http_and_model_construct_controls_fail_closed():
    client = _make_client(
        lambda req: httpx.Response(
            200,
            content=b'{"intent": "return_policy", "confidence": 0.95, "margin": 0.8, "model_version": "v1.0.0", "selective_score": NaN}',
            headers={"content-type": "application/json"},
        )
    )
    try:
        pred = client.classify_intent("Return policy?")
    finally:
        client.close()

    assert pred.error is not None
    policy = load_policy_v2()
    dec = decide_route(pred, RoutingContext(ticket_customer_id="cust_1"), policy)
    assert dec.action == "manual_fallback"
    assert dec.reason_codes == ["ml_unavailable"]

    # Direct IntentPrediction validation rejects NaN / malformed bools
    with pytest.raises(ValidationError):
        IntentPrediction(intent="return_policy", confidence=0.95, model_version="v1.0.0", selective_accepted="false")
    with pytest.raises(ValidationError):
        IntentPrediction(intent="return_policy", confidence=0.95, model_version="v1.0.0", selective_score=math.nan)

    # Even if validation were bypassed with model_construct, decide_route still fails closed
    bypassed = IntentPrediction.model_construct(
        intent="return_policy",
        confidence=0.95,
        margin=0.80,
        model_version="v1.0.0",
        selective_accepted="false",
    )
    dec_bypassed = decide_route(bypassed, RoutingContext(ticket_customer_id="cust_1"), policy)
    assert dec_bypassed.action == "manual_fallback"
    assert dec_bypassed.reason_codes == ["invalid_model_output"]


def test_arbitrary_extra_fields_are_not_enabled():
    pred = IntentPrediction(
        intent="return_policy",
        confidence=0.95,
        margin=0.80,
        model_version="v1.0.0",
        arbitrary_extra_gate="bypass",
    )
    assert not hasattr(pred, "arbitrary_extra_gate")
    assert "arbitrary_extra_gate" not in pred.model_dump()

    client = _make_client({
        "intent": "return_policy",
        "confidence": 0.95,
        "margin": 0.80,
        "model_version": "v1.0.0",
        "arbitrary_extra_gate": True,
    })
    try:
        http_pred = client.classify_intent("Return policy?")
    finally:
        client.close()
    assert not hasattr(http_pred, "arbitrary_extra_gate")
    assert "arbitrary_extra_gate" not in http_pred.model_dump()


def test_override_authorization_and_provenance_with_rejector():
    client = _make_client({
        "intent": "return_policy",
        "confidence": 0.95,
        "margin": 0.85,
        "model_version": "v1.0.0",
        "selective_accepted": False,
        "rejected_by_experimental_adapter": True,
    })
    try:
        pred = client.classify_intent("How do I return?")
    finally:
        client.close()

    policy = load_policy_v2()

    # Unauthorized scope cannot bypass rejector veto
    unauth_ctx = RoutingContext(
        verified_scope="ticket:read",
        ticket_customer_id="cust_1",
        intent_override="track_order",
        override_provenance={"actor_id": "user_1", "reason": "force draft"},
        extracted_slots={"order_id": "ORD-1"},
    )
    dec_unauth = decide_route(pred, unauth_ctx, policy)
    assert dec_unauth.action == "manual_fallback"
    assert dec_unauth.final_intent == "return_policy"
    assert "selective_rejected" in dec_unauth.reason_codes

    # Missing provenance cannot bypass rejector veto
    no_prov_ctx = RoutingContext(
        verified_scope="ticket:read intent:override",
        ticket_customer_id="cust_1",
        intent_override="track_order",
        override_provenance={"actor_id": "sup_1"},
        extracted_slots={"order_id": "ORD-1"},
    )
    dec_no_prov = decide_route(pred, no_prov_ctx, policy)
    assert dec_no_prov.action == "manual_fallback"
    assert "selective_rejected" in dec_no_prov.reason_codes

    # Validated staff override applies and preserves downstream slot/authority gates
    auth_ctx = RoutingContext(
        verified_scope="ticket:read intent:override",
        ticket_customer_id="cust_1",
        intent_override="return_policy",
        override_provenance={"actor_id": "sup_1", "reason": "confirmed in-scope return inquiry"},
    )
    dec_auth = decide_route(pred, auth_ctx, policy)
    assert dec_auth.action == "retrieve_draft"
    assert dec_auth.final_intent == "return_policy"


def test_explicit_human_and_outside_scope_precedence_over_rejector():
    policy = load_policy_v2()

    # 1. Explicit human request in context overrides rejector veto and ML error
    rejected_client = _make_client({
        "intent": "return_policy",
        "confidence": 0.95,
        "margin": 0.85,
        "model_version": "v1.0.0",
        "selective_accepted": False,
        "rejected_by_experimental_adapter": True,
    })
    try:
        rejected_pred = rejected_client.classify_intent("Connect me to a human")
    finally:
        rejected_client.close()

    human_ctx = RoutingContext(ticket_customer_id="cust_1", is_explicit_human_request=True)
    dec_human = decide_route(rejected_pred, human_ctx, policy)
    assert dec_human.action == "escalate"
    assert dec_human.requested_team == "general_support"
    assert dec_human.reason_codes == ["explicit_human_request"]

    # Even with malformed control failure in IntentClient, explicit human request escalates
    bad_client = _make_client({
        "intent": "return_policy",
        "confidence": 0.95,
        "model_version": "v1.0.0",
        "selective_accepted": "false",
    })
    try:
        bad_pred = bad_client.classify_intent("Talk to a person")
    finally:
        bad_client.close()
    assert bad_pred.error is not None
    dec_human_err = decide_route(bad_pred, human_ctx, policy)
    assert dec_human_err.action == "escalate"
    assert dec_human_err.requested_team == "general_support"
    assert dec_human_err.reason_codes == ["explicit_human_request"]

    # 2. human_agent intent escalates even if rejector rejected
    human_intent_client = _make_client({
        "intent": "human_agent",
        "confidence": 0.90,
        "margin": 0.70,
        "model_version": "v1.0.0",
        "selective_accepted": False,
    })
    try:
        human_intent_pred = human_intent_client.classify_intent("Speak to agent")
    finally:
        human_intent_client.close()
    dec_human_intent = decide_route(human_intent_pred, RoutingContext(ticket_customer_id="cust_1"), policy)
    assert dec_human_intent.action == "escalate"
    assert dec_human_intent.requested_team == "general_support"
    assert dec_human_intent.reason_codes == ["human_agent_requested"]

    # 3. Outside-scope 34 intent still escalates with recognized_outside_product_scope
    oos_client = _make_client({
        "intent": "close_account",
        "confidence": 0.93,
        "margin": 0.80,
        "model_version": "v1.0.0",
        "selective_accepted": False,
    })
    try:
        oos_pred = oos_client.classify_intent("Delete my account")
    finally:
        oos_client.close()
    dec_oos = decide_route(oos_pred, RoutingContext(ticket_customer_id="cust_1"), policy)
    assert dec_oos.action == "escalate"
    assert dec_oos.requested_team == "account_support"
    assert dec_oos.reason_codes == ["recognized_outside_product_scope"]
