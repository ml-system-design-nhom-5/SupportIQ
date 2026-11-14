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


def test_flash_lite_default_and_explicit_hydrogen_low_thinking_compatibility(monkeypatch):
    from pathlib import Path
    from apps.ai_service.main import AiSettings

    monkeypatch.delenv('GEMINI_MODEL', raising=False)
    monkeypatch.setenv('GEMINI_API_KEY', 'hydrogen-test-key')

    env_example = (Path(__file__).resolve().parents[2] / '.env.example').read_text(encoding='utf-8')
    assert 'GEMINI_MODEL=gemini-3.5-flash-lite' in env_example.splitlines()
    assert AiSettings(_env_file=None).gemini_model == 'gemini-3.5-flash-lite'
    assert GeminiDraftClient(api_key='test-key').model == 'gemini-3.5-flash-lite'

    captured = {}

    def handler(request):
        captured['url'] = str(request.url)
        captured['headers'] = dict(request.headers)
        captured['body'] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                'modelVersion': 'gemini-4-hydrogen',
                'usageMetadata': {
                    'promptTokenCount': 120,
                    'candidatesTokenCount': 24,
                    'thoughtsTokenCount': 9,
                    'totalTokenCount': 153,
                },
                'candidates': [
                    {
                        'finishReason': 'STOP',
                        'content': {
                            'parts': [
                                {'thought': True, 'text': 'internal reasoning should be stripped'},
                                {
                                    'text': json.dumps(
                                        {
                                            'answerable': True,
                                            'is_clarification': False,
                                            'answer': 'Products may be returned within 30 days. [S1]',
                                            'citations': ['S1'],
                                        }
                                    )
                                },
                            ]
                        },
                    }
                ],
            },
        )

    client = GeminiDraftClient(
        model='gemini-4-hydrogen',
        http_client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    assert client.model == 'gemini-4-hydrogen'

    result = client.generate(
        'Return policy for user@example.com or 0912345678',
        'return_policy',
        EVIDENCE,
        timeout_seconds=7.0,
    )

    assert captured['url'].endswith('/v1beta/models/gemini-4-hydrogen:generateContent')
    assert 'key=' not in captured['url']
    assert captured['headers']['x-goog-api-key'] == 'hydrogen-test-key'

    gen_cfg = captured['body']['generationConfig']
    assert gen_cfg['thinkingConfig'] == {'thinkingLevel': 'low'}
    assert 'thinkingBudget' not in gen_cfg['thinkingConfig']
    for sampling_key in ('temperature', 'topP', 'topK', 'top_p', 'top_k'):
        assert sampling_key not in gen_cfg
    assert gen_cfg['maxOutputTokens'] == 1024
    assert gen_cfg['responseMimeType'] == 'application/json'
    assert 'responseSchema' in gen_cfg

    prompt_text = captured['body']['contents'][0]['parts'][0]['text']
    assert 'user@example.com' not in prompt_text and '0912345678' not in prompt_text
    assert 'internal reasoning should be stripped' not in result['body']
    assert result['model'] == 'gemini-4-hydrogen'
    assert result['citations'][0]['document_id'] == 'returns'
    assert result['usage']['thoughtsTokenCount'] == 9


def test_explicit_legacy_gemini25_thinking_budget_and_gemini3_minimal_preserved():
    seen = {}

    def handler(request):
        model_seg = request.url.path.split('/')[-1].split(':')[0]
        seen[model_seg] = json.loads(request.content)['generationConfig']
        return httpx.Response(200, json=response_payload())

    http = httpx.Client(transport=httpx.MockTransport(handler))
    GeminiDraftClient(api_key='k', model='gemini-2.5-flash', http_client=http).generate('q', 'return_policy', EVIDENCE)
    GeminiDraftClient(api_key='k', model='gemini-3.1-flash-lite', http_client=http).generate('q', 'return_policy', EVIDENCE)

    assert seen['gemini-2.5-flash']['thinkingConfig'] == {'thinkingBudget': 0}
    assert seen['gemini-2.5-flash']['temperature'] == 0.1
    assert seen['gemini-3.1-flash-lite']['thinkingConfig'] == {'thinkingLevel': 'minimal'}
    assert 'temperature' not in seen['gemini-3.1-flash-lite']


@pytest.mark.parametrize('answer', [
    'Returns are accepted within 30 days [S1]. Refunds always arrive within 2 hours of approval.',
    'Returns are accepted within 30 days [S1]. Shipping is free.',
    'Returns are accepted within 45 days of receipt [S1].',
    'Good news: your order has been cancelled and refunded [S1].',
    'I have approved and issued your refund [S1].',
    'We will cancel your order right now [S1].',
])
def test_validator_rejects_uncited_claims_unsupported_numbers_and_commitments(answer):
    from apps.core_backend.safety import validate_generated_draft

    sources = [{'source_id': 'S1', 'source_type': 'policy', 'document_id': 'returns', 'version': '1',
                'excerpt': 'Products may be returned within 30 days in original packaging.'}]
    with pytest.raises(LLMError) as caught:
        client_for(lambda r: httpx.Response(200, json=response_payload(answer=answer, citations=['S1']))).generate(
            'What is your return policy?', 'return_policy', EVIDENCE
        )
    assert caught.value.code == 'llm_invalid_citations'

    ok, codes, _ = validate_generated_draft(
        'What is your return policy?',
        {'body': answer, 'citations': ['S1'], 'input_snapshot': {'sources': sources}},
        sources,
    )
    assert (ok, codes) == (False, ['grounding_failed'])


def test_validator_allows_safe_positive_controls_formats_and_quotations():
    import hashlib
    from apps.core_backend.safety import validate_generated_draft

    pol_hotline_content = (
        "In the event a Tiki order exceeds its estimated delivery date without arrival, "
        "or if a courier marks an order as 'Successfully Delivered' when the customer has not received the parcel, "
        "the customer must contact Tiki Customer Support within 24-48 hours via hotline 1900 6035. "
        "Tiki's dispatch team will verify courier GPS logs, coordinate with the delivery hub, and resolve the complaint. "
        "If an order is lost, Tiki will dispatch a replacement or issue a 100% refund."
    )
    rich_evidence = [
        {
            'source_type': 'policy',
            'document_id': 'POL-SHIP-004',
            'version': '1.0',
            'title': 'Handling Delayed, Lost, or Discrepant Delivery Statuses',
            'excerpt': pol_hotline_content,
            'content_hash': hashlib.sha256(pol_hotline_content.encode('utf-8')).hexdigest(),
        },
        {
            'source_type': 'policy',
            'document_id': 'POL-REFUND',
            'version': '1.0',
            'title': 'Refund Window & Currency',
            'excerpt': (
                'Approved refunds are credited within 5 to 7 business days once an order has been canceled. '
                'Orders from 18,000 VND to 1,000,000 VND ship under fee $5.00.'
            ),
        },
    ]
    ctx = {'order_id': 'ORD-1001', 'order_status': 'Shipping', 'delivery_date': '2026-11-04'}
    valid_answers = [
        'Hello!\n\nPlease contact support within 24-48 hours via hotline 1900 6035. [S1]\n\nThank you for contacting support.',
        (
            'Approved refunds are credited within 5-7 business days once an order has been canceled [S2]. '
            'Orders from 18.000 to 1.000.000 VND have fee $5 [S2].'
        ),
        'Your delivery date is 2026-11-04 (November 4, 2026) [S3].',
        (
            'You mentioned that "your order has been cancelled and refunded", '
            'and we have not cancelled your order yet [S1]. '
            'Please call hotline 1900 6035 within 24-48 hours [S1].'
        ),
    ]
    expected_cites = [['S1'], ['S2'], ['S3'], ['S1']]
    for ans, cites in zip(valid_answers, expected_cites):
        res = client_for(lambda r, a=ans, c=cites: httpx.Response(200, json=response_payload(answer=a, citations=c))).generate(
            'Help with my order and refund', 'refund_policy', rich_evidence, business_context=ctx
        )
        ok, codes, _ = validate_generated_draft('Help with my order and refund', res, res['input_snapshot']['sources'])
        assert (ok, codes) == (True, [])

    # Direct validator check when source itself carries dot-grouped Vietnamese currency (1.000.000 VND)
    dot_sources = [{'source_id': 'S1', 'source_type': 'policy', 'document_id': 'POL-SHIP-002', 'version': '1.0',
                    'excerpt': 'Orders above 1.000.000 VND ship free.'}]
    ok_dot, codes_dot, _ = validate_generated_draft(
        'Shipping fee threshold?',
        {'body': 'Orders above 1,000,000 VND ship free [S1].', 'citations': ['S1'], 'input_snapshot': {'sources': dot_sources}},
        dot_sources,
    )
    assert (ok_dot, codes_dot) == (True, [])


@pytest.mark.parametrize('answer', [
    'Thank you for reaching out about your order.\n\nProducts may be returned within 30 days in original packaging [S1].',
    'Products may be returned within 30 days in original packaging [S1].\n\nPlease let us know if you have questions about this policy.',
    'Hello [NAME_1],\n\nThank you for reaching out about your order.\n\nProducts may be returned within 30 days in original packaging [S1].\n\nPlease let us know if you have questions about this policy.',
    'Thank you for contacting us regarding your return request.\n\nProducts may be returned within 30 days in original packaging [S1].\n\nPlease feel free to reach out if you have any questions about our return policy.',
    'Thank you for reaching out about your refund.\n\nProducts may be returned within 30 days in original packaging [S1].',
    'Thank you for reaching out about your order. Products may be returned within 30 days in original packaging [S1]. Please let us know if you have questions about this policy.',
])
def test_validator_allows_narrow_nonfactual_polite_framing_around_cited_policy(answer):
    from apps.core_backend.safety import validate_generated_draft

    question = 'Hello [NAME_1], what is your return policy?'
    res = client_for(lambda r: httpx.Response(200, json=response_payload(answer=answer, citations=['S1']))).generate(
        question, 'return_policy', EVIDENCE
    )
    ok, codes, _ = validate_generated_draft(question, res, res['input_snapshot']['sources'])
    assert (ok, codes) == (True, [])


@pytest.mark.parametrize('answer', [
    'Thank you, your refund is approved.\n\nProducts may be returned within 30 days in original packaging [S1].',
    'Please know shipping is free.\n\nProducts may be returned within 30 days in original packaging [S1].',
    'We apologize, your order will arrive tomorrow.\n\nProducts may be returned within 30 days in original packaging [S1].',
    'Products may be returned within 30 days in original packaging [S1].\n\nLet us know after 5 days.',
    'Products may be returned within 30 days in original packaging [S1].\n\nLet us know after five days.',
    'Hello, I promise you will get money back.\n\nProducts may be returned within 30 days in original packaging [S1].',
    'Hello, your order ships free.\n\nProducts may be returned within 30 days in original packaging [S1].',
    'Thank you for reaching out about your order.\nYour refund is approved.\n\nProducts may be returned within 30 days in original packaging [S1].',
    'Thank you for reaching out about your order; shipping is free.\n\nProducts may be returned within 30 days in original packaging [S1].',
    'Products may be returned within 30 days in original packaging [S1]; Shipping is free.',
    'Shipping is free; Products may be returned within 30 days in original packaging [S1].',
    'Products may be returned within 30 days in original packaging [S1].Shipping is free.',
    'Thank you for reaching out about your order.your refund is approved.\n\nProducts may be returned within 30 days in original packaging [S1].',
    'Please let us know if you have questions about our $5 fee.\n\nProducts may be returned within 30 days in original packaging [S1].',
    'Thank you for reaching out about your order.\n\nPlease let us know if you have questions about this policy.',
])
def test_validator_rejects_adversarial_polite_framing_and_multiline_bypasses(answer):
    from apps.core_backend.safety import validate_generated_draft

    sources = [{'source_id': 'S1', 'source_type': 'policy', 'document_id': 'returns', 'version': '1',
                'excerpt': 'Products may be returned within 30 days in original packaging.'}]
    has_cite = '[S1]' in answer
    cites = ['S1'] if has_cite else []
    with pytest.raises(LLMError) as caught:
        client_for(lambda r: httpx.Response(200, json=response_payload(answer=answer, citations=cites))).generate(
            'What is your return policy?', 'return_policy', EVIDENCE
        )
    assert caught.value.code == 'llm_invalid_citations'

    ok, codes, _ = validate_generated_draft(
        'What is your return policy?',
        {'body': answer, 'citations': cites, 'input_snapshot': {'sources': sources}},
        sources,
    )
    assert (ok, codes) == (False, ['grounding_failed'])


@pytest.mark.parametrize('answer', [
    'Your order is cancelled [S1].',
    'Your refund is approved [S1].',
    'Your return is approved [S1].',
    'Your refund is refunded [S1].',
    'Your return is processed [S1].',
    'Your order is credited [S1].',
    'Shipping is free.Products may be returned within 30 days in original packaging [S1].',
    'Shipping is free.products may be returned within 30 days in original packaging [S1].',
    'Products may be returned within 30 days in original packaging [S1].Shipping is free.',
    'Products may be returned within 30 days in original packaging [S1], shipping is free.',
    'Shipping is free, products may be returned within 30 days in original packaging [S1].',
    'Shipping is free: products may be returned within 30 days in original packaging [S1].',
    'Products may be returned within 30 days in original packaging - shipping is free [S1].',
    'Products may be returned within 30 days in original packaging (shipping is free) [S1].',
])
def test_validator_rejects_bare_passive_status_missing_space_periods_and_clause_splices(answer):
    from apps.core_backend.safety import validate_generated_draft

    sources = [{'source_id': 'S1', 'source_type': 'policy', 'document_id': 'returns', 'version': '1',
                'excerpt': 'Products may be returned within 30 days in original packaging.'}]
    with pytest.raises(LLMError) as caught:
        client_for(lambda r: httpx.Response(200, json=response_payload(answer=answer, citations=['S1']))).generate(
            'What is your return policy?', 'return_policy', EVIDENCE
        )
    assert caught.value.code == 'llm_invalid_citations'

    ok, codes, _ = validate_generated_draft(
        'What is your return policy?',
        {'body': answer, 'citations': ['S1'], 'input_snapshot': {'sources': sources}},
        sources,
    )
    assert (ok, codes) == (False, ['grounding_failed'])


def test_validator_passive_status_strict_against_order_facts_and_allows_verified_and_plural_policy():
    from apps.core_backend.safety import validate_generated_draft

    pol_and_mismatched_order = [
        {'source_id': 'S1', 'source_type': 'policy', 'document_id': 'POL-RET-001', 'version': '1.0',
         'title': 'Returns Policy', 'excerpt': 'Refunds are approved after inspection and returned within 30 days.'},
        {'source_id': 'S2', 'source_type': 'order_facts', 'document_id': 'ORDER-FACTS', 'version': 'facts',
         'excerpt': 'Verified Order Details:\norder_status: delivered\nrefund_status: pending\nreturn_status: requested'},
    ]
    for bad in (
        'Your order is cancelled [S2].',
        'Your refund is approved [S2].',
        'Your return is approved [S2].',
        'Your refund is refunded [S2].',
        'Your return is processed [S2].',
        'Your order is credited [S2].',
    ):
        ok, codes, _ = validate_generated_draft(
            'Check my order',
            {'body': bad, 'citations': ['S2'], 'input_snapshot': {'sources': pol_and_mismatched_order}},
            pol_and_mismatched_order,
        )
        assert (ok, codes) == (False, ['grounding_failed']), bad

    for good_policy in (
        'Refunds are approved after inspection [S1].',
        'Returns Policy: Refunds are approved after inspection [S1].',
        'Thank you for reaching out, refunds are approved after inspection [S1].',
        'Once an order has been returned, refunds are approved after inspection [S1].',
    ):
        ok, codes, _ = validate_generated_draft(
            'Refund policy?',
            {'body': good_policy, 'citations': ['S1'], 'input_snapshot': {'sources': pol_and_mismatched_order}},
            pol_and_mismatched_order,
        )
        assert (ok, codes) == (True, []), good_policy

    verified_order = [
        {'source_id': 'S2', 'source_type': 'order_facts', 'document_id': 'ORDER-FACTS', 'version': 'facts',
         'excerpt': 'Verified Order Details:\norder_status: Cancelled\nrefund_status: Refunded\nreturn_status: approved'},
        {'source_id': 'S3', 'source_type': 'order_facts', 'document_id': 'ORDER-FACTS', 'version': 'facts',
         'excerpt': 'Verified Order Details:\nrefund_status: approved\nreturn_status: processed'},
    ]
    for cite, good_order in (
        ('S2', 'Your order is cancelled [S2].'),
        ('S2', 'Your refund is refunded [S2].'),
        ('S2', 'Your return is approved [S2].'),
        ('S3', 'Your refund is approved [S3].'),
        ('S3', 'Your return is processed [S3].'),
    ):
        ok, codes, _ = validate_generated_draft(
            'Order status?',
            {'body': good_order, 'citations': [cite], 'input_snapshot': {'sources': verified_order}},
            verified_order,
        )
        assert (ok, codes) == (True, []), good_order
