"""KB v2 admits 0 versions and quarantines 17, each with its reasons (ADR-0021, Validation).

The run reads `data/raw/kb/v2/` and `contracts/schemas/IntentLabel.yaml` only, and the files of
`eval/kb-ingestion/v2/` are exactly what it writes. Issue #13 accepts the quarantine (DATA-13),
so the run names it with `--accepted-quarantine` and succeeds.
"""

import hashlib
import json
from pathlib import Path

import pytest

from supportiq_release.composition_root import cli

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
RAW_KB_V2 = REPOSITORY_ROOT / "data" / "raw" / "kb" / "v2"
INTENT_LABEL_SCHEMA = REPOSITORY_ROOT / "contracts" / "schemas" / "IntentLabel.yaml"
COMMITTED_OUTPUT = REPOSITORY_ROOT / "eval" / "kb-ingestion" / "v2"
FILES = ("kb.json", "document-intents.json", "ingestion-report.json")
# The issue that reviewed and accepted the quarantine of KB v2 (DATA-13).
ISSUE = "https://github.com/ml-system-design-nhom-5/SupportIQ/issues/13"
NO_POLICY_KEY = [{"code": "missing_field", "field": "policy_key"}]
UNKNOWN_INTENT = {"code": "unknown_intent", "field": "supported_intents"}
NO_POLICY_KEY_AND_UNKNOWN_INTENT = [*NO_POLICY_KEY, UNKNOWN_INTENT]
NOT_RELEASED = [{"code": "invalid_field", "field": "version"}, {"code": "not_in_release"}]
# The 17 records of KB v2, by their position in the KB file, with their reasons.
EXPECTED_QUARANTINE = [
    ("b1000000-0000-0000-0000-000000000001", NOT_RELEASED),
    ("b1000000-0000-0000-0000-000000000002", NOT_RELEASED),
    ("b1000000-0000-0000-0000-000000000003", NOT_RELEASED),
    ("POL-RET-001", NO_POLICY_KEY),
    ("POL-RET-002", NO_POLICY_KEY),
    ("POL-RET-003", NO_POLICY_KEY),
    ("POL-REFUND-001", NO_POLICY_KEY),
    ("POL-REFUND-002", NO_POLICY_KEY),
    ("POL-REFUND-007", NO_POLICY_KEY),
    ("POL-ORD-001", NO_POLICY_KEY),
    ("POL-ORD-002", NO_POLICY_KEY),
    ("POL-ORD-003", NO_POLICY_KEY_AND_UNKNOWN_INTENT),
    ("POL-SHIP-001", NO_POLICY_KEY_AND_UNKNOWN_INTENT),
    ("POL-SHIP-002", NO_POLICY_KEY),
    ("POL-SHIP-004", NO_POLICY_KEY),
    ("POL-PAY-001", NO_POLICY_KEY),
    ("POL-PAY-004", NO_POLICY_KEY),
]


def _sha256(folder: Path) -> dict[str, str]:
    return {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in folder.iterdir()}


@pytest.fixture
def output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> Path:
    before = _sha256(RAW_KB_V2)
    status = cli.main(
        [
            "ingest-kb",
            "--kb-folder",
            str(RAW_KB_V2),
            "--intent-labels",
            str(INTENT_LABEL_SCHEMA),
            "--output",
            str(tmp_path / "v2"),
            "--accepted-quarantine",
            ISSUE,
        ]
    )
    assert status == cli.EXIT_SUCCESS
    assert capsys.readouterr().out == (
        "kb_version=v2 admitted=0 quarantined=17 conflicts=0 released_but_absent=0"
        " quarantine=accepted\n"
    )
    # The raw KB keeps every byte (DATA-06).
    assert _sha256(RAW_KB_V2) == before
    return tmp_path / "v2"


def test_kb_v2_admits_no_version_and_quarantines_each_with_its_reasons(output: Path) -> None:
    report = json.loads((output / "ingestion-report.json").read_text(encoding="utf-8"))

    assert report["admitted"] == []
    assert [(entry["document_id"], entry["reasons"]) for entry in report["quarantined"]] == (
        EXPECTED_QUARANTINE
    )
    assert [entry["position"] for entry in report["quarantined"]] == list(range(17))
    assert [item["sha256"] for item in report["inputs"]] == [
        _sha256(RAW_KB_V2)["kb-release.json"],
        _sha256(RAW_KB_V2)["approved_kb.v2.json"],
    ]
    assert report["quarantine_accepted_in"] == ISSUE


def test_the_committed_output_is_exactly_what_the_command_writes(output: Path) -> None:
    assert [(COMMITTED_OUTPUT / name).read_bytes() for name in FILES] == [
        (output / name).read_bytes() for name in FILES
    ]


@pytest.mark.parametrize("name", ["document-intents.json", "ingestion-report.json"])
def test_the_mapping_and_the_report_hold_no_text_of_kb_v2(output: Path, name: str) -> None:
    documents = json.loads((RAW_KB_V2 / "approved_kb.v2.json").read_text(encoding="utf-8"))
    texts = [document[field] for document in documents for field in ("title", "content")]

    written = (output / name).read_text(encoding="utf-8")

    assert not any(text in written for text in texts)
