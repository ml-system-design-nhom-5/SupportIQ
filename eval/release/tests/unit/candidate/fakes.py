"""Fake sources of the six assets and their spec, with synthetic bytes only (TEST-18).

`verify_candidate` checks the manifest and the bytes of every file, not the formats of the
assets, so each fake file holds a short marker. Only the KB file and the mapping hold the
version fields that `build-candidate` reads. The model and the index are folders, with a
nested folder for the encoder; the other assets are single files.
"""

import json
from pathlib import Path

RELEASE_ID = "fake-release-1"
MODEL_VERSION = "fake-model-1"
KB_VERSION = "v9"
MAPPING_VERSION = "v9"
SOURCE_FILES = {
    "model/artifact.json": b'{"fake": "artifact"}\n',
    "model/model.safetensors": b"fake weights",
    "model/tokenizer.json": b'{"fake": "tokenizer"}\n',
    "kb.json": b'{"format": "supportiq-kb/interim-1", "kb_version": "v9", "documents": []}\n',
    "document-intents.json": (
        b'{"format": "supportiq-document-intents/interim-1", "version": "v9",'
        b' "kb_version": "v9", "documents": []}\n'
    ),
    "prompts/drafting-system.txt": b"A fake system prompt.\n",
    "prompts/drafting-requires-authority.txt": b"A fake authority prompt.\n",
    "routing.json": b'{"fake": "routing"}\n',
    "index/index.json": b'{"fake": "index"}\n',
    "index/encoder/model.safetensors": b"fake encoder weights",
}
# The path of each source file in the release folder.
RELEASE_FILES = {
    "model/artifact.json": "model/artifact.json",
    "model/model.safetensors": "model/model.safetensors",
    "model/tokenizer.json": "model/tokenizer.json",
    "kb.json": "kb/kb.json",
    "document-intents.json": "mapping/document-intents.json",
    "prompts/drafting-system.txt": "prompts/drafting-system.txt",
    "prompts/drafting-requires-authority.txt": "prompts/drafting-requires-authority.txt",
    "routing.json": "routing/routing.json",
    "index/index.json": "index/index.json",
    "index/encoder/model.safetensors": "index/encoder/model.safetensors",
}


def asset_entries() -> dict[str, dict[str, str]]:
    """Return the six asset entries of a valid spec.

    Returns:
        Each asset with its version, source, and path.
    """
    return {
        "model": {"version": MODEL_VERSION, "source": "model", "path": "model"},
        "kb": {"version": KB_VERSION, "source": "kb.json", "path": "kb/kb.json"},
        "mapping": {
            "version": MAPPING_VERSION,
            "source": "document-intents.json",
            "path": "mapping/document-intents.json",
        },
        "prompts": {"version": "fake-prompts-1", "source": "prompts", "path": "prompts"},
        "routing": {
            "version": "fake-routing-1",
            "model_version": MODEL_VERSION,
            "source": "routing.json",
            "path": "routing/routing.json",
        },
        "index": {"version": "fake-index-1", "source": "index", "path": "index"},
    }


def spec_document(**assets: dict[str, str]) -> dict[str, object]:
    """Return a valid spec, with some asset entries replaced.

    Args:
        **assets: The asset entries to replace.

    Returns:
        The spec.
    """
    return {
        "format": "supportiq-release-spec/interim-1",
        "release_id": RELEASE_ID,
        "assets": {**asset_entries(), **assets},
    }


def write_sources(base: Path) -> Path:
    """Write the fake sources into a folder.

    Args:
        base: An existing folder.

    Returns:
        The folder.
    """
    for name, data in SOURCE_FILES.items():
        path = base / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return base


def write_spec(base: Path, document: object | None = None) -> Path:
    """Write a spec next to the fake sources.

    Args:
        base: The folder of the sources.
        document: The spec; a valid one when None.

    Returns:
        The spec file.
    """
    path = base / "release-spec.json"
    path.write_text(json.dumps(spec_document() if document is None else document))
    return path
