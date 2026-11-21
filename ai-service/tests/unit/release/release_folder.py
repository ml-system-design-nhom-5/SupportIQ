"""A release folder for tests: the files of each asset, and a manifest that names them.

The weights are a few fake bytes, not a model. Every other file holds its interim format, so the
reader of each asset accepts it. The index holds the files of the encoder, as a real release
does, and the KB holds no document, as the first release does (ADR-0021, KB ingestion,
statement 5). The routing values are test values, never tuned ones.
"""

import hashlib
import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import pytest

from app.intent import INTENT_LABELS
from app.intent.adapters.model_artifact import MODEL_ARTIFACT_FORMAT
from app.release.manifest import (
    MANIFEST_FORMAT,
    ReleaseInvalidError,
    ReleaseInvalidReason,
    VerifiedReleaseSource,
    verify_release,
)
from app.retrieval.adapters.index_file import INDEX_FORMAT
from app.retrieval.adapters.kb_file import KB_FORMAT
from app.suggestions.adapters.mapping_file import MAPPING_FORMAT
from app.suggestions.adapters.routing_file import ROUTING_FORMAT
from tests.unit.release.fakes import EXAMPLE_VERSIONS

type JsonDocument = dict[str, Any]
# The files of each asset, by path in the release folder; None removes a file.
type AssetFileChanges = Mapping[str, Mapping[str, bytes | None]]

MANIFEST_FILE_NAME = "release-manifest.json"
ASSET_VERSIONS = {
    "model": EXAMPLE_VERSIONS.model_version,
    "kb": EXAMPLE_VERSIONS.kb_version,
    "mapping": EXAMPLE_VERSIONS.mapping_version,
    "prompts": EXAMPLE_VERSIONS.prompt_version,
    "routing": EXAMPLE_VERSIONS.routing_version,
    "index": EXAMPLE_VERSIONS.index_version,
}
GATE_RUN = {
    "run_id": "gate-run-sample-1",
    "outcome": "passed",
    "record": "eval/runs/gate-run-sample-1/report.json",
    "record_sha256": hashlib.sha256(b"a fake gate record\n").hexdigest(),
}


def json_file(document: JsonDocument) -> bytes:
    """Encode a document as the content of a JSON file.

    Args:
        document: The document.

    Returns:
        The content, in UTF-8 with a final newline.
    """
    return (json.dumps(document, indent=2) + "\n").encode()


ARTIFACT_DOCUMENT: JsonDocument = {
    "format": MODEL_ARTIFACT_FORMAT,
    "model_version": EXAMPLE_VERSIONS.model_version,
    "preprocessing": {"max_length": 64, "padding": "max_length", "truncation": True},
    "training_data_manifest_sha256": hashlib.sha256(b"a fake data manifest\n").hexdigest(),
    "metrics_summary": {"run_id": "train-run-sample-1", "metrics": {"macro_f1": 0.5}},
    "calibration": None,
}
MODEL_CONFIG_DOCUMENT: JsonDocument = {
    "num_labels": len(INTENT_LABELS),
    "id2label": {str(output): label for output, label in enumerate(INTENT_LABELS)},
    "architectures": ["FakeForSequenceClassification"],
}
KB_DOCUMENT: JsonDocument = {
    "format": KB_FORMAT,
    "kb_version": EXAMPLE_VERSIONS.kb_version,
    "documents": [],
}
# One KB document version, which a test adds to the KB that holds none.
KB_ENTRY: JsonDocument = {
    "document_id": "SAMPLE-REFUND-001",
    "version": "1.0",
    "title": "A fake refund policy",
    "body": "A fake refund policy for tests, which states no real rule.",
    "policy_key": "refund_window",
    "effective_start_at": "2026-01-01T00:00:00Z",
    "effective_end_at": "2026-12-31T23:59:59Z",
    "owner": "policy_owner",
    "source": "fake-kb.json, KB version kb-sample-1",
}
MAPPING_DOCUMENT: JsonDocument = {
    "format": MAPPING_FORMAT,
    "version": EXAMPLE_VERSIONS.mapping_version,
    "kb_version": EXAMPLE_VERSIONS.kb_version,
    "documents": [],
}
ROUTING_DOCUMENT: JsonDocument = {
    "format": ROUTING_FORMAT,
    "version": EXAMPLE_VERSIONS.routing_version,
    "model_version": EXAMPLE_VERSIONS.model_version,
    "min_top_probability": 0.5,
    "min_top_two_gap": 0.1,
    "rerank_weight": 0.2,
    "high_band_min_probability": 0.9,
    "sensitive_intents": ["request_refund", "payment_issue"],
    "sensitive_intent_min_probability": 0.2,
    "sensitive_terms": [
        {"term": "fake legal term", "category": "legal_claim"},
        {"term": "fake fraud term", "category": "suspected_fraud"},
    ],
}
INDEX_DOCUMENT: JsonDocument = {
    "format": INDEX_FORMAT,
    "version": EXAMPLE_VERSIONS.index_version,
    "kb_version": EXAMPLE_VERSIONS.kb_version,
    "encoder": {
        "name": "fake/encoder",
        "directory": "index/encoder",
        "query_prefix": "A fake query prefix: ",
        "max_length": 128,
    },
    "chunking": {"max_tokens": 100, "overlap_tokens": 10},
    "relevance_min_score": 0.5,
}
# The files of each asset, by path in the release folder.
ASSET_FILES: dict[str, dict[str, bytes]] = {
    "model": {
        "model/artifact.json": json_file(ARTIFACT_DOCUMENT),
        "model/model.safetensors": b"fake weights of the intent model\n",
        "model/config.json": json_file(MODEL_CONFIG_DOCUMENT),
        "model/tokenizer.json": b'{"fake": "tokenizer"}\n',
        "model/tokenizer_config.json": b'{"tokenizer_class": "FakeTokenizer"}\n',
    },
    "kb": {"kb/kb.json": json_file(KB_DOCUMENT)},
    "mapping": {"mapping/document-intents.json": json_file(MAPPING_DOCUMENT)},
    "prompts": {
        "prompts/drafting-system.txt": b"A fake system prompt for tests.\n",
        "prompts/drafting-requires-authority.txt": b"A fake prompt for authority.\n",
    },
    "routing": {"routing/routing.json": json_file(ROUTING_DOCUMENT)},
    "index": {
        "index/index.json": json_file(INDEX_DOCUMENT),
        "index/encoder/model.safetensors": b"fake weights of the encoder\n",
        "index/encoder/config.json": b'{"fake": "encoder"}\n',
        "index/encoder/tokenizer.json": b'{"fake": "encoder tokenizer"}\n',
        "index/encoder/tokenizer_config.json": b'{"tokenizer_class": "FakeEncoderTokenizer"}\n',
        "index/encoder/1_Pooling/config.json": b'{"pooling_mode_cls_token": true}\n',
    },
}


def with_changes(changes: AssetFileChanges) -> dict[str, dict[str, bytes]]:
    """Return the files of `ASSET_FILES` with some files replaced, added, or removed.

    Args:
        changes: The new content of each changed file, by asset and path; None removes it.

    Returns:
        The files of each asset.
    """
    assets = {name: dict(files) for name, files in ASSET_FILES.items()}
    for name, files in changes.items():
        for path, content in files.items():
            if content is None:
                del assets[name][path]
            else:
                assets[name][path] = content
    return assets


def manifest_document(
    *, gate_run: bool = True, assets: Mapping[str, Mapping[str, bytes]] = ASSET_FILES
) -> JsonDocument:
    """Build the manifest of the files of each asset, with their real checksums.

    Args:
        gate_run: Whether the manifest links a passing gate run; False for a candidate.
        assets: The files of each asset.

    Returns:
        The manifest as JSON data, which a test may change before writing it.
    """
    manifest_assets: JsonDocument = {
        name: {
            "version": ASSET_VERSIONS[name],
            "files": [
                {
                    "path": path,
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "size_bytes": len(content),
                }
                for path, content in files.items()
            ],
        }
        for name, files in assets.items()
    }
    manifest_assets["routing"]["model_version"] = ASSET_VERSIONS["model"]
    return {
        "format": MANIFEST_FORMAT,
        "release_id": EXAMPLE_VERSIONS.release_id,
        "assets": manifest_assets,
        "gate_run": GATE_RUN if gate_run else None,
    }


def write_release(
    folder: Path,
    *,
    gate_run: bool = True,
    change: Callable[[JsonDocument], None] | None = None,
    assets: Mapping[str, Mapping[str, bytes]] = ASSET_FILES,
) -> Path:
    """Write every asset file and the manifest into a folder.

    Args:
        folder: An empty folder.
        gate_run: Whether the manifest links a passing gate run; False for a candidate.
        change: A change to make to the manifest before it is written.
        assets: The files of each asset.

    Returns:
        The path of the manifest.
    """
    for files in assets.values():
        for path, content in files.items():
            target = folder / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
    document = manifest_document(gate_run=gate_run, assets=assets)
    if change is not None:
        change(document)
    manifest_path = folder / MANIFEST_FILE_NAME
    manifest_path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return manifest_path


def asset_refusal(read: Callable[[], object]) -> ReleaseInvalidError:
    """Run the reading of an asset that must refuse it.

    Args:
        read: The reading.

    Returns:
        The refusal, whose reason is `asset_invalid`.
    """
    with pytest.raises(ReleaseInvalidError) as raised:
        read()
    assert raised.value.reason is ReleaseInvalidReason.ASSET_INVALID
    return raised.value


def verified_release(
    folder: Path, changes: AssetFileChanges | None = None
) -> VerifiedReleaseSource:
    """Write a release with some files changed, and check it as `ai-service serve` does.

    Args:
        folder: An empty folder.
        changes: The new content of each changed file, by asset and path; None removes it.

    Returns:
        The source of the checked release, whose manifest matches the changed files.
    """
    return verify_release(write_release(folder, assets=with_changes(changes or {})))
