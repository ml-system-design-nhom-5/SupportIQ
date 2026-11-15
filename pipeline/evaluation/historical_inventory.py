"""Authoritative historical corpus inventory loader and anti-leakage verification.

Provides immutable, fail-closed loading and integrity verification of antecedent
datasets, benchmarks, evaluations, and audit files frozen as-of 2026-11-13 (commit 16b01eb).
Ensures holdout evaluation novelty is measured strictly against genuine antecedent exposure
rather than downstream evaluation result exports, and transparently handles UTF-8 BOM encoding.
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INVENTORY_PATH = Path(__file__).resolve().parent / "historical_as_of_inventory.json"


class HistoricalCorpusIntegrityError(RuntimeError):
    """Raised when an antecedent historical corpus input is missing or tampered."""


def read_json_safe(path: Path | str) -> Any:
    """Read JSON document transparently handling UTF-8 BOM if present without modifying disk bytes."""
    path = Path(path)
    content = path.read_text(encoding="utf-8-sig")
    return json.loads(content)


def read_jsonl_safe(path: Path | str) -> list[dict[str, Any]]:
    """Read JSONL document transparently handling UTF-8 BOM if present without modifying disk bytes."""
    path = Path(path)
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out


def _compute_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest().lower()


def load_historical_corpus_inventory(
    inventory_path: Path | None = None,
    repo_root: Path | None = None,
    *,
    verify_hashes: bool = True,
) -> dict[str, Any]:
    """Load and validate the immutable antecedent historical corpus inventory fail-closed.

    Raises:
        HistoricalCorpusIntegrityError: If any inventory file is missing or its SHA-256
            differs from the frozen manifest.
    """
    inv_path = inventory_path or DEFAULT_INVENTORY_PATH
    root = repo_root or REPO_ROOT

    if not inv_path.is_file():
        raise HistoricalCorpusIntegrityError(f"Historical corpus inventory not found: {inv_path}")

    inventory = read_json_safe(inv_path)
    corpus_files = inventory.get("corpus_files", [])

    if verify_hashes:
        missing: list[str] = []
        mismatched: list[tuple[str, str, str]] = []

        for entry in corpus_files:
            rel = entry["path"]
            expected_sha = entry["sha256"]
            full_path = root / rel

            if not full_path.is_file():
                missing.append(rel)
                continue

            actual_sha = _compute_sha256(full_path)
            if actual_sha != expected_sha:
                mismatched.append((rel, expected_sha, actual_sha))

        if missing or mismatched:
            err_parts = []
            if missing:
                err_parts.append(f"Missing antecedent files ({len(missing)}): {missing[:5]}")
            if mismatched:
                err_parts.append(
                    f"Mismatched antecedent file hashes ({len(mismatched)}): {[(m[0], m[1][:8], m[2][:8]) for m in mismatched[:5]]}"
                )
            raise HistoricalCorpusIntegrityError(
                "Historical corpus integrity violation; antecedent inputs have been mutated or deleted:\n"
                + "\n".join(err_parts)
            )

    return inventory


def _walk_obj(obj: Any, out: list[str]) -> None:
    """Extract candidate query/inquiry text strings from nested dict/list structures."""
    if isinstance(obj, dict):
        for k in ("text", "query", "instruction", "message", "user_query"):
            v = obj.get(k)
            if isinstance(v, str) and len(v.strip()) >= 8:
                out.append(v.strip())
        for v in obj.values():
            if isinstance(v, (dict, list)):
                _walk_obj(v, out)
    elif isinstance(obj, list):
        for item in obj:
            _walk_obj(item, out)


def _walk_obj_with_source(obj: Any, source: str, out: list[tuple[str, str]]) -> None:
    """Extract (source, text) pairs from nested dict/list structures."""
    if isinstance(obj, dict):
        for k in ("text", "query", "instruction", "message", "user_query"):
            v = obj.get(k)
            if isinstance(v, str) and len(v.strip()) >= 8:
                out.append((source, v.strip()))
        for v in obj.values():
            if isinstance(v, (dict, list)):
                _walk_obj_with_source(v, source, out)
    elif isinstance(obj, list):
        for item in obj:
            _walk_obj_with_source(item, source, out)


def collect_historical_corpus_prompts(
    inventory_path: Path | None = None,
    repo_root: Path | None = None,
    *,
    verify_hashes: bool = True,
    exclude_dirs: list[Path] | None = None,
) -> tuple[list[str], int]:
    """Collect prompt strings from the immutable antecedent inventory fail-closed.

    Returns:
        tuple[list[str], int]: (extracted_prompts, file_count)
    """
    root = repo_root or REPO_ROOT
    inv = load_historical_corpus_inventory(inventory_path, root, verify_hashes=verify_hashes)
    exclude = [d.resolve() for d in (exclude_dirs or [])]

    out: list[str] = []
    files_read = 0

    for entry in inv["corpus_files"]:
        p = root / entry["path"]
        p_resolved = p.resolve()
        if any(exc in p_resolved.parents or exc == p_resolved for exc in exclude):
            continue
        if not p.is_file() or p.stat().st_size > 50_000_000:
            continue

        try:
            if p.suffix == ".jsonl":
                for ln in p.read_text(encoding="utf-8-sig").splitlines():
                    if ln.strip():
                        _walk_obj(json.loads(ln), out)
            elif p.suffix == ".json":
                _walk_obj(json.loads(p.read_text(encoding="utf-8-sig")), out)
            elif p.suffix == ".csv":
                with p.open(encoding="utf-8-sig", newline="") as f:
                    for row in csv.DictReader(f):
                        _walk_obj(row, out)
            else:
                continue
            files_read += 1
        except Exception as exc:
            raise HistoricalCorpusIntegrityError(f"Failed to read antecedent corpus file {p}: {exc}") from exc

    return out, files_read


def collect_historical_prompt_tuples(
    inventory_path: Path | None = None,
    repo_root: Path | None = None,
    *,
    verify_hashes: bool = True,
    exclude_dirs: list[Path] | None = None,
) -> list[tuple[str, str]]:
    """Collect (source_rel_path, prompt_text) tuples from the immutable antecedent inventory."""
    root = repo_root or REPO_ROOT
    inv = load_historical_corpus_inventory(inventory_path, root, verify_hashes=verify_hashes)
    exclude = [d.resolve() for d in (exclude_dirs or [])]

    out: list[tuple[str, str]] = []

    for entry in inv["corpus_files"]:
        rel = entry["path"]
        p = root / rel
        p_resolved = p.resolve()
        if any(exc in p_resolved.parents or exc == p_resolved for exc in exclude):
            continue
        if not p.is_file() or p.stat().st_size > 50_000_000:
            continue

        try:
            if p.suffix == ".jsonl":
                for ln in p.read_text(encoding="utf-8-sig").splitlines():
                    if ln.strip():
                        _walk_obj_with_source(json.loads(ln), rel, out)
            elif p.suffix == ".json":
                _walk_obj_with_source(json.loads(p.read_text(encoding="utf-8-sig")), rel, out)
            elif p.suffix == ".csv":
                with p.open(encoding="utf-8-sig", newline="") as f:
                    for row in csv.DictReader(f):
                        _walk_obj_with_source(row, rel, out)
        except Exception as exc:
            raise HistoricalCorpusIntegrityError(f"Failed to read antecedent corpus file {p}: {exc}") from exc

    return out
