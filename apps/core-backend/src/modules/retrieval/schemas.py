from datetime import datetime
from pydantic import BaseModel, Field

class Evidence(BaseModel):
    citation_id: str
    source_id: str
    snippet: str
    title: str | None = None
    policy_key: str | None = None
    normalized_rule_value: str | None = None
    valid_to: datetime | None = None
    allowed_roles: list[str] = Field(default_factory=lambda: ["agent", "staff", "manager", "admin"])

class RetrievalResult(BaseModel):
    evidence: list[Evidence]
    reason_codes: list[str] = Field(default_factory=list)
