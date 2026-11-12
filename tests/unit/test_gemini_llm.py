import json
from types import SimpleNamespace

import httpx
import pytest

from apps.core_backend.llm.gemini import GeminiDraftClient, LLMError
from apps.core_backend.intent.schemas import IntentPrediction, RoutingContext
from apps.core_backend.orchestration.pipeline_runner import PipelineRunner
from apps.core_backend.orchestration.store import PersistentStore


EVIDENCE = [{"document_id": "returns", "version": "1", "title": "Returns",
             "excerpt": "Products may be returned within 30 days in original packaging."}]


def response_payload(answerable=True, answer="Return within 30 days. [S1]", citations=None):
    return {"modelVersion": "gemini-2.5-flash", "usageMetadata": {"promptTokenCount": 100, "candidatesTokenCount": 20},
            "candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps({
                "answerable": answerable, "answer": answer, "citations": ["S1"] if citations is None else citations})}]}}]}


def client_for(handler, key="test-key"):
    return GeminiDraftClient(api_key=key, model="gemini-2.5-flash", http_client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_gemini_grounded_request_has_header_key_and_no_contact_fields():
    def handler(request):
        assert request.url.path.endswith('/gemini-2.5-flash:generateContent')
        assert 'key=' not in str(request.url)
        assert request.headers['x-goog-api-key'] == 'test-key'
        body = json.loads(request.content)
        prompt = body['contents'][0]['parts'][0]['text']
        assert 'person@example.com' not in prompt and '0912345678' not in prompt
        assert 'returns' in prompt and 'original packaging' in prompt
        assert 'SECRET_NAME' not in prompt and 'transaction-secret' not in prompt
        assert body['generationConfig']['responseMimeType'] == 'application/json'
        return httpx.Response(200, json=response_payload())
    result = client_for(handler).generate(
        'Return policy for person@example.com, phone 0912345678', 'return_policy', EVIDENCE,
        business_context={'order_status': 'Delivered', 'customer_name': 'SECRET_NAME', 'transaction_id': 'transaction-secret'})
    assert result['body'].endswith('[S1]')
    assert result['citations'][0]['document_id'] == 'returns'
    assert result['model'] == 'gemini-2.5-flash' and result['usage']['promptTokenCount'] == 100


@pytest.mark.parametrize('payload', [
    response_payload(answer='Invented. [S9]', citations=['S9']),
    response_payload(answer='No citation', citations=[]),
    {"candidates": [{"finishReason": "MAX_TOKENS", "content": {"parts": [{"text": '{}'}]}}]},
    {"promptFeedback": {"blockReason": "SAFETY"}},
    response_payload(answerable='yes'),
])
def test_invalid_or_blocked_generation_is_not_published(payload):
    with pytest.raises(LLMError):
        client_for(lambda r: httpx.Response(200, json=payload)).generate('return policy', 'return_policy', EVIDENCE)


@pytest.mark.parametrize('status,reason', [(400,'llm_request_rejected'),(403,'llm_auth_error'),(429,'llm_rate_limited'),(503,'llm_unavailable')])
def test_provider_errors_are_sanitized_and_not_retried(status, reason):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(status, json={'error': {'message': 'private provider secret'}})
    with pytest.raises(LLMError) as caught:
        client_for(handler).generate('return policy', 'return_policy', EVIDENCE)
    assert caught.value.code == reason and len(calls) == 1
    assert 'private' not in str(caught.value)


def test_missing_key_or_evidence_never_calls_provider():
    def handler(request):
        pytest.fail('must not call external provider')
    with pytest.raises(LLMError, match='llm_not_configured'):
        client_for(handler, key='').generate('question','return_policy',EVIDENCE)
    with pytest.raises(LLMError, match='llm_no_evidence'):
        client_for(handler).generate('question','return_policy',[])


def test_timeout_is_typed_and_sanitized():
    def handler(request):
        raise httpx.ReadTimeout('secret', request=request)
    with pytest.raises(LLMError, match='llm_timeout'):
        client_for(handler).generate('q','return_policy',EVIDENCE)


def test_provider_timeout_can_be_configured_server_side(monkeypatch):
    monkeypatch.setenv('GEMINI_TIMEOUT_SECONDS','15')
    def handler(request):
        assert request.extensions['timeout']['read']==15.0
        return httpx.Response(200,json=response_payload())
    client_for(handler).generate('q','return_policy',EVIDENCE)


def test_provider_abstention_is_not_a_draft():
    with pytest.raises(LLMError, match='llm_insufficient_evidence'):
        client_for(lambda r: httpx.Response(200,json=response_payload(False,'',[]))).generate('q','return_policy',EVIDENCE)


def test_gemini3_uses_thinking_level_instead_of_budget():
    def handler(request):
        config=json.loads(request.content)['generationConfig']
        assert config['thinkingConfig']=={'thinkingLevel':'minimal'}
        assert 'temperature' not in config
        return httpx.Response(200,json=response_payload())
    client=client_for(handler)
    client.model='gemini-3.1-flash-lite'
    assert client.generate('q','return_policy',EVIDENCE)['model']=='gemini-3.1-flash-lite'


def test_order_dates_are_not_redacted_as_phone_numbers():
    def handler(request):
        prompt=json.loads(request.content)['contents'][0]['parts'][0]['text']
        facts=json.loads(prompt)['order_facts']
        assert facts['delivery_date']=='2026-11-04'
        return httpx.Response(200,json=response_payload())
    client_for(handler).generate('q','return_policy',EVIDENCE,business_context={'delivery_date':'2026-11-04'})


@pytest.mark.parametrize('payload', [[], None, 'bad', {'candidates': []}, {'candidates':[None]},
    {'candidates':[{'finishReason':'STOP','content':{'parts':[None]}}]},
    {**response_payload(),'usageMetadata':None}])
def test_malformed_provider_envelope_fails_closed(payload):
    with pytest.raises(LLMError, match='llm_invalid_response'):
        client_for(lambda r: httpx.Response(200,json=payload)).generate('q','return_policy',EVIDENCE)


def test_runner_persists_llm_draft_and_does_not_regenerate_on_retry(tmp_path):
    calls=[]
    def handler(request):
        calls.append(request)
        return httpx.Response(200,json=response_payload())
    runner=PipelineRunner(
        intent_client=SimpleNamespace(classify_intent=lambda *a,**k: IntentPrediction(intent='return_policy',confidence=.99,margin=.9,model_version='v1.0.0')),
        retrieval_adapter=SimpleNamespace(retrieve=lambda *a,**k: {'status':'success','evidence':EVIDENCE}),
        llm_client=client_for(handler), store=PersistentStore(str(tmp_path/'runs.sqlite3')))
    context=RoutingContext(ticket_customer_id='demo-customer')
    result=runner.run('return policy',context,run_id='run-llm')
    assert result['action']=='retrieve_draft' and result['draft_kind']=='llm'
    assert result['llm_called'] and result['llm']['model']=='gemini-2.5-flash'
    assert result['must_human_approve'] and not result['can_execute_transaction']
    assert runner.run('return policy',context,run_id='run-llm')['is_duplicate_run']
    assert len(calls)==1


@pytest.mark.parametrize('no_evidence', [False, True])
def test_runner_never_falls_back_to_template_on_llm_failure(tmp_path, no_evidence):
    calls=[]
    def handler(request):
        calls.append(request)
        raise httpx.ReadTimeout('timeout',request=request)
    runner=PipelineRunner(
        intent_client=SimpleNamespace(classify_intent=lambda *a,**k: IntentPrediction(intent='return_policy',confidence=.99,margin=.9,model_version='v1.0.0')),
        retrieval_adapter=SimpleNamespace(retrieve=lambda *a,**k: {'status':'success','evidence':[] if no_evidence else EVIDENCE}),
        llm_client=client_for(handler), store=PersistentStore(str(tmp_path/'runs.sqlite3')))
    result=runner.run('return policy',RoutingContext(ticket_customer_id='demo-customer'))
    assert result['draft_body'] is None and result['draft_kind'] is None
    assert result['action'] in {'escalate','manual_fallback'}
    assert len(calls)==(0 if no_evidence else 1)
