"""The interim escalation cases of the offline evaluation gate, as the gate reads them.

The set replaces the mandatory escalation cases of the shared scenario set until that set is in
`eval/` (ADR-0021, Exception to TEST-26). Each case sends one request to `createAnalysis` and
to `createDraft`, possibly with a part of `ai-service` replaced, and states the outcome that
contract 1.0.0 expects (`eval/suites/escalation/interim-v1/README.md`).
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum


class Failure(StrEnum):
    """The part of `ai-service` that a case makes fail."""

    INTENT_MODEL = "intent_model"
    RETRIEVAL = "retrieval"
    LLM = "llm"


class Recommendation(StrEnum):
    """`RoutingRecommendation` of contract 1.0.0 of `ai-service`."""

    DRAFT = "draft"
    ABSTAIN = "abstain"
    ESCALATE = "escalate"


class DraftStatus(StrEnum):
    """The `status` of the `200` body of `createDraft` in contract 1.0.0 of `ai-service`."""

    DRAFT_READY = "draft_ready"
    ABSTAINED = "abstained"
    ESCALATION_RECOMMENDED = "escalation_recommended"
    LLM_UNAVAILABLE = "llm_unavailable"


class ProblemType(StrEnum):
    """The `type` of each Problem Details body that contract 1.0.0 of `ai-service` gives."""

    INTERNAL_ERROR = "urn:supportiq:problem:internal-error"
    INVALID_REQUEST = "urn:supportiq:problem:invalid-request"
    NOT_FOUND = "urn:supportiq:problem:not-found"
    NOT_READY = "urn:supportiq:problem:not-ready"
    UNAUTHENTICATED = "urn:supportiq:problem:unauthenticated"


class ReasonCode(StrEnum):
    """`AiServiceReasonCode` of contract 1.0.0 of `ai-service`."""

    LOW_CONFIDENCE = "low_confidence"
    SIGNAL_DISAGREEMENT = "signal_disagreement"
    OUT_OF_SCOPE_INTENT = "out_of_scope_intent"
    HUMAN_AGENT_REQUESTED = "human_agent_requested"
    REQUIRES_AUTHORITY = "requires_authority"
    NO_VALID_DOCUMENT = "no_valid_document"
    ONLY_EXPIRED_DOCUMENTS = "only_expired_documents"
    CONFLICTING_SOURCES = "conflicting_sources"
    MISSING_INFORMATION = "missing_information"
    SOURCE_REVIEW_OVERDUE = "source_review_overdue"
    GROUNDING_FAILED = "grounding_failed"
    LLM_UNAVAILABLE = "llm_unavailable"
    LLM_INVALID_OUTPUT = "llm_invalid_output"
    BUDGET_EXCEEDED = "budget_exceeded"
    AI_SERVICE_UNAVAILABLE = "ai_service_unavailable"
    PSEUDONYMIZATION_FAILED = "pseudonymization_failed"


class CaseKind(StrEnum):
    """What a case rests on, which the record of a gate run states for each case."""

    REAL_MODEL = "real_model"
    INJECTED_DISTRIBUTION = "injected_distribution"
    INJECTED_FAILURE = "injected_failure"
    STAFF_CHOICE = "staff_choice"


@dataclass(frozen=True, slots=True)
class Injection:
    """The parts of `ai-service` that the gate replaces for one case.

    Attributes:
        intent_distribution: The listed intents and their probabilities, most likely first, or
            None when the intent model is not replaced. Every other intent gets an equal share
            of the rest.
        failure: The part that fails, or None.
    """

    intent_distribution: tuple[tuple[str, float], ...] | None
    failure: Failure | None


@dataclass(frozen=True, slots=True)
class Expected:
    """The outcome of a case under contract 1.0.0.

    Attributes:
        http_status: The status of both operations.
        problem_type: The `type` of the Problem Details body when the status is 500.
        recommendation: The routing recommendation of both operations, or None for a 500.
        draft_status: The `status` of `createDraft`, or None for a 500.
        required_reason_codes: Codes that both lists of reason codes hold.
        forbidden_reason_codes: Codes that neither list holds.
        no_other_reason_codes: Whether both lists hold exactly the required codes, plus
            `requires_authority` when it is expected.
        requires_authority: Whether `requires_authority` is in both lists, or None when it is
            not checked.
        llm_called: Whether the LLM step received a call during `createDraft`.
    """

    http_status: int
    problem_type: ProblemType | None
    recommendation: Recommendation | None
    draft_status: DraftStatus | None
    required_reason_codes: frozenset[ReasonCode]
    forbidden_reason_codes: frozenset[ReasonCode]
    no_other_reason_codes: bool
    requires_authority: bool | None
    llm_called: bool


@dataclass(frozen=True, slots=True)
class Case:
    """One case of the set.

    Attributes:
        case_id: The unique ID of the case.
        esc_rule: The escalation rule that the case checks, such as `ESC-01`.
        request: The body of `createAnalysis` and `createDraft`.
        injection: The parts that the gate replaces, or None.
        depends_on_model: Whether the outcome rests on the real intent model.
        expected: The outcome under contract 1.0.0.
    """

    case_id: str
    esc_rule: str
    request: Mapping[str, object]
    injection: Injection | None
    depends_on_model: bool
    expected: Expected

    @property
    def kind(self) -> CaseKind:
        """Return what the outcome of the case rests on."""
        if self.injection is not None and self.injection.intent_distribution is not None:
            return CaseKind.INJECTED_DISTRIBUTION
        if self.injection is not None and self.injection.failure is not None:
            return CaseKind.INJECTED_FAILURE
        return CaseKind.REAL_MODEL if self.depends_on_model else CaseKind.STAFF_CHOICE

    @property
    def message(self) -> str:
        """Return the message of the request, which the logs must never hold (LOG-29).

        The reader of the cases refuses a request without a message, so the empty text is only
        the value of a case built without one.
        """
        message = self.request.get("message")
        return message if isinstance(message, str) else ""


@dataclass(frozen=True, slots=True)
class WrittenFor:
    """The release that the expected outcomes are written for.

    Attributes:
        ai_service_contract: The version of the contract of `ai-service`.
        model_version: The model artifact version.
        routing_version: The routing configuration version.
        kb_version: The KB version.
        kb_document_count: The number of document versions in the KB.
    """

    ai_service_contract: str
    model_version: str
    routing_version: str
    kb_version: str
    kb_document_count: int


@dataclass(frozen=True, slots=True)
class CaseSet:
    """A versioned set of escalation cases.

    Attributes:
        label: Always `interim, not the shared scenario set`.
        name: The name of the set, such as `escalation/interim-v1`.
        written_for: The release that the expected outcomes are written for.
        cases: The cases, in their order in the file.
    """

    label: str
    name: str
    written_for: WrittenFor
    cases: tuple[Case, ...]
