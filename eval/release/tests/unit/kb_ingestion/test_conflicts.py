"""Conflicts follow the rule of `conflicting_sources` in ai-service (DATA-12, DATA-19).

The cases are those of `ai-service/tests/unit/suggestions/test_evidence.py`, which test
`_in_effect` and `_validity` of `ai-service/app/suggestions/domain/
evidence.py`: a version is in effect from its start, included, until its end, excluded, and two
versions in effect with one policy key conflict. When one side changes, the other must too.
"""

from datetime import UTC, datetime, timedelta

import pytest

from supportiq_release.kb_ingestion.domain import AdmittedVersion, Conflict, find_conflicts

START = datetime(2026, 1, 1, tzinfo=UTC)
SECOND = timedelta(seconds=1)
END = datetime(2026, 12, 31, 23, 59, 59, tzinfo=UTC)


def _version(
    document_id: str,
    policy_key: str = "refund_window",
    starts: datetime = START,
    ends: datetime | None = END,
    version: str = "1.0",
) -> AdmittedVersion:
    return AdmittedVersion(
        document_id=document_id,
        version=version,
        title="A fake title",
        body="A fake body.",
        policy_key=policy_key,
        effective_start_at=starts.isoformat(),
        effective_end_at=None if ends is None else ends.isoformat(),
        owner="fake_owner",
        source="fake_kb.json, KB v9",
        intents=("request_refund",),
        starts=starts,
        ends=ends,
    )


REFUND = _version("REFUND")
SECOND_REFUND = _version("REFUND-B")
DELIVERY = _version("DELIVERY", policy_key="delivery")


def test_two_versions_in_effect_together_with_one_policy_key_conflict() -> None:
    # As `test_two_versions_in_effect_with_one_policy_key_conflict_and_abstain`.
    conflicts = find_conflicts([REFUND, SECOND_REFUND, DELIVERY])

    assert conflicts == (Conflict(first=("REFUND", "1.0"), second=("REFUND-B", "1.0")),)


@pytest.mark.parametrize(
    ("ending_id", "later_id"),
    [
        pytest.param("REFUND-A", "REFUND-B", id="ending-first"),
        pytest.param("REFUND-B", "REFUND-A", id="ending-second"),
    ],
)
def test_a_version_that_ends_when_the_other_starts_does_not_conflict_with_it(
    ending_id: str, later_id: str
) -> None:
    # As `test_a_version_that_ends_at_as_of_has_expired`: the end is excluded, whichever
    # version comes first in the order of the keys.
    ending = _version(ending_id, starts=datetime(2025, 1, 1, tzinfo=UTC), ends=START)
    later = _version(later_id, starts=START, ends=None)

    assert find_conflicts([ending, later]) == ()


def test_a_version_that_starts_while_the_other_is_in_effect_conflicts_with_it() -> None:
    # As `test_a_version_that_starts_at_as_of_is_in_effect`: the start is included, so a
    # period of one second in common, from the start of the later version, is a conflict.
    ending = _version("REFUND-A", starts=datetime(2025, 1, 1, tzinfo=UTC), ends=START + SECOND)
    starting = _version("REFUND-B", starts=START, ends=None)

    assert find_conflicts([ending, starting]) == (
        Conflict(first=("REFUND-A", "1.0"), second=("REFUND-B", "1.0")),
    )


def test_a_version_that_ended_before_the_other_started_does_not_conflict_with_it() -> None:
    # As the expired version of `test_each_version_gets_its_validity_...`.
    expired = _version("REFUND", version="0.9", starts=datetime(2025, 1, 1, tzinfo=UTC), ends=START)

    assert find_conflicts([expired, REFUND]) == ()


def test_a_version_from_the_future_conflicts_once_both_are_in_effect() -> None:
    # As the future version of `test_each_version_gets_its_validity_...`: it is left out only
    # while `as_of` is before its start.
    future = _version(
        "DELIVERY", policy_key="delivery", version="2.0", starts=datetime(2027, 1, 1, tzinfo=UTC)
    )
    open_ended = _version("DELIVERY-B", policy_key="delivery", ends=None)

    assert find_conflicts([DELIVERY, future]) == ()
    assert find_conflicts([open_ended, future]) == (
        Conflict(first=("DELIVERY", "2.0"), second=("DELIVERY-B", "1.0")),
    )


def test_every_pair_of_one_policy_key_is_listed_once_in_the_order_of_the_keys() -> None:
    third = _version("REFUND-C")

    conflicts = find_conflicts([third, SECOND_REFUND, REFUND])

    assert conflicts == (
        Conflict(first=("REFUND", "1.0"), second=("REFUND-B", "1.0")),
        Conflict(first=("REFUND", "1.0"), second=("REFUND-C", "1.0")),
        Conflict(first=("REFUND-B", "1.0"), second=("REFUND-C", "1.0")),
    )
