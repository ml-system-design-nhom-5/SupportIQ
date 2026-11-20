"""The interface mappings of the reads of ai-service, which need no database.

A path parameter outside the pattern of the contract names no document, so it is `404`
(TEST-12: boundaries of length, first character, and characters outside the pattern). The
views leave out every optional field that the domain value does not have (CON-08).
"""

import json
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from app.platform.web import render_json
from app.suggestions import KbDocumentVersionNotFoundError, VersionsInUse
from app.suggestions.api.admin import to_admin_versions_view
from app.suggestions.api.console import (
    parse_kb_document_id,
    parse_kb_document_version_tag,
    to_kb_document_version_view,
)
from tests.unit.suggestions.builders import build_kb_document_version, build_versions

LONGEST_IDENTIFIER = "A" * 64
VALID_IDENTIFIERS = ["SAMPLE-REFUND-001", "1.0", "a_b.c-d", "7", LONGEST_IDENTIFIER]
INVALID_IDENTIFIERS = [
    "",
    LONGEST_IDENTIFIER + "A",
    ".hidden",
    "-1",
    "_a",
    "..",
    "a b",
    "a/b",
    "a%2Fb",
    "a\n",
    "tài-liệu",
]
INVALID_IDS = [
    "empty",
    "too-long",
    "leading-dot",
    "leading-dash",
    "leading-underscore",
    "dot-segment",
    "space",
    "slash",
    "percent",
    "trailing-newline",
    "non-ascii",
]
BUILD_VERSION = "880b33a"
EFFECTIVE_END_AT = datetime(2027, 1, 1, tzinfo=UTC)
LAST_REVIEWED_AT = datetime(2026, 6, 30, 12, 0, 0, 125_000, tzinfo=UTC)


@pytest.mark.parametrize("raw", VALID_IDENTIFIERS)
def test_a_path_parameter_of_the_pattern_is_read_as_it_is(raw: str) -> None:
    assert (parse_kb_document_id(raw), parse_kb_document_version_tag(raw)) == (raw, raw)


@pytest.mark.parametrize("raw", INVALID_IDENTIFIERS, ids=INVALID_IDS)
def test_a_document_id_outside_the_pattern_names_no_document(raw: str) -> None:
    with pytest.raises(KbDocumentVersionNotFoundError):
        parse_kb_document_id(raw)


@pytest.mark.parametrize("raw", INVALID_IDENTIFIERS, ids=INVALID_IDS)
def test_a_version_outside_the_pattern_names_no_version(raw: str) -> None:
    with pytest.raises(KbDocumentVersionNotFoundError):
        parse_kb_document_version_tag(raw)


def test_an_open_ended_document_version_without_a_review_date_leaves_both_out() -> None:
    view = to_kb_document_version_view(build_kb_document_version())

    assert json.loads(render_json(view)) == {
        "document_id": "SAMPLE-REFUND-001",
        "version": "1.0",
        "title": "Sample refund document",
        "body": "This is sample text. It is not KB content and not a policy.",
        "policy_key": "sample_refund_review",
        "effective_start_at": "2026-01-01T00:00:00Z",
        "owner": "Policy owner",
        "source": "Sample source document",
    }


def test_a_document_version_with_an_end_and_a_review_date_carries_both() -> None:
    document = replace(
        build_kb_document_version(),
        effective_end_at=EFFECTIVE_END_AT,
        last_reviewed_at=LAST_REVIEWED_AT,
    )

    view = json.loads(render_json(to_kb_document_version_view(document)))

    assert (view["effective_end_at"], view["last_reviewed_at"]) == (
        "2027-01-01T00:00:00Z",
        "2026-06-30T12:00:00.125000Z",
    )


def test_the_versions_in_use_without_ai_service_hold_only_the_build_version() -> None:
    view = to_admin_versions_view(VersionsInUse(BUILD_VERSION, None))

    assert json.loads(render_json(view)) == {
        "backend_version": BUILD_VERSION,
        "ai_service_status": "unavailable",
    }


def test_the_versions_in_use_with_ai_service_hold_every_asset_version() -> None:
    view = to_admin_versions_view(VersionsInUse(BUILD_VERSION, build_versions()))

    assert json.loads(render_json(view)) == {
        "backend_version": BUILD_VERSION,
        "ai_service_status": "available",
        "ai_service_versions": {
            "release_id": "release-sample",
            "model_version": "intent-model-sample-1",
            "kb_version": "kb-sample-1",
            "mapping_version": "mapping-sample-1",
            "prompt_version": "prompts-sample-1",
            "routing_version": "routing-sample-1",
            "index_version": "index-sample-1",
        },
    }
