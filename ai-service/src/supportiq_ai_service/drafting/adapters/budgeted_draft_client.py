"""Retry transient provider failures once inside the existing ten-second LLM budget."""
import time
from apps.core_backend.llm.gemini import LLMError


class BudgetedDraftClient:
    def __init__(self, client, clock=time.monotonic):
        self.client, self.clock = client, clock

    def generate(self, *args, **kwargs):
        deadline = self.clock() + 10
        for attempt in range(2):
            remaining = deadline - self.clock()
            if remaining <= 0:
                raise LLMError('llm_timeout')
            try:
                return self.client.generate(*args, **kwargs, timeout_seconds=min(5,remaining))
            except LLMError as error:
                if attempt or error.code not in ('llm_timeout','llm_unavailable'):
                    raise
