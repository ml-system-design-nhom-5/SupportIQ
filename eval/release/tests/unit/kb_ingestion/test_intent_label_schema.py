"""The intent labels come from the contract, and a schema of another shape stops the run."""

import os
from pathlib import Path

import pytest

from supportiq_release.kb_ingestion.adapters import (
    IntentLabelSchemaInvalidError,
    IntentLabelSchemaProblem,
    read_intent_labels,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
INTENT_LABEL_SCHEMA = REPOSITORY_ROOT / "contracts" / "schemas" / "IntentLabel.yaml"
# The 46 Bitext labels (glossary, Intent).
BITEXT_LABEL_COUNT = 46

needs_file_permissions = pytest.mark.skipif(
    not hasattr(os, "geteuid") or os.geteuid() == 0,
    reason="root reads every file, whatever its permissions",
)


def _refusal(path: Path) -> IntentLabelSchemaInvalidError:
    with pytest.raises(IntentLabelSchemaInvalidError) as refused:
        read_intent_labels(path)
    return refused.value


def test_the_schema_of_the_contract_gives_the_46_labels() -> None:
    labels = read_intent_labels(INTENT_LABEL_SCHEMA)

    assert len(labels) == BITEXT_LABEL_COUNT
    assert {"track_order", "request_refund", "human_agent", "wrong_item"} <= labels


def test_a_schema_of_the_expected_shape_gives_its_labels(tmp_path: Path) -> None:
    path = tmp_path / "IntentLabel.yaml"
    path.write_text("description: x\ntype: string\nenum:\n  - track_order\n  - wrong_item\n")

    assert read_intent_labels(path) == {"track_order", "wrong_item"}


@pytest.mark.parametrize(
    "text",
    [
        pytest.param("type: string\n", id="no-enum"),
        pytest.param("enum:\n", id="no-label"),
        pytest.param("enum:\n  - a\nenum:\n  - b\n", id="two-enums"),
        pytest.param("enum:\n  - track_order\n  - track_order\n", id="label-twice"),
        pytest.param("enum:\n  - track_order\ndescription: more\n", id="line-after-labels"),
        pytest.param("enum:\n  - Track Order\n", id="not-a-label"),
        pytest.param("enum: [track_order]\n", id="flow-style"),
    ],
)
def test_a_schema_of_another_shape_stops_the_run(tmp_path: Path, text: str) -> None:
    path = tmp_path / "IntentLabel.yaml"
    path.write_text(text)

    refused = _refusal(path)

    assert (refused.file_name, refused.problem) == (
        "IntentLabel.yaml",
        IntentLabelSchemaProblem.SHAPE_INVALID,
    )


def test_a_missing_schema_stops_the_run(tmp_path: Path) -> None:
    refused = _refusal(tmp_path / "IntentLabel.yaml")

    assert refused.problem is IntentLabelSchemaProblem.NOT_A_REGULAR_FILE


def test_a_schema_that_is_a_link_stops_the_run(tmp_path: Path) -> None:
    path = tmp_path / "IntentLabel.yaml"
    path.symlink_to(INTENT_LABEL_SCHEMA)

    assert _refusal(path).problem is IntentLabelSchemaProblem.NOT_A_REGULAR_FILE


def test_a_schema_that_is_not_utf_8_stops_the_run_with_a_typed_error(tmp_path: Path) -> None:
    path = tmp_path / "IntentLabel.yaml"
    path.write_bytes(b"enum:\n  - track_order\xff\n")

    assert _refusal(path).problem is IntentLabelSchemaProblem.UNREADABLE


@needs_file_permissions
def test_a_schema_that_cannot_be_read_stops_the_run_with_a_typed_error(tmp_path: Path) -> None:
    path = tmp_path / "IntentLabel.yaml"
    path.write_text("enum:\n  - track_order\n")
    path.chmod(0)

    try:
        refused = _refusal(path)
    finally:
        path.chmod(0o600)

    assert refused.problem is IntentLabelSchemaProblem.UNREADABLE
