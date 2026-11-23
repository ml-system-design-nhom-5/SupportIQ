"""KB v2.1 admits its 14 versions, quarantines none, and has no conflict (ADR-0021, Validation).

The run reads `data/raw/kb/v2.1/` and `contracts/schemas/IntentLabel.yaml` only, and the files of
`eval/kb-ingestion/v2.1/` are exactly what it writes. Nothing is quarantined, so the run needs no
`--accepted-quarantine` and succeeds (DATA-13).
"""

import hashlib
import json
from pathlib import Path

import pytest

from supportiq_release.composition_root import cli

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
RAW_KB_V2_1 = REPOSITORY_ROOT / "data" / "raw" / "kb" / "v2.1"
KB_FILE = "approved_kb.v2.1.json"
INTENT_LABEL_SCHEMA = REPOSITORY_ROOT / "contracts" / "schemas" / "IntentLabel.yaml"
COMMITTED_OUTPUT = REPOSITORY_ROOT / "eval" / "kb-ingestion" / "v2.1"
FILES = ("kb.json", "document-intents.json", "ingestion-report.json")
# The 14 versions of the release `current-policies-v1.1`, in the order of the report.
EXPECTED_ADMITTED = [
    ("POL-ORD-001", "1.1"),
    ("POL-ORD-002", "1.1"),
    ("POL-ORD-003", "1.0"),
    ("POL-PAY-001", "1.1"),
    ("POL-PAY-004", "1.1"),
    ("POL-REFUND-001", "1.1"),
    ("POL-REFUND-002", "2.1"),
    ("POL-REFUND-007", "1.1"),
    ("POL-RET-001", "2.1"),
    ("POL-RET-002", "2.1"),
    ("POL-RET-003", "2.1"),
    ("POL-SHIP-001", "1.1"),
    ("POL-SHIP-002", "1.1"),
    ("POL-SHIP-004", "1.1"),
]
# The brand of KB v2, which KB v2.1 replaces with the simulated shop (data/raw/kb/v2.1/README.md).
BRAND_OF_KB_V2 = "tiki"


def _sha256(folder: Path) -> dict[str, str]:
    return {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in folder.iterdir()}


def _texts() -> list[str]:
    documents = json.loads((RAW_KB_V2_1 / KB_FILE).read_text(encoding="utf-8"))
    return [document[field] for document in documents for field in ("title", "content")]


@pytest.fixture
def output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> Path:
    before = _sha256(RAW_KB_V2_1)
    status = cli.main(
        [
            "ingest-kb",
            "--kb-folder",
            str(RAW_KB_V2_1),
            "--intent-labels",
            str(INTENT_LABEL_SCHEMA),
            "--output",
            str(tmp_path / "v2.1"),
        ]
    )
    assert status == cli.EXIT_SUCCESS
    assert capsys.readouterr().out == (
        "kb_version=v2.1 admitted=14 quarantined=0 conflicts=0 released_but_absent=0"
        " quarantine=accepted\n"
    )
    # The raw KB keeps every byte (DATA-06).
    assert _sha256(RAW_KB_V2_1) == before
    return tmp_path / "v2.1"


def test_kb_v2_1_admits_its_14_versions_with_no_quarantine_and_no_conflict(output: Path) -> None:
    report = json.loads((output / "ingestion-report.json").read_text(encoding="utf-8"))

    assert report["kb_version"] == "v2.1"
    assert report["kb_release"] == "current-policies-v1.1"
    assert [(entry["document_id"], entry["version"]) for entry in report["admitted"]] == (
        EXPECTED_ADMITTED
    )
    assert report["quarantined"] == report["conflicts"] == report["released_but_absent"] == []
    assert "quarantine_accepted_in" not in report
    assert [item["sha256"] for item in report["inputs"]] == [
        _sha256(RAW_KB_V2_1)["kb-release.json"],
        _sha256(RAW_KB_V2_1)[KB_FILE],
    ]


def test_the_committed_output_is_exactly_what_the_command_writes(output: Path) -> None:
    assert [(COMMITTED_OUTPUT / name).read_bytes() for name in FILES] == [
        (output / name).read_bytes() for name in FILES
    ]


@pytest.mark.parametrize("name", ["document-intents.json", "ingestion-report.json"])
def test_the_mapping_and_the_report_hold_no_text_of_kb_v2_1(output: Path, name: str) -> None:
    written = (output / name).read_text(encoding="utf-8")

    assert not any(text in written for text in _texts())


def test_no_text_of_kb_v2_1_names_the_brand_of_kb_v2(output: Path) -> None:
    served = (output / "kb.json").read_text(encoding="utf-8")

    assert BRAND_OF_KB_V2 not in served.lower()
    assert not any(BRAND_OF_KB_V2 in text.lower() for text in _texts())
