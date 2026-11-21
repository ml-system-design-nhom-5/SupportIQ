"""A version is admitted only when it is released and every field is valid (ADR-0021, DATA-13)."""

from datetime import UTC, datetime

import pytest

from supportiq_release.kb_ingestion.domain import (
    AdmittedVersion,
    Conflict,
    IngestionResult,
    KbField,
    QuarantineCode,
    QuarantinedRecord,
    QuarantineReason,
    RawKb,
    admit,
)
from tests.unit.kb_ingestion.fakes import (
    BODY,
    KB_FILE_NAME,
    KB_VERSION,
    LABELS,
    TITLE,
    raw_kb,
    record,
    sha256_text,
    without,
)

KEY = ("FAKE-REFUND-001", "1.0")
NOT_IN_RELEASE = QuarantineReason(QuarantineCode.NOT_IN_RELEASE)
DUPLICATE_VERSION = QuarantineReason(QuarantineCode.DUPLICATE_VERSION)
UNKNOWN_INTENT = QuarantineReason(QuarantineCode.UNKNOWN_INTENT, KbField.SUPPORTED_INTENTS)
VIETNAMESE_TITLE = "Chính sách hoàn tiền trong 30 ngày"
LONE_SURROGATE = "a\ud800b"
# The SHA-256 of VIETNAMESE_TITLE in UTF-8.
VIETNAMESE_CHECKSUM = "37ab0a2c17e416ba34c6d0e8685afe38107a061d3b226d22eac325f53a281e67"


def _admit(kb: RawKb) -> IngestionResult:
    return admit(kb, LABELS, sha256_text)


def _missing(field: KbField) -> QuarantineReason:
    return QuarantineReason(QuarantineCode.MISSING_FIELD, field)


def _invalid(field: KbField) -> QuarantineReason:
    return QuarantineReason(QuarantineCode.INVALID_FIELD, field)


def _reasons(*records: dict[str, object]) -> tuple[QuarantineReason, ...]:
    (quarantined,) = _admit(raw_kb(*records)).quarantined
    return quarantined.reasons


def test_a_released_version_with_every_field_is_admitted_with_its_texts_unchanged() -> None:
    result = _admit(raw_kb(record()))

    assert result.admitted == (
        AdmittedVersion(
            document_id="FAKE-REFUND-001",
            version="1.0",
            title=TITLE,
            body=BODY,
            policy_key="fake_refund_window",
            effective_start_at="2026-01-01T00:00:00Z",
            effective_end_at="2026-12-31T23:59:59Z",
            owner="fake_policy_owner",
            source=f"{KB_FILE_NAME}, KB {KB_VERSION}",
            intents=("request_refund",),
            starts=datetime(2026, 1, 1, tzinfo=UTC),
            ends=datetime(2026, 12, 31, 23, 59, 59, tzinfo=UTC),
        ),
    )
    assert (result.quarantined, result.conflicts, result.released_but_absent) == ((), (), ())
    assert not result.needs_accepted_quarantine


def test_a_field_that_ingestion_does_not_read_never_decides() -> None:
    # `main` refused a status other than `approved`; here the release file decides.
    result = _admit(raw_kb(record(status="draft"), record(document_id="FAKE-2", status=3)))

    assert [version.key for version in result.admitted] == [("FAKE-2", "1.0"), KEY]


def test_an_open_ended_version_is_admitted_without_an_end() -> None:
    (admitted,) = _admit(raw_kb(without(record(), "valid_to"))).admitted

    assert (admitted.effective_end_at, admitted.ends) == (None, None)


@pytest.mark.parametrize(
    "field",
    [
        KbField.TITLE,
        KbField.CONTENT,
        KbField.CONTENT_HASH,
        KbField.POLICY_KEY,
        KbField.VALID_FROM,
        KbField.APPROVED_BY,
        KbField.SUPPORTED_INTENTS,
    ],
)
def test_a_missing_or_null_field_is_quarantined_and_never_filled_in(field: KbField) -> None:
    absent = _reasons(without(record(), field))
    null = _reasons(record(**{field: None}))

    assert absent == null == (_missing(field),)


def test_a_record_without_a_document_id_is_quarantined_by_its_position() -> None:
    result = _admit(raw_kb(record(document_id="FAKE-2"), without(record(), "document_id")))

    assert result.quarantined == (
        QuarantinedRecord(
            position=1,
            document_id=None,
            version="1.0",
            reasons=(_missing(KbField.DOCUMENT_ID), NOT_IN_RELEASE),
        ),
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        pytest.param(KbField.TITLE, "", id="empty-title"),
        pytest.param(KbField.TITLE, "t" * 201, id="long-title"),
        pytest.param(KbField.CONTENT, "c" * 20_001, id="long-content"),
        pytest.param(KbField.POLICY_KEY, "k" * 101, id="long-policy-key"),
        pytest.param(KbField.APPROVED_BY, "o" * 101, id="long-owner"),
        pytest.param(KbField.APPROVED_BY, ["fake_policy_owner"], id="owner-not-text"),
        pytest.param(KbField.VALID_FROM, "2026-01-01", id="date-without-time"),
        pytest.param(KbField.VALID_FROM, "2026-13-01T00:00:00Z", id="no-such-month"),
        pytest.param(KbField.VALID_FROM, 20_260_101, id="time-as-number"),
        pytest.param(KbField.VALID_TO, "2027-01-01T00:00:00+07:00", id="not-utc"),
        pytest.param(KbField.VERSION, "1 0", id="version-pattern"),
        pytest.param(KbField.VERSION, "v" * 65, id="long-version"),
        pytest.param(KbField.CONTENT_HASH, "A" * 64, id="checksum-in-uppercase"),
        pytest.param(KbField.CONTENT_HASH, "a" * 63, id="checksum-too-short"),
        pytest.param(KbField.CONTENT_HASH, 7, id="checksum-not-text"),
    ],
)
def test_a_field_outside_the_limits_of_the_contract_is_quarantined(
    field: KbField, value: object
) -> None:
    assert _reasons(record(**{field: value})) == (_invalid(field),)


@pytest.mark.parametrize(
    "field", [KbField.TITLE, KbField.CONTENT, KbField.POLICY_KEY, KbField.APPROVED_BY]
)
@pytest.mark.parametrize("blank", [" ", "\t\n", "　"])
def test_a_text_of_white_space_only_is_quarantined_as_main_did(field: KbField, blank: str) -> None:
    assert _reasons(record(**{field: blank})) == (_invalid(field),)


@pytest.mark.parametrize(
    "field", [KbField.TITLE, KbField.CONTENT, KbField.POLICY_KEY, KbField.APPROVED_BY]
)
def test_a_text_with_a_lone_surrogate_is_quarantined_and_never_written(field: KbField) -> None:
    # JSON allows `\ud800`, which UTF-8 cannot write.
    assert _reasons(record(**{field: LONE_SURROGATE})) == (_invalid(field),)


def test_each_field_may_reach_the_limit_of_the_contract() -> None:
    longest = record(
        title="t" * 200,
        content="c" * 20_000,
        policy_key="k" * 100,
        approved_by="o" * 100,
        valid_from="2026-01-01T00:00:00.123456Z",
    )

    assert _admit(raw_kb(longest)).admitted


def test_a_text_outside_ascii_is_admitted_unchanged_and_measured_in_characters() -> None:
    # 200 characters, but 600 bytes in UTF-8: the contract limits characters.
    longest = record(document_id="FAKE-VI-1", title="ệ" * 200, content=VIETNAMESE_TITLE)
    too_long = record(document_id="FAKE-VI-2", title="ệ" * 201)

    result = _admit(raw_kb(longest, too_long))

    assert [(version.title, version.body) for version in result.admitted] == [
        ("ệ" * 200, VIETNAMESE_TITLE)
    ]
    assert result.quarantined[0].reasons == (_invalid(KbField.TITLE),)


def test_a_content_that_its_checksum_does_not_match_is_quarantined() -> None:
    # The content was edited and its checksum was not.
    edited = record(content="An edited fake rule.", content_hash=sha256_text(BODY))

    assert _reasons(edited) == (_invalid(KbField.CONTENT_HASH),)


def test_the_declared_checksum_is_compared_with_the_digest_of_the_content() -> None:
    # A digest that knows only this content: any other text would raise a KeyError.
    digest = {VIETNAMESE_TITLE: VIETNAMESE_CHECKSUM}.__getitem__
    declared = record(content=VIETNAMESE_TITLE, content_hash=VIETNAMESE_CHECKSUM)

    assert [version.body for version in admit(raw_kb(declared), LABELS, digest).admitted] == [
        VIETNAMESE_TITLE
    ]


def test_a_document_id_that_is_not_an_identifier_never_leaves_the_kb_file() -> None:
    (quarantined,) = _admit(raw_kb(record(document_id="A refund rule text"))).quarantined

    assert (quarantined.document_id, quarantined.reasons) == (
        None,
        (_invalid(KbField.DOCUMENT_ID),),
    )


@pytest.mark.parametrize("valid_to", ["2026-01-01T00:00:00Z", "2025-12-31T23:59:59Z"])
def test_a_version_that_ends_when_or_before_it_starts_is_quarantined(valid_to: str) -> None:
    assert _reasons(record(valid_to=valid_to)) == (_invalid(KbField.VALID_TO),)


def test_a_version_that_the_kb_holder_did_not_release_is_quarantined() -> None:
    result = _admit(raw_kb(record(), released=[("FAKE-REFUND-001", "2.0")]))

    assert result.quarantined[0].reasons == (NOT_IN_RELEASE,)
    assert result.released_but_absent == (("FAKE-REFUND-001", "2.0"),)
    assert result.needs_accepted_quarantine


def test_a_released_version_that_the_kb_file_lacks_needs_an_issue_that_accepts_it() -> None:
    result = _admit(raw_kb(record(), released=[KEY, ("FAKE-GONE", "3")]))

    assert (len(result.admitted), result.quarantined) == (1, ())
    assert result.released_but_absent == (("FAKE-GONE", "3"),)
    assert result.needs_accepted_quarantine


def test_a_version_written_as_a_number_is_never_turned_into_text() -> None:
    # The case of the three `b1000000-…` documents of KB v2.
    result = _admit(raw_kb(record(version=1), released=[("FAKE-REFUND-001", "1")]))

    assert result.quarantined == (
        QuarantinedRecord(
            position=0,
            document_id="FAKE-REFUND-001",
            version=None,
            reasons=(_invalid(KbField.VERSION), NOT_IN_RELEASE),
        ),
    )
    assert result.released_but_absent == (("FAKE-REFUND-001", "1"),)


def test_a_record_carries_every_reason_sorted_by_code_then_field() -> None:
    broken = record(title="", policy_key=None, supported_intents=["not_a_label"])

    reasons = _admit(raw_kb(broken, released=[])).quarantined[0].reasons

    assert reasons == (
        _invalid(KbField.TITLE),
        _missing(KbField.POLICY_KEY),
        NOT_IN_RELEASE,
        UNKNOWN_INTENT,
    )


def test_two_records_of_one_version_are_both_quarantined() -> None:
    result = _admit(raw_kb(record(), record(title="Another fake title")))

    assert [(entry.position, entry.reasons) for entry in result.quarantined] == [
        (0, (DUPLICATE_VERSION,)),
        (1, (DUPLICATE_VERSION,)),
    ]
    assert result.admitted == ()


@pytest.mark.parametrize(
    ("intents", "reasons"),
    [
        pytest.param([], (_invalid(KbField.SUPPORTED_INTENTS),), id="empty"),
        pytest.param("request_refund", (_invalid(KbField.SUPPORTED_INTENTS),), id="not-a-list"),
        pytest.param(["request_refund", 3], (_invalid(KbField.SUPPORTED_INTENTS),), id="not-text"),
        pytest.param(["request_refund"] * 2, (_invalid(KbField.SUPPORTED_INTENTS),), id="twice"),
        pytest.param(["request_refund", "not_a_label"], (UNKNOWN_INTENT,), id="unknown"),
        pytest.param(
            ["request_refund", "request_refund", "not_a_label"],
            (_invalid(KbField.SUPPORTED_INTENTS), UNKNOWN_INTENT),
            id="twice-and-unknown",
        ),
    ],
)
def test_the_intents_are_texts_each_once_and_each_a_label_of_the_contract(
    intents: object, reasons: tuple[QuarantineReason, ...]
) -> None:
    assert _reasons(record(supported_intents=intents)) == reasons


def test_admitted_versions_follow_their_keys_and_quarantined_records_their_position() -> None:
    result = _admit(
        raw_kb(
            record(document_id="FAKE-C"),
            record(document_id="FAKE-B", title=""),
            record(document_id="FAKE-A"),
            record(document_id="FAKE-D", content=None),
        )
    )

    assert [version.document_id for version in result.admitted] == ["FAKE-A", "FAKE-C"]
    assert [(entry.position, entry.document_id) for entry in result.quarantined] == [
        (1, "FAKE-B"),
        (3, "FAKE-D"),
    ]


def test_a_conflict_between_admitted_versions_is_listed_and_both_stay_admitted() -> None:
    result = _admit(raw_kb(record(), record(document_id="FAKE-REFUND-002")))

    assert len(result.admitted) == len(result.conflicts) * 2
    assert result.conflicts == (Conflict(first=KEY, second=("FAKE-REFUND-002", "1.0")),)
