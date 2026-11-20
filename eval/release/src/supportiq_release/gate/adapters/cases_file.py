"""Read a set of escalation cases strictly, with the SHA-256 of its file (DATA-12).

The format is the one that `data/benchmarks/escalation/interim-v1/README.md` (Format) states. A
field that is missing, unknown, or of another type refuses the whole set, so a case is never
skipped or read in part. A problem type, a recommendation, a draft status, or a reason code
outside contract 1.0.0 refuses the set too, so a typo never shows as a failed case. An injected
distribution lists each intent label of the model at most once, most likely first, with
probabilities that add up to at most 1 and that each stay above the equal share of the rest, so
the listed intents come first. The SHA-256 of the file goes into the record of the gate run,
and the approval of the set must cover it.
"""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import cast

from supportiq_ai_service.intent import INTENT_LABELS

from supportiq_release.errors import ReleaseCommandError
from supportiq_release.files import read_json_file
from supportiq_release.gate.domain import (
    Case,
    CaseSet,
    DraftStatus,
    Expected,
    Failure,
    Injection,
    ProblemType,
    ReasonCode,
    Recommendation,
    WrittenFor,
)

_SET_FIELDS = frozenset({"label", "set", "written_for", "cases"})
_WRITTEN_FOR_FIELDS = frozenset(
    {"ai_service_contract", "model_version", "routing_version", "kb_version", "kb_document_count"}
)
_CASE_FIELDS = frozenset(
    {
        "case_id",
        "esc_rule",
        "signal",
        "request",
        "inject",
        "depends_on_model",
        "expected",
        "without_kb_evidence",
    }
)
_INJECT_FIELDS = frozenset({"intent_distribution", "failure"})
_PROBABILITY_FIELDS = frozenset({"label", "probability"})
_EXPECTED_FIELDS = frozenset(
    {
        "http_status",
        "problem_type",
        "recommendation",
        "draft_status",
        "required_reason_codes",
        "forbidden_reason_codes",
        "no_other_reason_codes",
        "requires_authority",
        "llm_called",
    }
)


class CasesProblem(StrEnum):
    """Why a set of cases is refused."""

    SHAPE_INVALID = "shape_invalid"
    CASE_ID_TWICE = "case_id_twice"


class CasesInvalidError(ReleaseCommandError):
    """A set of cases cannot be read. The message names the problem and the case only."""

    def __init__(self, problem: CasesProblem, case_id: str | None = None) -> None:
        """Build the error with a message that names the problem and the case.

        Args:
            problem: Why the set is refused.
            case_id: The case that the problem is about, if it is known.
        """
        about = "" if case_id is None else f", case {case_id}"
        super().__init__(f"The escalation cases are refused: {problem}{about}.")
        self.problem = problem
        self.case_id = case_id


@dataclass(frozen=True, slots=True)
class CasesFile:
    """A set of cases, read, with the SHA-256 of its file.

    Attributes:
        case_set: The set.
        sha256: The SHA-256 of the bytes of the file, in lowercase hexadecimal.
    """

    case_set: CaseSet
    sha256: str


def read_cases_file(path: Path) -> CasesFile:
    """Read and check a set of escalation cases.

    Args:
        path: The file, such as `data/benchmarks/escalation/interim-v1/cases.json`.

    Returns:
        The set, with the checksum of its file.

    Raises:
        JsonFileInvalidError: The file is missing, a link, unreadable, or not strict JSON.
        CasesInvalidError: The set breaks the format, or names a case twice.
    """
    document = read_json_file(path)
    fields = _object(document.content, _SET_FIELDS, None)
    entries = _list(fields["cases"], None)
    cases = tuple(_case(entry) for entry in entries)
    ids = [case.case_id for case in cases]
    if not cases or len(set(ids)) != len(ids):
        raise CasesInvalidError(CasesProblem.CASE_ID_TWICE if cases else CasesProblem.SHAPE_INVALID)
    case_set = CaseSet(
        label=_text(fields["label"], None),
        name=_text(fields["set"], None),
        written_for=_written_for(fields["written_for"]),
        cases=cases,
    )
    return CasesFile(case_set=case_set, sha256=document.sha256)


def _written_for(value: object) -> WrittenFor:
    fields = _object(value, _WRITTEN_FOR_FIELDS, None)
    count = fields["kb_document_count"]
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        raise CasesInvalidError(CasesProblem.SHAPE_INVALID)
    return WrittenFor(
        ai_service_contract=_text(fields["ai_service_contract"], None),
        model_version=_text(fields["model_version"], None),
        routing_version=_text(fields["routing_version"], None),
        kb_version=_text(fields["kb_version"], None),
        kb_document_count=count,
    )


def _case(value: object) -> Case:
    # The ID first, so every later refusal, a missing or unknown field included, names the case.
    case_id = _text(_object(value, None, None).get("case_id"), None)
    fields = _object(value, _CASE_FIELDS, case_id)
    _text(fields["signal"], case_id)
    _text(fields["without_kb_evidence"], case_id)
    request = _object(fields["request"], None, case_id)
    # The message is what the logs must never hold, so a request without one is refused.
    _text(request.get("message"), case_id)
    return Case(
        case_id=case_id,
        esc_rule=_text(fields["esc_rule"], case_id),
        request=request,
        injection=_injection(fields["inject"], case_id),
        depends_on_model=_flag(fields["depends_on_model"], case_id),
        expected=_expected(fields["expected"], case_id),
    )


def _injection(value: object, case_id: str) -> Injection | None:
    if value is None:
        return None
    fields = _object(value, _INJECT_FIELDS, case_id)
    distribution = fields["intent_distribution"]
    failure = fields["failure"]
    if failure is not None and failure not in set(Failure):
        raise CasesInvalidError(CasesProblem.SHAPE_INVALID, case_id)
    return Injection(
        intent_distribution=None if distribution is None else _distribution(distribution, case_id),
        failure=None if failure is None else Failure(cast("str", failure)),
    )


def _distribution(value: object, case_id: str) -> tuple[tuple[str, float], ...]:
    listed = tuple(_probability(entry, case_id) for entry in _list(value, case_id))
    labels = {label for label, _probability in listed}
    if not listed or len(labels) != len(listed) or not labels <= set(INTENT_LABELS):
        raise CasesInvalidError(CasesProblem.SHAPE_INVALID, case_id)
    probabilities = [probability for _label, probability in listed]
    total = math.fsum(probabilities)
    # Every other label gets an equal share of the rest, which stays below each listed one.
    rest = len(INTENT_LABELS) - len(labels)
    share = (1 - total) / rest if rest else 0.0
    if (
        total > 1
        or probabilities != sorted(probabilities, reverse=True)
        or min(probabilities) <= share
    ):
        raise CasesInvalidError(CasesProblem.SHAPE_INVALID, case_id)
    return listed


def _probability(value: object, case_id: str) -> tuple[str, float]:
    fields = _object(value, _PROBABILITY_FIELDS, case_id)
    probability = fields["probability"]
    if not isinstance(probability, float) or not 0 < probability <= 1:
        raise CasesInvalidError(CasesProblem.SHAPE_INVALID, case_id)
    return (_text(fields["label"], case_id), probability)


def _expected(value: object, case_id: str) -> Expected:
    fields = _object(value, _EXPECTED_FIELDS, case_id)
    status = fields["http_status"]
    authority = fields["requires_authority"]
    if not isinstance(status, int) or isinstance(status, bool):
        raise CasesInvalidError(CasesProblem.SHAPE_INVALID, case_id)
    if authority is not None and not isinstance(authority, bool):
        raise CasesInvalidError(CasesProblem.SHAPE_INVALID, case_id)
    return Expected(
        http_status=status,
        problem_type=_optional_member(ProblemType, fields["problem_type"], case_id),
        recommendation=_optional_member(Recommendation, fields["recommendation"], case_id),
        draft_status=_optional_member(DraftStatus, fields["draft_status"], case_id),
        required_reason_codes=_codes(fields["required_reason_codes"], case_id),
        forbidden_reason_codes=_codes(fields["forbidden_reason_codes"], case_id),
        no_other_reason_codes=_flag(fields["no_other_reason_codes"], case_id),
        requires_authority=authority,
        llm_called=_flag(fields["llm_called"], case_id),
    )


def _codes(value: object, case_id: str) -> frozenset[ReasonCode]:
    return frozenset(
        _member(ReasonCode, _text(code, case_id), case_id) for code in _list(value, case_id)
    )


def _member[Member: StrEnum](values: type[Member], value: str, case_id: str) -> Member:
    # A value outside the closed set of the contract refuses the set (CODE-30).
    if value not in set(values):
        raise CasesInvalidError(CasesProblem.SHAPE_INVALID, case_id)
    return values(value)


def _optional_member[Member: StrEnum](
    values: type[Member], value: object, case_id: str
) -> Member | None:
    text = _optional_text(value, case_id)
    return None if text is None else _member(values, text, case_id)


# Each cast below only names the type that `isinstance` found in a JSON value (PY-12).
def _object(
    value: object, names: frozenset[str] | None, case_id: str | None
) -> Mapping[str, object]:
    # `names` None accepts any fields: the request is checked by the contract, not here.
    document = cast("dict[str, object]", value) if isinstance(value, dict) else None
    if document is None or (names is not None and frozenset(document) != names):
        raise CasesInvalidError(CasesProblem.SHAPE_INVALID, case_id)
    return document


def _list(value: object, case_id: str | None) -> Sequence[object]:
    if not isinstance(value, list):
        raise CasesInvalidError(CasesProblem.SHAPE_INVALID, case_id)
    return cast("list[object]", value)


def _text(value: object, case_id: str | None) -> str:
    if not isinstance(value, str) or not value:
        raise CasesInvalidError(CasesProblem.SHAPE_INVALID, case_id)
    return value


def _optional_text(value: object, case_id: str) -> str | None:
    return None if value is None else _text(value, case_id)


def _flag(value: object, case_id: str) -> bool:
    if not isinstance(value, bool):
        raise CasesInvalidError(CasesProblem.SHAPE_INVALID, case_id)
    return value
