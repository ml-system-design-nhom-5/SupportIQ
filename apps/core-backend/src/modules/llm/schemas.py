from typing import Literal
from pydantic import BaseModel, Field

class ValidatedDraft(BaseModel):
    body: str
    citation_ids: list[str]

class LlmCallOutcome(BaseModel):
    status: Literal["completed", "timeout", "failed", "outcome_unknown"]
    draft: ValidatedDraft | None = None
    cost_micro: int = 0
    response_tokens: int = 0
    error: str | None = None
