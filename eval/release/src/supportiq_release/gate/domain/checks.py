"""Compare the responses of a candidate with the expected outcome of each case (DATA-57).

A case passes only when every field of its expected outcome matches both operations,
`createAnalysis` and `createDraft`. A mismatch names the operation and the field only, never a
value of the response, because a response can hold text of the message (LOG-29).
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from supportiq_release.gate.domain.cases import (
    Case,
    CaseKind,
    CaseSet,
    Failure,
    ReasonCode,
    WrittenFor,
)

INTERIM_LABEL = "interim, not the shared scenario set"
# The one version of the contract of `ai-service` whose responses the gate reads.
CONTRACT_VERSION = "1.0.0"
REQUIRES_AUTHORITY = ReasonCode.REQUIRES_AUTHORITY
HTTP_OK = 200
ANALYSIS = "createAnalysis"
DRAFT = "createDraft"


@dataclass(frozen=True, slots=True)
class Response:
    """One response of the candidate.

    Attributes:
        status: The HTTP status.
        body: The JSON object of the body, or an empty mapping when it is not one.
    """

    status: int
    body: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class Observation:
    """What the candidate did for one case.

    Attributes:
        analysis: The response of `createAnalysis`.
        draft: The response of `createDraft`.
        llm_called: Whether the LLM step received a call during `createDraft`.
    """

    analysis: Response
    draft: Response
    llm_called: bool


@dataclass(frozen=True, slots=True)
class CaseResult:
    """The result of one case.

    Attributes:
        case_id: The ID of the case.
        esc_rule: The escalation rule of the case.
        kind: What the outcome rests on: the real model, an injected part, or a staff choice.
        injected_failure: The part that the case made fail, or None.
        mismatches: Each field that did not match, as `<operation>.<field>`; none when passed.
    """

    case_id: str
    esc_rule: str
    kind: CaseKind
    injected_failure: Failure | None
    mismatches: tuple[str, ...]

    @property
    def passed(self) -> bool:
        """Whether every field matched."""
        return not self.mismatches


def written_for_mismatches(case_set: CaseSet, release: WrittenFor) -> tuple[str, ...]:
    """Return each field of `written_for`, and the label, that the release does not match.

    Args:
        case_set: The set of cases.
        release: The versions of the candidate, its KB size, and the contract of the gate.

    Returns:
        The names of the fields that differ; none when the set is written for the release.
    """
    expected = case_set.written_for
    fields = (
        ("label", case_set.label == INTERIM_LABEL),
        ("ai_service_contract", expected.ai_service_contract == release.ai_service_contract),
        ("model_version", expected.model_version == release.model_version),
        ("routing_version", expected.routing_version == release.routing_version),
        ("kb_version", expected.kb_version == release.kb_version),
        ("kb_document_count", expected.kb_document_count == release.kb_document_count),
    )
    return tuple(name for name, matches in fields if not matches)


def check_case(case: Case, observation: Observation) -> CaseResult:
    """Compare one observation with the expected outcome of its case.

    Args:
        case: The case.
        observation: What the candidate did.

    Returns:
        The result, with every field that did not match.
    """
    mismatches = [
        *_status_mismatches(case, observation),
        *_routing_mismatches(case, observation),
        *_reason_code_mismatches(case, ANALYSIS, _analysis_codes(observation.analysis)),
        *_reason_code_mismatches(case, DRAFT, _draft_codes(observation.draft)),
    ]
    if observation.llm_called != case.expected.llm_called:
        mismatches.append(f"{DRAFT}.llm_called")
    return CaseResult(
        case_id=case.case_id,
        esc_rule=case.esc_rule,
        kind=case.kind,
        injected_failure=None if case.injection is None else case.injection.failure,
        mismatches=tuple(mismatches),
    )


def _status_mismatches(case: Case, observation: Observation) -> list[str]:
    expected = case.expected
    mismatches: list[str] = []
    for operation, response in ((ANALYSIS, observation.analysis), (DRAFT, observation.draft)):
        if response.status != expected.http_status:
            mismatches.append(f"{operation}.http_status")
        problem_type = response.body.get("type") if expected.problem_type is not None else None
        if problem_type != expected.problem_type:
            mismatches.append(f"{operation}.problem_type")
    return mismatches


def _routing_mismatches(case: Case, observation: Observation) -> list[str]:
    expected = case.expected
    mismatches: list[str] = []
    if _field(observation.analysis.body, "routing", "recommendation") != expected.recommendation:
        mismatches.append(f"{ANALYSIS}.recommendation")
    draft_recommendation = _field(observation.draft.body, "analysis", "routing", "recommendation")
    if draft_recommendation != expected.recommendation:
        mismatches.append(f"{DRAFT}.recommendation")
    if _field(observation.draft.body, "status") != expected.draft_status:
        mismatches.append(f"{DRAFT}.draft_status")
    return mismatches


def _reason_code_mismatches(case: Case, operation: str, codes: frozenset[str] | None) -> list[str]:
    expected = case.expected
    if codes is None:
        # A response without reason codes matches only a case that expects a failure.
        return [] if expected.http_status != HTTP_OK else [f"{operation}.reason_codes"]
    authority = frozenset({REQUIRES_AUTHORITY} if expected.requires_authority else ())
    checks = (
        ("required_reason_codes", expected.required_reason_codes <= codes),
        ("forbidden_reason_codes", not expected.forbidden_reason_codes & codes),
        (
            "no_other_reason_codes",
            not expected.no_other_reason_codes
            or codes == expected.required_reason_codes | authority,
        ),
        (
            "requires_authority",
            expected.requires_authority is None
            or (REQUIRES_AUTHORITY in codes) == expected.requires_authority,
        ),
    )
    return [f"{operation}.{name}" for name, matches in checks if not matches]


def _analysis_codes(response: Response) -> frozenset[str] | None:
    return _codes(_field(response.body, "routing", "reason_codes"))


def _draft_codes(response: Response) -> frozenset[str] | None:
    return _codes(_field(response.body, "reason_codes"))


def _codes(value: object) -> frozenset[str] | None:
    if not isinstance(value, list):
        return None
    # The cast only names the type that `isinstance` found in a JSON value (PY-12).
    items = cast("list[object]", value)
    return frozenset(code for code in items if isinstance(code, str))


def _field(body: Mapping[str, object], *names: str) -> object:
    # The value at a path of nested JSON objects, or None when the path does not exist.
    value: object = body
    for name in names:
        mapping = _mapping(value)
        if mapping is None:
            return None
        value = mapping.get(name)
    return value


def _mapping(value: object) -> Mapping[str, object] | None:
    # The cast only names the type that `isinstance` found in a JSON value (PY-12).
    return cast("Mapping[str, object]", value) if isinstance(value, Mapping) else None
