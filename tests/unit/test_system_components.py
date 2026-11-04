"""Unit tests for Component Probes evaluating routing and semantic retrieval in isolation."""

import json
import pytest
from pathlib import Path
from datetime import datetime, timezone

from pipeline.evaluation.system_contracts import (
    SystemCase,
    SystemCaseContext,
    SystemCaseExpected,
    SystemConfig,
    VerifiedSystemInputs,
)
from pipeline.evaluation.system_execution import (
    build_system_dependencies,
    run_component_probes,
)


@pytest.fixture
def component_probe_inputs(tmp_path):
    # Create KB with 1 approved, 1 expired, 1 wrong_role, 1 unapproved
    kb_data = [
        {
            "doc_id": "KB-ACTIVE-01",
            "title": "Return Policy Valid",
            "version": "1.0",
            "status": "approved",
            "allowed_roles": ["agent", "customer"],
            "valid_from": "2026-01-01T00:00:00Z",
            "valid_to": "2027-01-01T00:00:00Z",
            "approved_by": "qa_reviewer",
            "approved_at": "2026-01-01T00:00:00Z",
            "content": "You can return products within 30 days of purchase for full refund.",
        },
        {
            "doc_id": "KB-EXPIRED-01",
            "title": "Old Expired Policy",
            "version": "1.0",
            "status": "approved",
            "allowed_roles": ["agent", "customer"],
            "valid_from": "2025-01-01T00:00:00Z",
            "valid_to": "2026-01-01T00:00:00Z",  # Expired as of 2026-11-05!
            "approved_by": "qa_reviewer",
            "approved_at": "2025-01-01T00:00:00Z",
            "content": "Expired terms and conditions.",
        },
        {
            "doc_id": "KB-AGENT-ONLY-01",
            "title": "Internal Agent Guide",
            "version": "1.0",
            "status": "approved",
            "allowed_roles": ["agent"],  # Agent only!
            "valid_from": "2026-01-01T00:00:00Z",
            "valid_to": "2027-01-01T00:00:00Z",
            "approved_by": "qa_reviewer",
            "approved_at": "2026-01-01T00:00:00Z",
            "content": "Confidential internal process.",
        },
    ]
    kb_file = tmp_path / "kb.json"
    kb_file.write_text(json.dumps(kb_data), encoding="utf-8")

    cases = [
        # Answerable query
        SystemCase(
            id="comp-ret-01",
            primary_slice="supported",
            text="How many days do I have to return an item?",
            true_intent="return_policy",
            context=SystemCaseContext(ticket_customer_id="cust-1"),
            expected=SystemCaseExpected(
                actions=["retrieve_draft"],
                answerable=True,
                gold_sources=[{"doc_id": "KB-ACTIVE-01", "version": "1.0"}],
            ),
        ),
        # 34 non-core unsupported intent -> must route to escalate with target queue
        SystemCase(
            id="comp-route-uns-01",
            primary_slice="unsupported",
            text="I want to delete my account",
            true_intent="close_account",
            context=SystemCaseContext(ticket_customer_id="cust-2"),
            expected=SystemCaseExpected(
                actions=["escalate"],
                team="account_support",
                must_escalate=True,
            ),
        ),
        # human_agent -> must escalate to general_support
        SystemCase(
            id="comp-route-human-01",
            primary_slice="supported",
            text="Can I talk to a human agent please",
            true_intent="human_agent",
            context=SystemCaseContext(ticket_customer_id="cust-3"),
            expected=SystemCaseExpected(
                actions=["escalate"],
                team="general_support",
                must_escalate=True,
            ),
        ),
        # General policy query without order ID should NOT require order_id slot
        SystemCase(
            id="comp-route-policy-01",
            primary_slice="supported",
            text="What is your return policy?",
            true_intent="return_policy",
            context=SystemCaseContext(ticket_customer_id="cust-4", is_personal_lookup=False),
            expected=SystemCaseExpected(
                actions=["retrieve_draft"],
                answerable=True,
                gold_sources=[{"doc_id": "KB-ACTIVE-01", "version": "1.0"}],
            ),
        ),
    ]

    return VerifiedSystemInputs(
        cases=cases,
        config=SystemConfig(),
        source_paths={"kb": kb_file},
        input_hashes={},
        as_of=datetime(2026, 11, 5, 0, 0, 0, tzinfo=timezone.utc),
        coverage={},
        manifest={"status": "approved"},
    )


def test_run_component_probes_returns_scoped_results(component_probe_inputs, tmp_path):
    """run_component_probes executes both retrieval and routing probes with scope='component'."""
    runtime_dir = tmp_path / "runtime_comp"
    runtime_dir.mkdir()
    deps = build_system_dependencies(component_probe_inputs, profile="mock", runtime_dir=runtime_dir)

    results = run_component_probes(component_probe_inputs, deps)
    assert len(results) == len(component_probe_inputs.cases)
    for r in results:
        assert r.scope == "component"

    # Check routing probe for close_account
    r_uns = next(r for r in results if r.case_id == "comp-route-uns-01")
    assert r_uns.final_action == "escalate"
    assert r_uns.requested_team == "account_support"

    # Check routing probe for human_agent
    r_human = next(r for r in results if r.case_id == "comp-route-human-01")
    assert r_human.final_action == "escalate"
    assert r_human.requested_team == "general_support"

    # Check general policy query does not block on missing order_id
    r_pol = next(r for r in results if r.case_id == "comp-route-policy-01")
    assert r_pol.routing_action in ("retrieve_draft", "escalate")
    assert "missing_order_id" not in r_pol.reason_codes

    deps.close()


def test_routing_probe_nan_margin_fails_closed(component_probe_inputs, tmp_path):
    """NaN or infinite prediction margin fails closed to manual_fallback."""
    from apps.core_backend.intent.routing import decide_route
    from apps.core_backend.intent.schemas import IntentPrediction, RoutingContext

    pred = IntentPrediction(
        intent="track_order",
        confidence=0.95,
        margin=float("nan"),
        model_version="v1.0",
    )
    ctx = RoutingContext(ticket_customer_id="cust-1")
    runtime_dir = tmp_path / "runtime_nan"
    runtime_dir.mkdir()
    deps = build_system_dependencies(component_probe_inputs, profile="mock", runtime_dir=runtime_dir)

    decision = decide_route(pred, ctx, deps.runner.policy)
    assert decision.action == "manual_fallback"
    assert "invalid_model_output" in decision.reason_codes
    deps.close()


def test_routing_probe_unapproved_policy_fails_closed(component_probe_inputs, tmp_path):
    """Unapproved policy fails closed to manual_fallback."""
    from apps.core_backend.intent.routing import decide_route
    from apps.core_backend.intent.schemas import IntentPrediction, RoutingContext

    pred = IntentPrediction(
        intent="return_policy",
        confidence=0.95,
        margin=0.20,
        model_version="v1.0",
    )
    ctx = RoutingContext(ticket_customer_id="cust-1")
    runtime_dir = tmp_path / "runtime_unapp"
    runtime_dir.mkdir()
    deps = build_system_dependencies(component_probe_inputs, profile="mock", runtime_dir=runtime_dir)

    # Force policy unapproved
    deps.runner.policy.approved = False
    decision = decide_route(pred, ctx, deps.runner.policy)
    assert decision.action == "manual_fallback"
    assert "policy_not_approved" in decision.reason_codes
    deps.close()

