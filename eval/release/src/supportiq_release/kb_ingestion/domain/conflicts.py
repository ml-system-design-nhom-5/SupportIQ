"""The conflicts between admitted versions, by the rule of `conflicting_sources` in ai-service.

This is a copy of that rule, not an import of it, because the release command never imports
the internals of `ai-service` (ADR-0021, Where the code of `main` goes, statement 1). In
`ai-service/src/supportiq_ai_service/suggestions/domain/evidence.py` (`_in_effect` and
`_validity`), a version is in effect from `effective_start_at`, included, until
`effective_end_at`, excluded, and two versions in effect at `as_of` with one `policy_key` are
both `conflicting`. So two versions conflict at some `as_of` exactly when they share a
`policy_key` and their effective periods overlap. `tests/unit/kb_ingestion/test_conflicts.py`
holds the cases of the conflict tests of `ai-service`, so a change on either side shows.
"""

from collections import defaultdict
from collections.abc import Iterable
from itertools import combinations

from supportiq_release.kb_ingestion.domain.records import AdmittedVersion, Conflict


def find_conflicts(versions: Iterable[AdmittedVersion]) -> tuple[Conflict, ...]:
    """Return every pair of versions that `ai-service` would show as `conflicting`.

    Args:
        versions: The admitted versions.

    Returns:
        The conflicting pairs, ordered by their keys. A conflict is reported, never resolved
        (DATA-12, DATA-19).
    """
    by_policy_key: defaultdict[str, list[AdmittedVersion]] = defaultdict(list)
    for version in versions:
        by_policy_key[version.policy_key].append(version)
    conflicts = [
        Conflict(first=first.key, second=second.key)
        for group in by_policy_key.values()
        for first, second in combinations(sorted(group, key=lambda version: version.key), 2)
        if _overlap(first, second)
    ]
    return tuple(sorted(conflicts, key=lambda conflict: (conflict.first, conflict.second)))


def _overlap(first: AdmittedVersion, second: AdmittedVersion) -> bool:
    # Some time is in both periods: each starts before the other ends. No end is no limit.
    return (second.ends is None or first.starts < second.ends) and (
        first.ends is None or second.starts < first.ends
    )
