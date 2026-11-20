"""Inference backends for the intent model.

* ``torch``: the same Hugging Face stack the ML service uses (requires torch + transformers).
* ``numpy``: a pure-numpy re-implementation (npbert) so CI or a lightweight machine can evaluate
  the released weights without installing torch.  ``parity`` checks both agree.
"""
from __future__ import annotations

import ast
import hashlib
import json
import time
from pathlib import Path
from typing import Any

import numpy as np

from apps.ml_inference.preprocessing import DRAFTABLE_INTENTS, normalize_placeholders, split_clauses

REPO_ROOT = Path(__file__).resolve().parents[3]
SERVICE_FILE = REPO_ROOT / "apps" / "ml_inference" / "app.py"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def pinned_manifest() -> dict[str, str]:
    """Read EXPECTED_MANIFEST from the ML service source without importing torch/fastapi."""
    tree = ast.parse(SERVICE_FILE.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "EXPECTED_MANIFEST" for t in node.targets):
            return ast.literal_eval(node.value)
    raise RuntimeError(f"EXPECTED_MANIFEST not found in {SERVICE_FILE}")


def verify_model(model_dir: Path) -> dict[str, Any]:
    """Same acceptance checks as apps/ml_inference (checksums + 46-label bijection)."""
    manifest = pinned_manifest()
    out: dict[str, Any] = {"model_dir": str(model_dir), "pinned_model_version": manifest.get("model_version")}
    files = {k: model_dir / k for k in ("model.safetensors", "tokenizer.json", "config.json")}
    missing = [k for k, p in files.items() if not p.exists()]
    if missing:
        out.update(ok=False, error=f"missing files: {missing}")
        return out
    out["weights_sha256"] = sha256_file(files["model.safetensors"])
    out["tokenizer_sha256"] = sha256_file(files["tokenizer.json"])
    out["checksum_match"] = (out["weights_sha256"] == manifest["weights_sha256"].lower()
                             and out["tokenizer_sha256"] == manifest["tokenizer_sha256"].lower())
    cfg = json.loads(files["config.json"].read_text(encoding="utf-8"))
    id2label = {int(k): v for k, v in cfg.get("id2label", {}).items()}
    out["n_labels"] = len(id2label)
    out["label_bijection"] = set(id2label) == set(range(46)) and len(set(id2label.values())) == 46
    out["ok"] = bool(out["checksum_match"] and out["label_bijection"])
    return out


class NumpyBackend:
    name = "numpy"

    def __init__(self, model_dir: Path):
        from .npbert import DistilBertClassifier
        self.model = DistilBertClassifier(str(model_dir))
        self.id2label = self.model.id2label

    def logits(self, text: str) -> np.ndarray:
        ids, _ = self.model.tok.encode(normalize_placeholders(text))
        return self.model.logits(ids).astype(np.float64)


class TorchBackend:
    name = "torch"

    def __init__(self, model_dir: Path, max_length: int = 64):
        import torch  # noqa: F401
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
        self.torch = torch
        self.tok = AutoTokenizer.from_pretrained(str(model_dir), local_files_only=True)
        self.model = AutoModelForSequenceClassification.from_pretrained(str(model_dir), local_files_only=True).eval()
        self.id2label = {int(k): v for k, v in self.model.config.id2label.items()}
        self.max_length = max_length

    def logits(self, text: str) -> np.ndarray:
        # Mirrors apps/ml_inference/app.py: max_length=64, padding="max_length", truncation.
        enc = self.tok(normalize_placeholders(text), max_length=self.max_length, padding="max_length", truncation=True, return_tensors="pt")
        with self.torch.inference_mode():
            return self.model(**enc).logits[0].double().cpu().numpy()


def load_backend(model_dir: Path, preferred: str = "auto"):
    """``torch`` must succeed; ``auto`` tries torch then falls back to numpy (reason kept on the backend)."""
    fallback_reason = None
    if preferred in ("auto", "torch"):
        try:
            return TorchBackend(model_dir)
        except Exception as e:
            if preferred == "torch":
                raise
            fallback_reason = f"{type(e).__name__}: {e}"
    backend = NumpyBackend(model_dir)
    backend.fallback_reason = fallback_reason
    return backend


class EnsembleBackend:
    """Averages the logits of several members with the same label order (docs/design/intent-model-v1.2.md)."""

    def __init__(self, members: list):
        if not members:
            raise ValueError("an ensemble needs at least one member")
        if any(m.id2label != members[0].id2label for m in members):
            raise ValueError("ensemble members must share one label order")
        self.members = members
        self.id2label = members[0].id2label
        self.name = f"ensemble[{len(members)}x{members[0].name}]"

    def logits(self, text: str) -> np.ndarray:
        return np.mean([m.logits(text) for m in self.members], axis=0)


def load_model_dirs(model_dirs: str, repo_root: Path, preferred: str = "auto"):
    """One backend for a single directory, an ``EnsembleBackend`` for a comma-separated list."""
    dirs = [d.strip() for d in model_dirs.split(",") if d.strip()]
    backends = [load_backend(repo_root / d, preferred) for d in dirs]
    return backends[0] if len(backends) == 1 else EnsembleBackend(backends)


class IntentModel:
    """Turns raw logits into the same fields the ML service returns (+ entropy)."""

    def __init__(self, backend):
        self.backend = backend
        self.id2label = backend.id2label
        self.latencies_ms: list[float] = []

    def predict(self, text: str, k: int = 3, record_latency: bool = True) -> dict[str, Any]:
        t0 = time.perf_counter()
        z = self.backend.logits(text)
        if record_latency:
            self.latencies_ms.append((time.perf_counter() - t0) * 1000.0)
        p = np.exp(z - z.max())
        p /= p.sum()
        order = np.argsort(-p)
        return {
            "intent": self.id2label[int(order[0])],
            "confidence": float(p[order[0]]),
            "margin": float(p[order[0]] - p[order[1]]),
            "top_k": [[self.id2label[int(j)], round(float(p[j]), 4)] for j in order[:k]],
            "entropy": float(-(p * np.log(p + 1e-12)).sum()),
            "scope_probability": float(sum(p[i] for i, label in self.id2label.items() if label in DRAFTABLE_INTENTS)),
        }

    def predict_clauses(self, text: str, min_words: int, max_clauses: int,
                        request_clauses_only: bool = False) -> list[dict[str, Any]] | None:
        """Per-clause intent and confidence, as ``ModelContainer.predict`` returns them (multi-request detection).

        Each clause is padded to the same length as in the service batch, so its logits match the batched ones.
        """
        clauses = split_clauses(text, min_words=min_words, max_clauses=max_clauses,
                                request_clauses_only=request_clauses_only)
        if not clauses:
            return None
        return [{"intent": p["intent"], "confidence": p["confidence"]}
                for p in (self.predict(c, record_latency=False) for c in clauses)]


def parity(model_dir: Path, texts: list[str], tol: float = 1e-3) -> dict[str, Any]:
    """Compare numpy vs torch logits; requires torch to be installed."""
    a, b = NumpyBackend(model_dir), TorchBackend(model_dir)
    diffs, flips = [], 0
    for t in texts:
        za, zb = a.logits(t), b.logits(t)
        diffs.append(float(np.max(np.abs(za - zb))))
        flips += int(np.argmax(za) != np.argmax(zb))
    return {"n": len(texts), "max_abs_logit_diff": max(diffs), "argmax_flips": flips, "ok": max(diffs) <= tol and flips == 0}
