"""Tests of the errors of pseudonymization (SEC-36; ADR-0029, statements 4 and 5)."""

from app.pseudonymization.domain import (
    PersonalDataLeftError,
    PseudonymizationError,
    PseudonymizationFailureReason,
    PseudonymType,
)


def test_personal_data_left_fails_closed_with_its_own_reason_and_keeps_only_the_type() -> None:
    error = PersonalDataLeftError(PseudonymType.PHONE)

    assert isinstance(error, PseudonymizationError)
    assert error.reason is PseudonymizationFailureReason.PERSONAL_DATA_LEFT
    assert error.reason.value == "personal_data_left"
    assert error.pseudonym_type is PseudonymType.PHONE
    assert error.args == (PseudonymizationError().detail,)
