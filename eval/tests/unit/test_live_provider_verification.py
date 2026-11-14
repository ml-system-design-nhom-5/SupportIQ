"""Unit tests for Task C bounded live verification transport cap and sanitization."""
from __future__ import annotations

from pathlib import Path
import sys

import httpx
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pipeline.evaluation.live_provider_verification import (
    ALLOWED_GEMINI_HOST,
    BudgetExhaustedBeforeNetworkError,
    BudgetGuardedTransport,
    MAX_LIVE_HTTP_REQUESTS,
    TARGET_LIVE_CASE_IDS,
    load_private_provider_config,
    sanitize_text,
    select_target_cases,
    summarize_tokens_and_conditional_cost,
)


def test_budget_guarded_transport_blocks_9th_call_and_counts_timeouts():
    inner_calls = 0

    class _FakeInner(httpx.BaseTransport):
        def __init__(self):
            self._retries = 0

        def handle_request(self, request: httpx.Request) -> httpx.Response:
            nonlocal inner_calls
            inner_calls += 1
            if inner_calls % 2 == 0:
                raise httpx.ReadTimeout("simulated read timeout", request=request)
            return httpx.Response(503, json={"error": {"code": 503}})

        def close(self) -> None:
            pass

    guard = BudgetGuardedTransport(max_requests=MAX_LIVE_HTTP_REQUESTS, inner=_FakeInner())
    client = httpx.Client(transport=guard, follow_redirects=False, trust_env=False)
    url = f"https://{ALLOWED_GEMINI_HOST}/v1beta/models/gemini-3.1-flash-lite:generateContent"

    assert guard.requests_attempted == 0
    for i in range(MAX_LIVE_HTTP_REQUESTS):
        if (i + 1) % 2 == 0:
            with pytest.raises(httpx.ReadTimeout):
                client.post(url, json={})
        else:
            resp = client.post(url, json={})
            assert resp.status_code == 503

    assert guard.requests_attempted == 8
    assert inner_calls == 8

    # 9th request must fail BEFORE inner transport is invoked
    with pytest.raises(BudgetExhaustedBeforeNetworkError):
        client.post(url, json={})
    assert inner_calls == 8
    assert guard.requests_attempted == 8
    assert guard.rejected_before_network_count == 1
    assert guard.records[-1]["rejected_before_network"] is True

    # Disallowed host must also be blocked before inner transport
    with pytest.raises(httpx.RequestError):
        client.post("https://example.com/v1/test", json={})
    assert inner_calls == 8
    client.close()


def test_default_transport_disables_hidden_retries_and_sanitizes_secrets(tmp_path):
    guard = BudgetGuardedTransport(max_requests=8)
    assert guard._retries_configured == 0
    guard.close()

    secret = "AIzaSyExampleSyntheticSecret12345"
    scrubbed = sanitize_text(f"Failure sending x-goog-api-key={secret} body={secret}", secret_key=secret)
    assert secret not in scrubbed
    assert "AIza" not in scrubbed

    missing_env = tmp_path / ".env"
    with pytest.raises(FileNotFoundError):
        load_private_provider_config(missing_env)

    empty_env = tmp_path / ".empty.env"
    empty_env.write_text("GEMINI_API_KEY=\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_private_provider_config(empty_env)


def test_target_case_selection_and_incomplete_token_accounting():
    cases = select_target_cases(REPO_ROOT / "data/benchmarks/final_acceptance/cases.jsonl")
    assert tuple(c["id"] for c in cases) == TARGET_LIVE_CASE_IDS
    assert len(cases) == 4

    incomplete = summarize_tokens_and_conditional_cost(
        [
            {"attempts": [{"usage": {}}, {"usage": {"promptTokenCount": 100, "candidatesTokenCount": 50, "totalTokenCount": 150}}]}
        ],
        "gemini-3.1-flash-lite",
    )
    assert incomplete["complete_token_coverage"] is False
    assert incomplete["attempts_missing_usage"] == 1
    assert incomplete["observed_reported_total_tokens"] is None
    assert incomplete["complete_cost_usd"] is None
    assert incomplete["complete_cost_known"] is False
    assert incomplete["cost_status"] == "incomplete_token_coverage"


def test_live_ff0e147_artifact_hashes_budget_and_no_secret_leaks():
    import hashlib
    import json

    live_dir = REPO_ROOT / "artifacts/evaluation/live_ff0e147_oracle_20261113"
    hashes = json.loads((live_dir / "report_hashes.json").read_text(encoding="utf-8"))
    for name, exp_sha in hashes.items():
        actual_sha = hashlib.sha256((live_dir / name).read_bytes()).hexdigest()
        assert actual_sha == exp_sha, f"Hash mismatch for {name}"

    raw_text = (live_dir / "live_verification.json").read_text(encoding="utf-8")
    assert "AIza" not in raw_text
    assert "x-goog-api-key" not in raw_text

    data = json.loads(raw_text)
    assert data["verification_scope"] == "oracle_intent_grounded_provider_component_verification"
    assert data["source_commit"].startswith("ff0e147")
    assert data["preflight"]["preflight_budget"] == "0/8"
    assert data["budget_accounting"]["authorized_max_http_requests"] == 8
    assert data["budget_accounting"]["actual_http_requests_made"] == 8
    assert data["budget_accounting"]["budget_enforced_within_cap"] is True
    assert data["budget_accounting"]["transport_retries_configured"] == 0
    assert len(data["transport_calls"]) == 8
    assert data["summary"]["cases_executed"] == 4
    assert data["summary"]["draft_ready_count"] == 2
    assert data["summary"]["no_auto_send_all"] is True
    assert data["tokens_and_cost"]["complete_token_coverage"] is False
    assert data["tokens_and_cost"]["attempts_missing_usage"] == 6
    assert data["tokens_and_cost"]["observed_reported_total_tokens"] is None
    assert data["tokens_and_cost"]["complete_cost_known"] is False
