import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from pipeline.evaluation import EvaluationError


def test_default_intent_client_actually_reuses_pool():
    from apps.core_backend.intent.client import IntentClient
    with patch('apps.core_backend.intent.client.httpx.Client') as factory:
        factory.return_value.post.return_value.json.return_value = {
            'intent': 'return_policy', 'confidence': .9, 'margin': .8, 'model_version': 'v1.0.0'}
        c = IntentClient()
        with patch('apps.core_backend.intent.client.httpx.post', side_effect=AssertionError('unpooled')):
            assert c.classify_intent('one').error is None
            assert c.classify_intent('two').error is None
        factory.assert_called_once()
        c.close()
        factory.return_value.close.assert_called_once()


def test_human_annotations_require_explicit_actor_time_and_evidence():
    from pipeline.evaluation.assess_system import evaluate_claim_annotations
    a = {'reviewer': 'person', 'case_id': 'x', 'draft_sha256': 'h', 'claims': [{'verdict': 'supported'}]}
    with pytest.raises(EvaluationError):
        evaluate_claim_annotations([a], {'x': 'h'})


@pytest.mark.parametrize('attestation', [True, 'false'])
def test_supported_verdict_casing_cannot_bypass_evidence(attestation):
    from pipeline.evaluation.assess_system import evaluate_claim_annotations
    a = {'reviewer':'person','reviewer_type':'human','reviewed_at':'2026-11-05T00:00:00Z',
         'case_id':'x','draft_sha256':'h','relevance':'fully_answers',
         'attestation':{'all_factual_claims_reviewed':attestation},'claims':[{'verdict':'SUPPORTED'}]}
    with pytest.raises(EvaluationError):
        evaluate_claim_annotations([a], {'x':'h'})


def test_unsigned_candidate_metrics_are_never_verified(tmp_path):
    from pipeline.evaluation.assess_system import import_verified_ml_metrics
    p = tmp_path / 'manifest.json'
    p.write_text(json.dumps({'status': 'candidate', 'model_type': 'unrelated',
                            'metrics': {'macro_f1': .99}}))
    with pytest.raises(EvaluationError):
        import_verified_ml_metrics(p, strict=True)


def test_checksum_bound_cv_import_rejects_report_tampering(tmp_path):
    from pipeline.evaluation.assess_system import import_verified_ml_metrics
    from pipeline.preparation.utils import compute_sha256
    report = tmp_path/'training_report.json'
    report.write_text(json.dumps({'cv_protocol': '10-fold cross-validation', 'cv_n_folds': 10,
        'cv_macro_f1_mean': .9, 'fold_metrics': [{'fold': i, 'macro_f1': .9} for i in range(10)]}))
    release = tmp_path/'release.json'
    release.write_text(json.dumps({'model_id': 'fixture', 'model_type': 'fixture_classifier', 'package_version': 'fixture-v1',
        'artifacts': {'training_report.json': {'path':report.name, 'sha256':compute_sha256(report)}}}))
    descriptor = tmp_path/'cv.json'
    descriptor.write_text(json.dumps({'schema_version':'verified-cv-v1','model_id':'fixture','model_type':'fixture_classifier',
        'package_version':'fixture-v1','release_sha256':compute_sha256(release),
        'cv_report':{'path':report.name,'sha256':compute_sha256(report)}}))
    value = import_verified_ml_metrics(descriptor, expected_model_type='fixture_classifier',
                                     expected_release_path=release, strict=True)
    assert value['status']=='verified' and value['macro_f1']==.9
    report.write_text('{}')
    with pytest.raises(EvaluationError, match='checksum'):
        import_verified_ml_metrics(descriptor, expected_release_path=release, strict=True)


def test_default_runtime_uses_v2_knowledge():
    from apps.core_backend.retrieval.adapter import RetrievalAdapter
    from pipeline.evaluation.system_execution import MockPolicyEncoder
    adapter = RetrievalAdapter(encoder=MockPolicyEncoder())
    assert len(adapter.eligible_versions) > 3


@pytest.mark.skipif(
    not (Path(__file__).resolve().parents[2] / 'data/benchmarks/system/v3/acceptance/cases.jsonl').exists(),
    reason="Draft v3 benchmark suite not generated",
)
def test_acceptance_is_disjoint_from_dev_and_retired_v1():
    root = Path(__file__).resolve().parents[2] / 'data/benchmarks/system'
    def texts(p):
        return {json.loads(s)['text'].casefold().strip() for s in p.read_text(encoding='utf8').splitlines()}
    acceptance = texts(root/'v3/acceptance/cases.jsonl')
    assert acceptance
    assert not acceptance & texts(root/'v3/dev/cases.jsonl')
    assert not acceptance & texts(root/'v1/cases.jsonl')


def test_native_side_effect_cannot_finish_after_isolated_timeout(tmp_path):
    from pipeline.evaluation.isolated_call import IsolatedCaller
    db = tmp_path / 'locked.sqlite3'
    lock = sqlite3.connect(db, isolation_level=None)
    lock.execute('CREATE TABLE effects(value TEXT)')
    lock.execute('BEGIN IMMEDIATE')
    def write_late():
        c = sqlite3.connect(str(db), timeout=3, isolation_level=None)
        try:
            c.execute("INSERT INTO effects VALUES ('late')")
            return 'written'
        finally:
            c.close()
    caller = IsolatedCaller()
    try:
        with pytest.raises(TimeoutError):
            caller.call(write_late, {}, .05)
        lock.commit()
        assert lock.execute('SELECT COUNT(*) FROM effects').fetchone()[0] == 0
        assert not caller.is_running()
    finally:
        caller.close()
        lock.close()


def test_runner_persists_order_sources_and_exact_prompt_snapshot(tmp_path):
    from apps.core_backend.intent.schemas import IntentPrediction, RoutingContext
    from apps.core_backend.llm.gemini import GeminiDraftClient
    from apps.core_backend.orchestration.pipeline_runner import PipelineRunner
    from apps.core_backend.orchestration.store import PersistentStore
    intent = MagicMock()
    intent.classify_intent.return_value = IntentPrediction(intent='return_product', confidence=.99, margin=.8, model_version='v1.0.0')
    commerce = MagicMock()
    commerce.lookup_order.return_value = {'authorized': True, 'order': {'order_id': 'ORD-1001', 'order_status': 'Shipping'}}
    retrieval = MagicMock()
    retrieval.retrieve.return_value = {'status': 'success', 'evidence': [
        {'document_id': 'POL', 'version': '2', 'excerpt': 'Return within 30 days.'}]}
    def response(req):
        return httpx.Response(200, json={'candidates': [{'finishReason': 'STOP', 'content': {'parts': [
            {'text': json.dumps({'answerable': True, 'answer': 'Order is Shipping [S2].', 'citations': ['S2']})}]}}]})
    llm = GeminiDraftClient(api_key='test', http_client=httpx.Client(transport=httpx.MockTransport(response)))
    store = PersistentStore(str(tmp_path/'runs.sqlite3'))
    runner = PipelineRunner(intent_client=intent, commerce_adapter=commerce, retrieval_adapter=retrieval, llm_client=llm, store=store)
    r = runner.run('Return order', RoutingContext(ticket_customer_id='demo-customer', is_personal_lookup=True,
                  extracted_slots={'order_id': 'ORD-1001'}), 'evidence-run')
    saved = store.get_run('evidence-run')
    assert any(s.get('source_type') == 'order_facts' for s in saved['sources'])
    assert saved['llm_input_snapshot']['sha256'] == hashlib.sha256(saved['llm_input_snapshot']['prompt'].encode()).hexdigest()
    assert saved['llm_input_snapshot']['sources'] == r['llm_input_snapshot']['sources']
    llm.close()
