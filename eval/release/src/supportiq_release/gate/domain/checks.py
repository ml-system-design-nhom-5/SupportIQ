"""Compare the responses of a candidate with the expected outcome of each case (DATA-57).

A case passes only when every field of its expected outcome matches both operations,
`createAnalysis` and `createDraft`. The fields of an outcome are read only from a `200` body,
and the type of a problem only from a Problem Details body, so the `status` of a problem is
never read as the status of a draft.

A mismatch names the operation and the field, with what the candidate gave: an HTTP status, a
value of a closed set of the contract, or reason codes. A value outside the closed set shows as
`other`, never as the text itself, because a response can hold text of the message (LOG-29).
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import cast

from supportiq_release.gate.domain.cases import (
    Case,
    CaseKind,
    CaseSet,
    DraftStatus,
    Failure,
    ProblemType,
    ReasonCode,
    Recommendation,
    WrittenFor,
)

INTERIM_LABEL = "interim, not the shared scenario set"
# The one version of the contract of `ai-service` whose responses the gate reads.
CONTRACT_VERSION = "1.0.0"
REQUIRES_AUTHORITY = ReasonCode.REQUIRES_AUTHORITY
HTTP_OK = 200
ANALYSIS = "createAnalysis"
DRAFT = "createDraft"
_NULL = "null"
_OTHER = "other"
_EMPTY = "empty"


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
class Mismatch:
    """One field of a case that did not match.

    Attributes:
        field: The field, as `<operation>.<field>`.
        observed: What the candidate gave for it: an HTTP status, a value of a closed set of the
            contract, or reason codes, never text (`other` for a value outside the set).
    """

    field: str
    observed: str


@dataclass(frozen=True, slots=True)
class CaseResult:
    """The result of one case.

    Attributes:
        case_id: The ID of the case.
        esc_rule: The escalation rule of the case.
        kind: What the outcome rests on: the real model, an injected part, or a staff choice.
        injected_failure: The part that the case made fail, or None.
        mismatches: Each field that did not match, with what was observed; none when passed.
    """

    case_id: str
    esc_rule: str
    kind: CaseKind
    injected_failure: Failure | None
    mismatches: tuple[Mismatch, ...]

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
        mismatches.append(Mismatch(f"{DRAFT}.llm_called", str(observation.llm_called).lower()))
    return CaseResult(
        case_id=case.case_id,
        esc_rule=case.esc_rule,
        kind=case.kind,
        injected_failure=None if case.injection is None else case.injection.failure,
        mismatches=tuple(mismatches),
    )


def _status_mismatches(case: Case, observation: Observation) -> list[Mismatch]:
    expected = case.expected
    mismatches: list[Mismatch] = []
    for operation, response in ((ANALYSIS, observation.analysis), (DRAFT, observation.draft)):
        if response.status != expected.http_status:
            mismatches.append(Mismatch(f"{operation}.http_status", str(response.status)))
        problem_type = _problem(response).get("type")
        if problem_type != expected.problem_type:
            shown = _shown_member(problem_type, ProblemType)
            mismatches.append(Mismatch(f"{operation}.problem_type", shown))
    return mismatches


def _routing_mismatches(case: Case, observation: Observation) -> list[Mismatch]:
    expected = case.expected
    analysis, draft = _outcome(observation.analysis), _outcome(observation.draft)
    fields = (
        (
            f"{ANALYSIS}.recommendation",
            _field(analysis, "routing", "recommendation"),
            expected.recommendation,
            Recommendation,
        ),
        (
            f"{DRAFT}.recommendation",
            _field(draft, "analysis", "routing", "recommendation"),
            expected.recommendation,
            Recommendation,
        ),
        (f"{DRAFT}.draft_status", _field(draft, "status"), expected.draft_status, DraftStatus),
    )
    return [
        Mismatch(name, _shown_member(value, members))
        for name, value, wanted, members in fields
        if value != wanted
    ]


def _reason_code_mismatches(
    case: Case, operation: str, codes: frozenset[str] | None
) -> list[Mismatch]:
    expected = case.expected
    if codes is None:
        # A response without reason codes matches only a case that expects a failure.
        missing = Mismatch(f"{operation}.reason_codes", _NULL)
        return [] if expected.http_status != HTTP_OK else [missing]
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
    return [
        Mismatch(f"{operation}.{name}", _shown_codes(codes))
        for name, matches in checks
        if not matches
    ]


def _analysis_codes(response: Response) -> frozenset[str] | None:
    return _codes(_field(_outcome(response), "routing", "reason_codes"))


def _draft_codes(response: Response) -> frozenset[str] | None:
    return _codes(_field(_outcome(response), "reason_codes"))


def _outcome(response: Response) -> Mapping[str, object]:
    # Only a 200 body holds the fields of an outcome. A Problem Details body holds none: its
    # `status` is the HTTP status, never the status of a draft.
    return response.body if response.status == HTTP_OK else {}


def _problem(response: Response) -> Mapping[str, object]:
    # Only a body of another status is a Problem Details body with a `type`.
    return response.body if response.status != HTTP_OK else {}


def _shown_member(value: object, members: type[StrEnum]) -> str:
    # A value of the closed set, `null`, or `other`: never a text that the candidate wrote.
    if value is None:
        return _NULL
    return value if isinstance(value, str) and value in {m.value for m in members} else _OTHER


def _shown_codes(codes: frozenset[str]) -> str:
    # The codes of the contract, sorted; any other code only as a count.
    known = sorted(code for code in codes if code in {m.value for m in ReasonCode})
    others = len(codes) - len(known)
    shown = [*known, *([f"{_OTHER}:{others}"] if others else [])]
    return ",".join(shown) if shown else _EMPTY


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
