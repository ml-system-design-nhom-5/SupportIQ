"""The analysis: the result of the pipeline up to routing (ADR-0005).

These types hold the shape of the contract's `Analysis`. How each value is computed belongs
to the pipeline, not to these types.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import NewType

from supportiq_ai_service.release import AssetVersions
from supportiq_ai_service.suggestions.domain.request import IntentName

# One reason code of the contract's `AiServiceReasonCode`. Internal.
ReasonCode = NewType("ReasonCode", str)


class ConfidenceBand(StrEnum):
    """The band of the probability of the model's top intent."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class DocumentValidity(StrEnum):
    """Whether a KB document version is in effect at `as_of`."""

    VALID = "valid"
    EXPIRED = "expired"
    CONFLICTING = "conflicting"


class RoutingRecommendation(StrEnum):
    """The recommended next step for the ticket (ADR-0005). Staff and managers decide."""

    DRAFT = "draft"
    ABSTAIN = "abstain"
    ESCALATE = "escalate"


@dataclass(frozen=True, slots=True)
class ModelIntent:
    """The top intent of the classification model.

    Attributes:
        label: The predicted intent.
        probability: Its probability, from 0 to 1.
        confidence_band: The band of the probability.
    """

    label: IntentName
    probability: float
    confidence_band: ConfidenceBand


@dataclass(frozen=True, slots=True)
class StaffIntent:
    """An intent that staff chose or confirmed; it has no probability (ADR-0005, statement 7).

    Attributes:
        label: The intent that staff chose.
    """

    label: IntentName


@dataclass(frozen=True, slots=True)
class IntentCandidate:
    """A further candidate intent of the model.

    Attributes:
        label: The candidate intent.
        probability: Its probability, from 0 to 1.
    """

    label: IntentName
    probability: float


@dataclass(frozen=True, slots=True)
class RankedDocument:
    """A KB document version that retrieval found.

    Attributes:
        document_id: The document.
        version: The version of the document.
        title: The title.
        policy_key: The policy key.
        effective_start_at: When the version takes effect, in UTC.
        effective_end_at: When it stops being in effect; None when open-ended.
        validity: Whether it is in effect at `as_of`.
        rank: Its rank, from 1.
        snippet: The supporting snippet.
    """

    document_id: str
    version: str
    title: str
    policy_key: str
    effective_start_at: datetime
    effective_end_at: datetime | None
    validity: DocumentValidity
    rank: int
    snippet: str


@dataclass(frozen=True, slots=True)
class Routing:
    """The routing recommendation and its reason codes.

    Attributes:
        recommendation: The recommended next step.
        reason_codes: The reason codes, without repeats.
    """

    recommendation: RoutingRecommendation
    reason_codes: tuple[ReasonCode, ...]


@dataclass(frozen=True, slots=True)
class AnalysisWarning:
    """A condition that allows a draft but needs staff attention.

    Attributes:
        warning_id: The identifier of the warning, unique in its list.
        reason_code: Why staff must look.
    """

    warning_id: str
    reason_code: ReasonCode


@dataclass(frozen=True, slots=True)
class StepLatencies:
    """How long the steps took, in milliseconds.

    Attributes:
        total_ms: The whole call.
        analysis_ms: The steps up to routing.
        llm_ms: The LLM step; None when the LLM was not called.
    """

    total_ms: int
    analysis_ms: int
    llm_ms: int | None = None


@dataclass(frozen=True, slots=True)
class Analysis:
    """The result of the pipeline up to routing.

    Attributes:
        intent: The model's top intent, or the intent that staff chose.
        alternatives: The next most likely intents, empty when staff chose the intent.
        is_in_scope: Whether the intent is one of the 12 in-scope intents.
        documents: The KB document versions that retrieval found, by rank.
        routing: The routing recommendation.
        warnings: The warnings that staff must acknowledge.
        versions: The release and asset versions that produced the analysis.
        step_latencies: How long the steps took.
    """

    intent: ModelIntent | StaffIntent
    alternatives: tuple[IntentCandidate, ...]
    is_in_scope: bool
    documents: tuple[RankedDocument, ...]
    routing: Routing
    warnings: tuple[AnalysisWarning, ...]
    versions: AssetVersions
    step_latencies: StepLatencies
