"""A set of escalation cases is read strictly: one wrong field refuses the whole set."""

import json
from collections import Counter
from pathlib import Path

import pytest

from supportiq_release.gate.adapters import (
    CasesInvalidError,
    CasesProblem,
    read_cases_file,
)
from supportiq_release.gate.domain import (
    CaseKind,
    DraftStatus,
    Failure,
    Injection,
    ReasonCode,
    Recommendation,
    WrittenFor,
)
from tests.unit.gate.fakes import (
    ABSTAIN,
    MESSAGE,
    SET_NAME,
    WRITTEN_FOR,
    case_document,
    expected_document,
    set_document,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
INTERIM_CASES = REPOSITORY_ROOT / "eval" / "suites" / "escalation" / "interim-v1" / "cases.json"
INTERIM_SHA256 = "9f548524194e7b42296fb491ffd818b7aa3cf3c94da331c2cdc17113b143ea75"
CASE_ID = "fake-case-1"


def _write(tmp_path: Path, document: object) -> Path:
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(document))
    return path


def _refusal(tmp_path: Path, document: object) -> CasesInvalidError:
    with pytest.raises(CasesInvalidError) as refused:
        read_cases_file(_write(tmp_path, document))
    return refused.value


def _without(document: dict[str, object], name: str) -> dict[str, object]:
    return {key: value for key, value in document.items() if key != name}


def _injected(*probabilities: tuple[str, object], failure: object = None) -> dict[str, object]:
    distribution = [{"label": label, "probability": value} for label, value in probabilities]
    return {"intent_distribution": distribution or None, "failure": failure}


def test_the_interim_set_of_the_repository_reads_with_its_27_cases_and_its_checksum() -> None:
    cases = read_cases_file(INTERIM_CASES)

    assert cases.sha256 == INTERIM_SHA256
    assert cases.case_set.name == "escalation/interim-v1"
    # 27 cases in all, as the README of the set counts them by kind.
    assert Counter(case.kind for case in cases.case_set.cases) == {
        CaseKind.INJECTED_DISTRIBUTION: 17,
        CaseKind.INJECTED_FAILURE: 2,
        CaseKind.STAFF_CHOICE: 2,
        CaseKind.REAL_MODEL: 6,
    }


def test_a_case_gives_its_request_its_injection_and_its_expected_outcome(
    tmp_path: Path,
) -> None:
    case = case_document(
        inject=_injected(("track_order", 0.70), ("request_refund", 0.10), failure="llm"),
        depends_on_model=False,
    )

    cases = read_cases_file(_write(tmp_path, set_document(case)))

    case_set = cases.case_set
    assert case_set.name == SET_NAME
    assert case_set.written_for == WrittenFor(
        ai_service_contract="1.0.0",
        model_version="fake-model-1",
        routing_version="fake-routing-1",
        kb_version="v9",
        kb_document_count=0,
    )
    (read,) = case_set.cases
    assert read.case_id == CASE_ID
    assert read.esc_rule == "ESC-04"
    assert read.message == MESSAGE
    assert read.injection == Injection(
        intent_distribution=(("track_order", 0.70), ("request_refund", 0.10)),
        failure=Failure.LLM,
    )
    assert read.kind is CaseKind.INJECTED_DISTRIBUTION
    assert read.expected == ABSTAIN
    assert read.expected.recommendation is Recommendation.ABSTAIN
    assert read.expected.draft_status is DraftStatus.ABSTAINED
    assert read.expected.required_reason_codes == {ReasonCode.NO_VALID_DOCUMENT}


def test_the_checksum_is_that_of_the_bytes_of_the_file(tmp_path: Path) -> None:
    path = _write(tmp_path, set_document())
    other = tmp_path / "other"
    other.mkdir()
    # The same set with other whitespace is another file, so it has another checksum.
    spaced = other / "cases.json"
    spaced.write_text(json.dumps(set_document(), indent=2))

    assert read_cases_file(path).sha256 != read_cases_file(spaced).sha256


@pytest.mark.parametrize(
    "case",
    [
        pytest.param(
            case_document(expected=expected_document(http_status=True)), id="status-a-boolean"
        ),
        pytest.param(
            case_document(expected=expected_document(http_status="200")), id="status-a-text"
        ),
        pytest.param(
            case_document(expected=_without(expected_document(), "llm_called")),
            id="expected-field-missing",
        ),
        pytest.param(
            case_document(expected={**expected_document(), "note": "x"}),
            id="expected-field-unknown",
        ),
        pytest.param(
            case_document(expected=expected_document(requires_authority="yes")),
            id="authority-a-text",
        ),
        pytest.param(
            case_document(expected=expected_document(llm_called=None)), id="llm-called-null"
        ),
        pytest.param(
            case_document(expected=expected_document(required_reason_codes="low_confidence")),
            id="codes-not-a-list",
        ),
        pytest.param(
            case_document(expected=expected_document(forbidden_reason_codes=[""])),
            id="code-empty",
        ),
        pytest.param(
            case_document(expected=expected_document(recommendation="")),
            id="recommendation-empty",
        ),
        pytest.param(case_document(inject=_injected(("track_order", 1))), id="probability-int"),
        pytest.param(case_document(inject=_injected(("track_order", 0.0))), id="probability-0"),
        pytest.param(
            case_document(inject=_injected(("track_order", 1.5))), id="probability-above-1"
        ),
        pytest.param(
            case_document(inject=_injected(("track_order", -0.2))), id="probability-negative"
        ),
        pytest.param(case_document(inject=_injected(("", 0.5))), id="probability-label-empty"),
        pytest.param(
            case_document(inject=_injected(failure="network")), id="failure-not-a-failure"
        ),
        pytest.param(
            case_document(inject={"intent_distribution": None}), id="inject-field-missing"
        ),
        pytest.param(case_document(inject=[]), id="inject-not-an-object"),
        pytest.param(case_document(esc_rule=""), id="esc-rule-empty"),
        pytest.param(case_document(signal=None), id="signal-null"),
        pytest.param(case_document(without_kb_evidence=""), id="reason-empty"),
        pytest.param(case_document(depends_on_model="true"), id="depends-on-model-a-text"),
        pytest.param(case_document(request=[MESSAGE]), id="request-not-an-object"),
        pytest.param(case_document(request={"as_of": "2026-11-17T09:00:00Z"}), id="no-message"),
        pytest.param(case_document(request={"message": ""}), id="message-empty"),
        pytest.param(
            case_document(expected=expected_document(recommendation="abstained")),
            id="recommendation-outside-the-contract",
        ),
        pytest.param(
            case_document(expected=expected_document(draft_status="abstain")),
            id="draft-status-outside-the-contract",
        ),
        pytest.param(
            case_document(expected=expected_document(required_reason_codes=["low_confidance"])),
            id="required-code-outside-the-contract",
        ),
        pytest.param(
            case_document(expected=expected_document(forbidden_reason_codes=["authority"])),
            id="forbidden-code-outside-the-contract",
        ),
        pytest.param(
            case_document(inject=_injected(("track_order", 0.5), ("track_order", 0.3))),
            id="distribution-label-twice",
        ),
        pytest.param(
            case_document(inject=_injected(("refund", 0.9))), id="distribution-label-not-an-intent"
        ),
        pytest.param(
            case_document(inject=_injected(("track_order", 0.7), ("request_refund", 0.4))),
            id="distribution-above-1",
        ),
        pytest.param(
            case_document(inject=_injected(("request_refund", 0.1), ("track_order", 0.7))),
            id="distribution-not-most-likely-first",
        ),
        pytest.param(
            case_document(inject=_injected(("track_order", 0.01))),
            id="distribution-below-the-share-of-the-rest",
        ),
    ],
)
def test_a_wrong_field_of_a_case_refuses_the_set_and_names_the_case(
    tmp_path: Path, case: dict[str, object]
) -> None:
    refusal = _refusal(tmp_path, set_document(case_document("fake-case-0"), case))

    assert refusal.problem is CasesProblem.SHAPE_INVALID
    assert refusal.case_id == CASE_ID
    assert str(refusal) == f"The escalation cases are refused: shape_invalid, case {CASE_ID}."


@pytest.mark.parametrize(
    "case",
    [
        pytest.param(_without(case_document(), "signal"), id="case-field-missing"),
        pytest.param({**case_document(), "note": "x"}, id="case-field-unknown"),
    ],
)
def test_a_case_without_its_exact_fields_refuses_the_set_and_names_the_case(
    tmp_path: Path, case: object
) -> None:
    refusal = _refusal(tmp_path, set_document(cases=[case_document("fake-case-0"), case]))

    assert refusal.problem is CasesProblem.SHAPE_INVALID
    assert refusal.case_id == CASE_ID


@pytest.mark.parametrize(
    "case",
    [
        pytest.param(_without(case_document(), "case_id"), id="case-id-missing"),
        pytest.param(case_document(case_id=""), id="case-id-empty"),
        pytest.param({**case_document(), "case_id": 7}, id="case-id-a-number"),
        pytest.param("fake-case-1", id="case-not-an-object"),
    ],
)
def test_a_case_without_an_id_refuses_the_set_without_naming_a_case(
    tmp_path: Path, case: object
) -> None:
    refusal = _refusal(tmp_path, set_document(cases=[case_document("fake-case-0"), case]))

    assert refusal.problem is CasesProblem.SHAPE_INVALID
    assert refusal.case_id is None


@pytest.mark.parametrize(
    "document",
    [
        pytest.param([set_document()], id="not-an-object"),
        pytest.param(_without(set_document(), "label"), id="set-field-missing"),
        pytest.param({**set_document(), "note": "x"}, id="set-field-unknown"),
        pytest.param(set_document(set=""), id="set-name-empty"),
        pytest.param(set_document(label=None), id="label-null"),
        pytest.param(set_document(cases={}), id="cases-not-a-list"),
        pytest.param(set_document(cases=[]), id="no-case"),
        pytest.param(set_document(written_for=None), id="written-for-null"),
    ],
)
def test_a_wrong_field_of_the_set_refuses_it_without_naming_a_case(
    tmp_path: Path, document: object
) -> None:
    refusal = _refusal(tmp_path, document)

    assert refusal.problem is CasesProblem.SHAPE_INVALID
    assert refusal.case_id is None


@pytest.mark.parametrize(
    ("name", "value"),
    [
        pytest.param("kb_document_count", -1, id="kb-count-negative"),
        pytest.param("kb_document_count", True, id="kb-count-a-boolean"),
        pytest.param("kb_document_count", 1.0, id="kb-count-a-float"),
        pytest.param("model_version", "", id="model-version-empty"),
        pytest.param("routing_version", None, id="routing-version-null"),
    ],
)
def test_a_wrong_field_of_written_for_refuses_the_set(
    tmp_path: Path, name: str, value: object
) -> None:
    written_for = {**WRITTEN_FOR, name: value}

    refusal = _refusal(tmp_path, set_document(written_for=written_for))

    assert refusal.problem is CasesProblem.SHAPE_INVALID
    assert refusal.case_id is None


def test_a_case_id_given_twice_refuses_the_set(tmp_path: Path) -> None:
    refusal = _refusal(tmp_path, set_document(case_document(), case_document()))

    assert refusal.problem is CasesProblem.CASE_ID_TWICE
    assert str(refusal) == "The escalation cases are refused: case_id_twice."
