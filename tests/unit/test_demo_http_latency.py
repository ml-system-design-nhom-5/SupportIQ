from types import SimpleNamespace
from datetime import datetime, timezone
from unittest.mock import MagicMock

import httpx
import pytest

from pipeline.evaluation.system_contracts import SystemCase


def case():
    return SystemCase.model_validate({
        'id': 'http-return', 'primary_slice': 'supported', 'text': 'return policy',
        'true_intent': 'return_policy', 'context': {'ticket_customer_id': 'demo-customer'},
        'expected': {'actions': ['retrieve_draft']},
    })


def test_http_measurement_posts_to_demo_and_keeps_middleware_response():
    from pipeline.evaluation.system_performance import execute_demo_http_case
    def handler(request):
        assert request.url.path == '/api/demo/runs'
        import json
        payload = json.loads(request.content)
        assert payload['submission_id'] == 'lat-unique'
        assert payload['profile_id'] == 'demo-customer'
        assert 'verified_scope' not in payload
        return httpx.Response(200, json={'run_id': 'lat-unique', 'action': 'retrieve_draft',
            'predicted_intent': 'return_policy', 'draft_body': 'Draft [S1]', 'sources': [], 'llm_called': True})
    deps = SimpleNamespace(profile='live', deadline_seconds=30, managed_server=SimpleNamespace(base_url='http://127.0.0.1:1234'))
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = execute_demo_http_case(case(), deps, 'lat-unique', client)
    assert result.stage_elapsed_ms['api_total'] > 0
    assert result.final_action == 'retrieve_draft'
    assert result.draft_hash
    assert result.llm_called is True


def test_fast_http_failures_do_not_pass_latency_acceptance():
    from pipeline.evaluation.complete_system_report import summarize_http_results
    from pipeline.evaluation.system_contracts import CaseResult
    rows = [CaseResult(case_id=str(i), profile='live', scope='e2e',
            execution_status='error', total_elapsed_ms=1) for i in range(100)]
    result = summarize_http_results(rows, warmup_count=5, expected_count=100)
    assert result['p95_seconds'] < 12
    assert result['latency_target_met'] is False


def test_http_timeout_is_recorded_not_dropped():
    from pipeline.evaluation.system_performance import execute_demo_http_case
    def handler(request):
        raise httpx.ReadTimeout('controlled', request=request)
    server = MagicMock(base_url='http://127.0.0.1:1234')
    deps = SimpleNamespace(profile='live', deadline_seconds=30, managed_server=server)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = execute_demo_http_case(case(), deps, 'lat-timeout', client)
    assert result.execution_status == 'timeout'
    assert result.stage_elapsed_ms['api_total'] >= 0
    server.restart.assert_called_once()


def test_unknown_http_profile_is_rejected_before_network():
    from pipeline.evaluation.system_performance import execute_demo_http_case
    from pipeline.evaluation import EvaluationError
    c = case().model_copy(update={'context': case().context.model_copy(update={'ticket_customer_id': 'unknown'})})
    with pytest.raises(EvaluationError, match='profile'):
        execute_demo_http_case(c, SimpleNamespace(), 'x', MagicMock())


def test_ai_preliminary_annotation_is_not_human_evidence():
    from pipeline.evaluation.assess_system import evaluate_claim_annotations
    from pipeline.evaluation import EvaluationError
    with pytest.raises(EvaluationError, match='human'):
        evaluate_claim_annotations([{'case_id': 'a', 'draft_sha256': 'h',
            'reviewer': 'AI assistant', 'reviewer_type': 'ai',
            'claims': [{'claim_id': 'c1', 'verdict': 'supported'}]}], {'a': 'h'})


def test_supplement_rejects_changed_parent_artifacts(tmp_path):
    import json
    from pipeline.evaluation.complete_system_report import verify_parent
    from pipeline.preparation.utils import compute_sha256
    from pipeline.evaluation import EvaluationError
    files = {}
    for name in ['results.jsonl', 'metrics.json', 'config.resolved.json']:
        path = tmp_path / name
        path.write_text('{}', encoding='utf8')
        files[name] = {'path': name, 'sha256': compute_sha256(path)}
    (tmp_path / 'manifest.json').write_text(json.dumps({'status': 'completed', 'files': files}), encoding='utf8')
    assert verify_parent(tmp_path)['status'] == 'completed'
    (tmp_path / 'results.jsonl').write_text('{"changed": true}', encoding='utf8')
    with pytest.raises(EvaluationError, match='checksum'):
        verify_parent(tmp_path)
