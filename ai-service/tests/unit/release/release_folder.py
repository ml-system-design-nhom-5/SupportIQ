"""A release folder for tests: a few bytes per asset file, and a manifest that names them.

The files are fakes, not model weights. The index holds the files of the encoder, as a real
release does, and the KB holds no document, as the first release does (ADR-0021, KB
ingestion, statement 5).
"""

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from supportiq_ai_service.release.manifest import MANIFEST_FORMAT
from tests.unit.release.fakes import EXAMPLE_VERSIONS

MANIFEST_FILE_NAME = "release-manifest.json"
# The files of each asset, by path in the release folder.
ASSET_FILES: dict[str, dict[str, bytes]] = {
    "model": {
        "model/model.safetensors": b"fake weights of the intent model\n",
        "model/config.json": b'{"num_labels": 46}\n',
        "model/tokenizer.json": b'{"fake": "tokenizer"}\n',
    },
    "kb": {"kb/kb.json": b'{"documents": []}\n'},
    "mapping": {"mapping/document-intents.json": b'{"documents": []}\n'},
    "prompts": {"prompts/drafting.txt": b"A fake prompt template.\n"},
    "routing": {"routing/routing.json": b'{"fake": "routing"}\n'},
    "index": {
        "index/encoder/model.safetensors": b"fake weights of the encoder\n",
        "index/encoder/config.json": b'{"fake": "encoder"}\n',
        "index/encoder/1_Pooling/config.json": b'{"pooling_mode_cls_token": true}\n',
    },
}
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

type ManifestDocument = dict[str, Any]


def manifest_document(*, gate_run: bool = True) -> ManifestDocument:
    """Build the manifest of the files of `ASSET_FILES`, with their real checksums.

    Args:
        gate_run: Whether the manifest links a passing gate run; False for a candidate.

    Returns:
        The manifest as JSON data, which a test may change before writing it.
    """
    assets: ManifestDocument = {
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
        for name, files in ASSET_FILES.items()
    }
    assets["routing"]["model_version"] = ASSET_VERSIONS["model"]
    return {
        "format": MANIFEST_FORMAT,
        "release_id": EXAMPLE_VERSIONS.release_id,
        "assets": assets,
        "gate_run": GATE_RUN if gate_run else None,
    }


def write_release(
    folder: Path,
    *,
    gate_run: bool = True,
    change: Callable[[ManifestDocument], None] | None = None,
) -> Path:
    """Write every asset file and the manifest into a folder.

    Args:
        folder: An empty folder.
        gate_run: Whether the manifest links a passing gate run; False for a candidate.
        change: A change to make to the manifest before it is written.

    Returns:
        The path of the manifest.
    """
    for files in ASSET_FILES.values():
        for path, content in files.items():
            target = folder / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
    document = manifest_document(gate_run=gate_run)
    if change is not None:
        change(document)
    manifest_path = folder / MANIFEST_FILE_NAME
    manifest_path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return manifest_path
