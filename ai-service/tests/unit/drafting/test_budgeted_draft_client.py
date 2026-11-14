import pytest
from apps.core_backend.llm.gemini import LLMError


def test_timeout_retries_with_remaining_budget():
    from apps.ai_service.drafting import BudgetedDraftClient
    # Default 5.0s attempt cap: fake clock advances from 0 to 5.0s during attempt 0, leaving 5.0s for attempt 1
    times = iter([0.0, 0.0, 5.0])
    class Client:
        attempts = []
        def generate(self, *args, timeout_seconds=None, **kwargs):
            self.attempts.append(timeout_seconds)
            if len(self.attempts) == 1:
                raise LLMError('llm_timeout')
            return {'body': 'A real response'}
    client = Client()
    result = BudgetedDraftClient(client, clock=lambda: next(times)).generate('question', 'intent', [])
    assert result['body'] == 'A real response'
    assert client.attempts == [5.0, 5.0]


def test_custom_attempt_timeout_with_remaining_budget():
    from apps.ai_service.drafting import BudgetedDraftClient
    # Configured 7.0s attempt cap: fake clock advances from 0 to 5.5s during attempt 0, leaving 4.5s for attempt 1
    times = iter([0.0, 0.0, 5.5])
    class Client:
        attempts = []
        def generate(self, *args, timeout_seconds=None, **kwargs):
            self.attempts.append(timeout_seconds)
            if len(self.attempts) == 1:
                raise LLMError('llm_timeout')
            return {'body': 'A real response'}
    client = Client()
    result = BudgetedDraftClient(client, clock=lambda: next(times), attempt_timeout_seconds=7.0).generate('question', 'intent', [])
    assert result['body'] == 'A real response'
    assert client.attempts == [7.0, 4.5]


def test_permanent_errors_are_not_retried():
    from apps.ai_service.drafting import BudgetedDraftClient
    class Client:
        def generate(self,*args,**kwargs): raise LLMError('llm_auth_error')
    with pytest.raises(LLMError,match='llm_auth_error'):
        BudgetedDraftClient(Client()).generate('question','intent',[])
