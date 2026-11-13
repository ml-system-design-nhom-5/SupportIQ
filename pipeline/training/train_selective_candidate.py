"""Bounded selective-intent candidate training, calibration & evaluation for Task A.

Implements two predeclared, uniform-KL-free candidate fits inside one shared
<= 1800s training budget:
  1. Fit 1 (`selective_head`): Clean 46-class cross-entropy fine-tuning on
     Bitext 46-label train replay + positive domain train families ONLY (no
     negative KL flattening), paired with a separately trained L2-regularized
     binary selective rejector (`cls_l2_plus_logit_geometry_v1`, 776 dims)
     plus constrained scalar temperature calibration (`T >= 1.0`).
  2. Fit 2 (`selective_margin`): Confidence-preserving selective fine-tuning
     using clean cross-entropy on positives and a bounded supported-11 + energy
     margin hinge on negatives ONLY (never flattening confident positives),
     paired with constrained scalar temperature calibration (`T >= 1.0`) and a
     lightweight `logit_geometry_v1` (8-dim) binary rejector.

Selects the winning candidate strictly on isolated calibration splits, locks its
weights, `calibration_manifest.json`, and `candidate_provenance_manifest.json`
BEFORE executing one post-decision evaluation across the new holdout, Bitext
46-label test split, ml_noise_420, ml_oos_80, and frozen regression suites.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import math
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
import torch
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score
from sklearn.preprocessing import StandardScaler
from torch.utils.data import DataLoader, Dataset
from transformers import AutoModelForSequenceClassification, AutoTokenizer, get_linear_schedule_with_warmup

from apps.ai_service.engine import Engine
from apps.core_backend.intent.routing import (
    ESCALATED_34_INTENTS,
    IntentPrediction,
    RoutingContext,
    STANDARD_INTENTS_46,
    SUPPORTED_12_INTENTS,
    decide_route,
    load_policy_v2,
)
from apps.core_backend.retrieval.adapter import RetrievalAdapter
from pipeline.evaluation.autoeval import metrics as M
from pipeline.evaluation.classifier_acceptance_gate import (
    KNOWN_UNINJECTED_ACCEPTANCE_IDS,
    KNOWN_UNINJECTED_FINAL_IDS,
    run_classifier_acceptance_gate,
)
from pipeline.preparation.utils import CORE_PRODUCT_INTENTS, compute_sha256
from pipeline.training.selective_domain_data import export_selective_datasets
from pipeline.training.train_domain_candidate import (
    MAX_TRAINING_BUDGET_SECONDS,
    VerifiedOriginalLineage,
    _OfflineSpyLLM,
    build_replay_and_domain_train_df,
    collect_compute_and_model_inventory,
    fit_temperature_on_calibration_logits,
    verify_original_46_label_lineage,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SUPPORTED_11_DRAFT_INTENTS: Tuple[str, ...] = tuple(
    i for i in SUPPORTED_12_INTENTS if i != "human_agent"
)
LOGIT_GEOMETRY_FEATURE_NAMES: Tuple[str, ...] = (
    "raw_max_prob",
    "raw_margin",
    "raw_entropy",
    "cal_max_prob",
    "cal_margin",
    "cal_entropy",
    "logit_max",
    "logit_logsumexp",
)
CALIBRATION_SCHEMA_VERSION = "selective_calibration.v1"


@dataclass(frozen=True)
class SelectiveRejectorParams:
    """Pure-JSON linear rejector parameters serialized in calibration_manifest.json."""

    enabled: bool
    feature_spec: str  # "cls_l2_plus_logit_geometry_v1" | "logit_geometry_v1"
    feature_dim: int
    scaler_mean: List[float]
    scaler_scale: List[float]
    weights: List[float]
    bias: float
    threshold: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "type": "logistic_regression_v1",
            "feature_spec": self.feature_spec,
            "feature_dim": int(self.feature_dim),
            "feature_names_tail": list(LOGIT_GEOMETRY_FEATURE_NAMES),
            "scaler_mean": [float(x) for x in self.scaler_mean],
            "scaler_scale": [float(x) for x in self.scaler_scale],
            "weights": [float(x) for x in self.weights],
            "bias": float(self.bias),
            "threshold": float(self.threshold),
            "positive_label": "in_scope",
            "rejection_policy": "reject_draft_on_abstain",
            "abstain_score_mode": "distinct_flag_only",
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SelectiveRejectorParams":
        feature_spec = str(data["feature_spec"])
        feature_dim = int(data["feature_dim"])
        expected_dim = 776 if feature_spec == "cls_l2_plus_logit_geometry_v1" else 8
        if feature_spec not in ("cls_l2_plus_logit_geometry_v1", "logit_geometry_v1"):
            raise ValueError(f"Unsupported rejector feature_spec: {feature_spec}")
        if feature_dim != expected_dim:
            raise ValueError(f"feature_dim={feature_dim} mismatch for {feature_spec} (expected {expected_dim})")

        scaler_mean = [float(x) for x in data["scaler_mean"]]
        scaler_scale = [float(x) for x in data["scaler_scale"]]
        weights = [float(x) for x in data["weights"]]
        bias = float(data["bias"])
        threshold = float(data["threshold"])

        if len(scaler_mean) != feature_dim or len(scaler_scale) != feature_dim or len(weights) != feature_dim:
            raise ValueError("Rejector parameter vector lengths do not match feature_dim")
        if any(not math.isfinite(x) for x in scaler_mean + scaler_scale + weights + [bias, threshold]):
            raise ValueError("Rejector parameters contain non-finite float")
        if any(x <= 0.0 for x in scaler_scale):
            raise ValueError("Rejector scaler_scale must be strictly positive")
        if not (0.0 <= threshold <= 1.0):
            raise ValueError(f"Rejector threshold out of [0, 1]: {threshold}")

        return cls(
            enabled=bool(data.get("enabled", True)),
            feature_spec=feature_spec,
            feature_dim=feature_dim,
            scaler_mean=scaler_mean,
            scaler_scale=scaler_scale,
            weights=weights,
            bias=bias,
            threshold=threshold,
        )


def validate_calibration_manifest(manifest: Dict[str, Any], model_dir: Path) -> None:
    """Fail-closed validation for calibration_manifest.json artifact & parameter integrity."""
    if manifest.get("schema_version") != CALIBRATION_SCHEMA_VERSION:
        raise ValueError(f"Unexpected calibration schema_version: {manifest.get('schema_version')}")

    cal = manifest.get("calibration", {})
    temp = float(cal.get("temperature", float("nan")))
    min_temp = float(cal.get("min_temperature", 1.0))
    if not math.isfinite(temp) or temp < min_temp or temp <= 0.0:
        raise ValueError(f"Invalid calibration temperature={temp} (min_temperature={min_temp})")

    label_space = manifest.get("label_space", {})
    id2label = label_space.get("id2label", {})
    if len(id2label) != 46 or not label_space.get("valid_46_label_bijection"):
        raise ValueError("Invalid 46-label bijection in calibration_manifest")
    mapped = [id2label.get(str(i)) for i in range(46)]
    if mapped != list(STANDARD_INTENTS_46):
        raise ValueError("calibration_manifest id2label does not match canonical 46 labels")

    art_hashes = manifest.get("artifact_hashes", {})
    for fname in ("model.safetensors", "tokenizer.json", "config.json"):
        p = model_dir / fname
        if not p.is_file():
            raise FileNotFoundError(f"Missing model artifact for checksum check: {p}")
        expected_sha = str(art_hashes.get(fname, "")).lower()
        actual_sha = compute_sha256(p).lower()
        if not expected_sha or actual_sha != expected_sha:
            raise ValueError(f"Artifact checksum mismatch for {fname}: expected={expected_sha}, actual={actual_sha}")

    rej_data = manifest.get("selective_rejector")
    if rej_data is not None and rej_data.get("enabled", False):
        SelectiveRejectorParams.from_dict(rej_data)


def compute_selective_feature_matrix(
    logits: np.ndarray,
    cls_embeddings: np.ndarray,
    *,
    temperature: float,
    feature_spec: str,
) -> np.ndarray:
    """Compute exact deterministic feature vectors matching calibration_manifest.json spec."""
    logits_f = logits.astype(np.float64)
    logits_shift = logits_f - logits_f.max(axis=1, keepdims=True)
    raw_exp = np.exp(logits_shift)
    raw_probs = raw_exp / np.clip(raw_exp.sum(axis=1, keepdims=True), 1e-12, None)
    raw_sorted = np.sort(raw_probs, axis=1)[:, ::-1]
    raw_max_prob = raw_sorted[:, 0]
    raw_margin = raw_sorted[:, 0] - raw_sorted[:, 1]
    raw_entropy = -(raw_probs * np.log(np.clip(raw_probs, 1e-12, None))).sum(axis=1)

    cal_logits = logits_f / float(temperature)
    cal_shift = cal_logits - cal_logits.max(axis=1, keepdims=True)
    cal_exp = np.exp(cal_shift)
    cal_probs = cal_exp / np.clip(cal_exp.sum(axis=1, keepdims=True), 1e-12, None)
    cal_sorted = np.sort(cal_probs, axis=1)[:, ::-1]
    cal_max_prob = cal_sorted[:, 0]
    cal_margin = cal_sorted[:, 0] - cal_sorted[:, 1]
    cal_entropy = -(cal_probs * np.log(np.clip(cal_probs, 1e-12, None))).sum(axis=1)

    logit_max = logits_f.max(axis=1)
    logit_lse = logits_f.max(axis=1) + np.log(np.clip(raw_exp.sum(axis=1), 1e-12, None))

    geom = np.column_stack(
        [
            raw_max_prob,
            raw_margin,
            raw_entropy,
            cal_max_prob,
            cal_margin,
            cal_entropy,
            logit_max,
            logit_lse,
        ]
    )
    if feature_spec == "logit_geometry_v1":
        return geom
    if feature_spec == "cls_l2_plus_logit_geometry_v1":
        cls_f = cls_embeddings.astype(np.float64)
        norms = np.linalg.norm(cls_f, ord=2, axis=1, keepdims=True)
        cls_l2 = cls_f / np.clip(norms, 1e-12, None)
        return np.hstack([cls_l2, geom])
    raise ValueError(f"Unsupported feature_spec: {feature_spec}")


def score_rejector(features: np.ndarray, rejector: SelectiveRejectorParams) -> np.ndarray:
    """Evaluate pure-JSON logistic rejector in_scope_probability on feature matrix."""
    mean = np.asarray(rejector.scaler_mean, dtype=np.float64)
    scale = np.clip(np.asarray(rejector.scaler_scale, dtype=np.float64), 1e-12, None)
    w = np.asarray(rejector.weights, dtype=np.float64)
    z = ((features - mean) / scale) @ w + float(rejector.bias)
    z = np.clip(z, -40.0, 40.0)
    return 1.0 / (1.0 + np.exp(-z))


class _SelectiveTrainDataset(Dataset):
    """Tokenized training dataset retaining integer labels and binary is_negative flags."""

    def __init__(
        self,
        encodings: Dict[str, torch.Tensor],
        labels: Sequence[int],
        is_negative: Sequence[int],
    ) -> None:
        self.encodings = encodings
        self.labels = torch.tensor(list(labels), dtype=torch.long)
        self.is_negative = torch.tensor(list(is_negative), dtype=torch.long)

    def __len__(self) -> int:
        return len(self.labels)

    def __getitem__(self, idx: int) -> Dict[str, torch.Tensor]:
        item = {k: v[idx] for k, v in self.encodings.items()}
        item["labels"] = self.labels[idx]
        item["is_negative"] = self.is_negative[idx]
        return item


class SelectiveCandidateAdapter:
    """Offline Engine-compatible adapter enforcing separate raw, calibrated, and rejector signals."""

    def __init__(
        self,
        name: str,
        model_dir: Path,
        version: str,
        *,
        mode: str = "calibrated_with_rejector",
        temperature_override: Optional[float] = None,
        rejector_override: Optional[SelectiveRejectorParams] = None,
        validate_manifest: bool = True,
    ) -> None:
        if mode not in ("raw_uncalibrated", "calibrated_without_rejector", "calibrated_with_rejector"):
            raise ValueError(f"Invalid adapter evaluation mode: {mode}")

        self.name = name
        self.model_dir = Path(model_dir)
        self.version = version
        self.mode = mode
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.tokenizer = AutoTokenizer.from_pretrained(str(self.model_dir))
        self.model = AutoModelForSequenceClassification.from_pretrained(str(self.model_dir))
        self.model.to(self.device)
        self.model.eval()
        self.id2label = {int(k): v for k, v in self.model.config.id2label.items()}

        manifest_path = self.model_dir / "calibration_manifest.json"
        if manifest_path.is_file() and validate_manifest:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            validate_calibration_manifest(manifest, self.model_dir)
            self.temperature = float(manifest["calibration"]["temperature"])
            rej_raw = manifest.get("selective_rejector")
            self.rejector = (
                SelectiveRejectorParams.from_dict(rej_raw)
                if rej_raw and rej_raw.get("enabled", False)
                else None
            )
        else:
            self.temperature = 1.0 if temperature_override is None else float(temperature_override)
            self.rejector = rejector_override

        if temperature_override is not None:
            self.temperature = float(temperature_override)
        if rejector_override is not None:
            self.rejector = rejector_override

        weights_file = self.model_dir / "model.safetensors"
        if not weights_file.exists():
            weights_file = self.model_dir / "pytorch_model.bin"
        self.weights_sha256 = compute_sha256(weights_file).lower() if weights_file.exists() else ""
        tok_file = self.model_dir / "tokenizer.json"
        self.tokenizer_sha256 = compute_sha256(tok_file).lower() if tok_file.exists() else ""

    def extract_logits_and_cls(self, texts: Sequence[str], batch_size: int = 64) -> Tuple[np.ndarray, np.ndarray]:
        all_logits: List[np.ndarray] = []
        all_cls: List[np.ndarray] = []
        with torch.no_grad():
            for i in range(0, len(texts), batch_size):
                batch = list(texts[i : i + batch_size])
                enc = self.tokenizer(
                    batch,
                    max_length=64,
                    padding="max_length",
                    truncation=True,
                    return_tensors="pt",
                )
                enc = {k: v.to(self.device) for k, v in enc.items()}
                out = self.model(**enc, output_hidden_states=True)
                all_logits.append(out.logits.detach().cpu().numpy())
                all_cls.append(out.hidden_states[-1][:, 0, :].detach().cpu().numpy())
        return np.vstack(all_logits), np.vstack(all_cls)

    def predict_batch(self, texts: Sequence[str], batch_size: int = 64) -> List[Dict[str, Any]]:
        if not texts:
            return []
        logits_np, cls_np = self.extract_logits_and_cls(texts, batch_size=batch_size)
        logits_t = torch.tensor(logits_np, dtype=torch.float32)
        raw_probs = torch.softmax(logits_t, dim=-1).numpy()

        eff_temp = 1.0 if self.mode == "raw_uncalibrated" else float(self.temperature)
        cal_probs = torch.softmax(logits_t / eff_temp, dim=-1).numpy()

        in_scope_probs: Optional[np.ndarray] = None
        if self.rejector is not None and self.rejector.enabled:
            feat = compute_selective_feature_matrix(
                logits_np,
                cls_np,
                temperature=self.temperature,
                feature_spec=self.rejector.feature_spec,
            )
            in_scope_probs = score_rejector(feat, self.rejector)

        results: List[Dict[str, Any]] = []
        for idx in range(len(texts)):
            rp = raw_probs[idx]
            cp = cal_probs[idx]
            r_order = np.argsort(-rp)
            c_order = np.argsort(-cp)

            top1_idx = int(c_order[0])
            top2_idx = int(c_order[1])
            intent = self.id2label[top1_idx]
            raw_conf = float(rp[int(r_order[0])])
            raw_margin = float(rp[int(r_order[0])] - rp[int(r_order[1])])
            cal_conf = float(cp[top1_idx])
            cal_margin = float(cp[top1_idx] - cp[top2_idx])

            p_in_scope = float(in_scope_probs[idx]) if in_scope_probs is not None else 1.0
            sel_accepted = (
                bool(p_in_scope >= self.rejector.threshold)
                if (self.mode == "calibrated_with_rejector" and self.rejector is not None and self.rejector.enabled)
                else True
            )

            top_k = [
                {"intent": self.id2label[int(j)], "probability": float(cp[int(j)])}
                for j in c_order[:5]
            ]
            score_kind = (
                "uncalibrated_softmax"
                if self.mode == "raw_uncalibrated"
                else "calibrated_probability"
            )

            results.append(
                {
                    "intent": intent,
                    "confidence": raw_conf if self.mode == "raw_uncalibrated" else cal_conf,
                    "margin": raw_margin if self.mode == "raw_uncalibrated" else cal_margin,
                    "raw_confidence": raw_conf,
                    "raw_margin": raw_margin,
                    "raw_score_kind": "uncalibrated_softmax",
                    "calibrated_confidence": cal_conf,
                    "calibrated_margin": cal_margin,
                    "in_scope_probability": p_in_scope,
                    "selective_accepted": sel_accepted,
                    "rejector_threshold": float(self.rejector.threshold) if self.rejector else None,
                    "calibrated": self.mode != "raw_uncalibrated",
                    "temperature": eff_temp,
                    "top_k": top_k,
                    "score_kind": score_kind,
                    "model_mode": "trained",
                    "verified": True,
                }
            )
        return results

    def predict(self, text: str) -> Dict[str, Any]:
        return self.predict_batch([text], batch_size=1)[0]


def _engine_analyse_selective(
    engine: Engine,
    adapter: SelectiveCandidateAdapter,
    *,
    text: str,
    as_of: str = "2026-11-13T00:00:00Z",
    order_ctx: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Run Engine._analyse and apply selective rejector draft-block cleanly at routing boundary."""
    ans, meta = engine._analyse(
        {"message": text, "as_of": as_of, "order_context": order_ctx or {}}
    )
    pred = adapter.predict(text)
    if (
        adapter.mode == "calibrated_with_rejector"
        and not pred["selective_accepted"]
        and ans["routing"]["recommendation"] == "draft"
    ):
        ans = dict(ans)
        routing = dict(ans["routing"])
        routing["recommendation"] = "abstain"
        routing["action"] = "manual_fallback"
        reasons = list(routing.get("reason_codes", []))
        if "selective_rejector_abstain" not in reasons:
            reasons.append("selective_rejector_abstain")
        routing["reason_codes"] = reasons
        ans["routing"] = routing
    return ans, meta


def _train_single_fit(
    *,
    fit_name: str,
    objective_mode: str,  # "clean_positive_ce" | "selective_margin_hinge"
    base_model_dir: Path,
    output_dir: Path,
    train_texts: Sequence[str],
    train_labels: Sequence[int],
    train_is_negative: Sequence[int],
    seed: int,
    epochs: int = 2,
    batch_size: int = 32,
    lr: float = 3e-5,
) -> Dict[str, Any]:
    """Run one bounded DistilBERT fine-tuning fit."""
    t0 = time.perf_counter()
    torch.manual_seed(seed)
    np.random.seed(seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    tokenizer = AutoTokenizer.from_pretrained(str(base_model_dir))
    model = AutoModelForSequenceClassification.from_pretrained(str(base_model_dir))
    model.to(device)

    enc = tokenizer(
        list(train_texts),
        max_length=64,
        padding="max_length",
        truncation=True,
        return_tensors="pt",
    )
    ds = _SelectiveTrainDataset(enc, train_labels, train_is_negative)
    loader = DataLoader(ds, batch_size=batch_size, shuffle=True)

    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=0.01)
    total_steps = max(1, len(loader) * epochs)
    scheduler = get_linear_schedule_with_warmup(
        optimizer,
        num_warmup_steps=max(1, int(0.1 * total_steps)),
        num_training_steps=total_steps,
    )
    ce_loss = torch.nn.CrossEntropyLoss()
    sup11_indices = [STANDARD_INTENTS_46.index(i) for i in SUPPORTED_11_DRAFT_INTENTS]
    sup11_idx_t = torch.tensor(sup11_indices, dtype=torch.long, device=device)

    epoch_stats: List[Dict[str, Any]] = []
    for ep in range(1, epochs + 1):
        model.train()
        tot_loss = pos_loss_sum = neg_loss_sum = 0.0
        n_pos_batches = n_neg_batches = 0
        for batch in loader:
            optimizer.zero_grad()
            input_ids = batch["input_ids"].to(device)
            attention_mask = batch["attention_mask"].to(device)
            labels = batch["labels"].to(device)
            is_neg = batch["is_negative"].to(device)

            logits = model(input_ids=input_ids, attention_mask=attention_mask).logits
            pos_mask = is_neg == 0
            neg_mask = is_neg == 1

            loss = logits.sum() * 0.0
            if pos_mask.any():
                lp = ce_loss(logits[pos_mask], labels[pos_mask])
                loss = loss + lp
                pos_loss_sum += float(lp.item())
                n_pos_batches += 1

            if objective_mode == "selective_margin_hinge" and neg_mask.any():
                neg_logits = logits[neg_mask]
                neg_probs = torch.softmax(neg_logits, dim=-1)
                sup11_max_prob = neg_probs[:, sup11_idx_t].max(dim=-1).values
                l_sup = torch.relu(sup11_max_prob - 0.35).pow(2).mean()

                neg_energy = -torch.logsumexp(neg_logits, dim=-1)
                if pos_mask.any():
                    pos_energy_mean = (-torch.logsumexp(logits[pos_mask], dim=-1)).mean().detach()
                else:
                    pos_energy_mean = torch.tensor(-8.0, device=device)
                l_energy = torch.relu((pos_energy_mean + 2.5) - neg_energy).mean()

                ln = 0.5 * l_sup + 0.25 * l_energy
                loss = loss + ln
                neg_loss_sum += float(ln.item())
                n_neg_batches += 1

            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()
            tot_loss += float(loss.item())

        epoch_stats.append(
            {
                "epoch": ep,
                "mean_total_loss": round(tot_loss / max(1, len(loader)), 5),
                "mean_pos_ce_loss": round(pos_loss_sum / max(1, n_pos_batches), 5),
                "mean_neg_hinge_loss": round(neg_loss_sum / max(1, n_neg_batches), 5) if n_neg_batches else 0.0,
            }
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(output_dir), safe_serialization=True)
    tokenizer.save_pretrained(str(output_dir))
    elapsed = round(time.perf_counter() - t0, 2)
    return {
        "fit_name": fit_name,
        "objective_mode": objective_mode,
        "elapsed_seconds": elapsed,
        "epoch_stats": epoch_stats,
    }


def _build_calibrated_rejector_on_train_and_cal(
    *,
    fit_name: str,
    model_dir: Path,
    feature_spec: str,
    rejector_c: float,
    rej_train_texts: Sequence[str],
    rej_train_y: Sequence[int],  # 1 = in_scope, 0 = negative/OOD
    cal_pos_df: pd.DataFrame,
    cal_neg_df: pd.DataFrame,
    bitext_cal_df: pd.DataFrame,
    policy_v2: Any,
) -> Tuple[float, SelectiveRejectorParams, Dict[str, Any]]:
    """Fit T>=1.0 on positive cal, rejector weights on train only, and threshold on cal only."""
    label2id = {lbl: idx for idx, lbl in enumerate(STANDARD_INTENTS_46)}
    adapter = SelectiveCandidateAdapter(
        fit_name,
        model_dir,
        fit_name,
        mode="raw_uncalibrated",
        validate_manifest=False,
    )

    # 1. Fit scalar temperature T >= 1.0 strictly on positive calibration logits (domain + Bitext cal)
    cal_pos_all_texts = cal_pos_df["instruction"].tolist() + bitext_cal_df["instruction"].tolist()
    cal_pos_all_y = np.array(
        [label2id[x] for x in cal_pos_df["intent"].tolist() + bitext_cal_df["intent"].tolist()],
        dtype=np.int64,
    )
    cal_pos_logits, cal_pos_cls = adapter.extract_logits_and_cls(cal_pos_all_texts, batch_size=64)
    temperature = fit_temperature_on_calibration_logits(
        cal_pos_logits,
        cal_pos_all_y,
        min_temperature=1.0,
        max_temperature=2.5,
    )

    # 2. Fit rejector scaler & logistic weights strictly on TRAIN split features
    trn_logits, trn_cls = adapter.extract_logits_and_cls(rej_train_texts, batch_size=64)
    trn_feats = compute_selective_feature_matrix(
        trn_logits,
        trn_cls,
        temperature=temperature,
        feature_spec=feature_spec,
    )
    scaler = StandardScaler()
    trn_scaled = scaler.fit_transform(trn_feats)
    clf = LogisticRegression(
        C=rejector_c,
        class_weight="balanced",
        max_iter=2000,
        random_state=42,
    )
    clf.fit(trn_scaled, np.asarray(rej_train_y, dtype=np.int64))

    temp_rej = SelectiveRejectorParams(
        enabled=True,
        feature_spec=feature_spec,
        feature_dim=trn_feats.shape[1],
        scaler_mean=scaler.mean_.tolist(),
        scaler_scale=scaler.scale_.tolist(),
        weights=clf.coef_[0].tolist(),
        bias=float(clf.intercept_[0]),
        threshold=0.50,
    )

    # 3. Select threshold strictly on isolated CALIBRATION splits
    cal_neg_texts = cal_neg_df["instruction"].tolist()
    cal_neg_logits, cal_neg_cls = adapter.extract_logits_and_cls(cal_neg_texts, batch_size=64)

    cal_dom_pos_texts = cal_pos_df["instruction"].tolist()
    cal_dom_pos_intents = cal_pos_df["intent"].tolist()
    n_dom_cal = len(cal_dom_pos_texts)

    # Slice cached pos arrays: first n_dom_cal are domain cal positives, rest are bitext cal
    cal_dom_logits = cal_pos_logits[:n_dom_cal]
    cal_dom_cls = cal_pos_cls[:n_dom_cal]
    bitext_cal_logits = cal_pos_logits[n_dom_cal:]

    cal_dom_feats = compute_selective_feature_matrix(
        cal_dom_logits, cal_dom_cls, temperature=temperature, feature_spec=feature_spec
    )
    cal_neg_feats = compute_selective_feature_matrix(
        cal_neg_logits, cal_neg_cls, temperature=temperature, feature_spec=feature_spec
    )
    cal_dom_p_in = score_rejector(cal_dom_feats, temp_rej)
    cal_neg_p_in = score_rejector(cal_neg_feats, temp_rej)

    def _softmax_np(lg: np.ndarray, temp: float) -> np.ndarray:
        z = lg / float(temp)
        z = z - z.max(axis=1, keepdims=True)
        e = np.exp(z)
        return e / np.clip(e.sum(axis=1, keepdims=True), 1e-12, None)

    cal_dom_probs = _softmax_np(cal_dom_logits, temperature)
    cal_neg_probs = _softmax_np(cal_neg_logits, temperature)
    bitext_cal_probs = _softmax_np(bitext_cal_logits, temperature)

    def _route_row(probs_vec: np.ndarray) -> Tuple[str, float, float, str]:
        order = np.argsort(-probs_vec)
        top1, top2 = int(order[0]), int(order[1])
        pred_lbl = STANDARD_INTENTS_46[top1]
        conf = float(probs_vec[top1])
        margin = float(probs_vec[top1] - probs_vec[top2])
        dec = decide_route(
            IntentPrediction(intent=pred_lbl, confidence=conf, margin=margin, model_version=fit_name),
            RoutingContext(ticket_customer_id="cal", extracted_slots={}, is_personal_lookup=False),
            policy_v2,
        )
        return pred_lbl, conf, margin, dec.action

    cal_dom_routes = [_route_row(cal_dom_probs[i]) for i in range(n_dom_cal)]
    cal_neg_routes = [_route_row(cal_neg_probs[i]) for i in range(len(cal_neg_texts))]

    best_tau = 0.50
    best_tau_score = -1e9
    best_tau_stats: Dict[str, Any] = {}

    sup11_cal_n = max(1, sum(1 for y in cal_dom_pos_intents if y in SUPPORTED_11_DRAFT_INTENTS))
    neg_cal_n = max(1, len(cal_neg_texts))

    for tau in np.linspace(0.20, 0.90, 71):
        tau_f = round(float(tau), 4)
        pos_corr_draft = 0
        pos_raw_draft = 0
        pos_human_escalate = 0
        for i, gold_y in enumerate(cal_dom_pos_intents):
            pred_lbl, _, _, raw_act = cal_dom_routes[i]
            accepted = cal_dom_p_in[i] >= tau_f
            eff_act = "manual_fallback" if (raw_act == "retrieve_draft" and not accepted) else raw_act
            if gold_y in SUPPORTED_11_DRAFT_INTENTS and eff_act == "retrieve_draft":
                pos_raw_draft += 1
                if pred_lbl == gold_y:
                    pos_corr_draft += 1
            elif gold_y == "human_agent" and eff_act == "escalate" and pred_lbl == "human_agent":
                pos_human_escalate += 1

        neg_false_draft = 0
        neg_false_accept_any = 0
        for i in range(len(cal_neg_texts)):
            _, _, _, raw_act = cal_neg_routes[i]
            accepted = cal_neg_p_in[i] >= tau_f
            if accepted:
                neg_false_accept_any += 1
            if raw_act == "retrieve_draft" and accepted:
                neg_false_draft += 1

        tau_obj = (
            (pos_corr_draft / sup11_cal_n)
            - 2.0 * (neg_false_draft / neg_cal_n)
            - 0.5 * (neg_false_accept_any / neg_cal_n)
            - 0.05 * abs(tau_f - 0.50)
        )
        if tau_obj > best_tau_score:
            best_tau_score = tau_obj
            best_tau = tau_f
            best_tau_stats = {
                "threshold": tau_f,
                "cal_dom_raw_draft": pos_raw_draft,
                "cal_dom_correct_draft": pos_corr_draft,
                "cal_dom_sup11_total": sup11_cal_n,
                "cal_dom_human_agent_correct": pos_human_escalate,
                "cal_neg_false_draft": neg_false_draft,
                "cal_neg_false_accept_any": neg_false_accept_any,
                "cal_neg_total": len(cal_neg_texts),
                "tau_objective": round(float(tau_obj), 5),
            }

    final_rej = SelectiveRejectorParams(
        enabled=True,
        feature_spec=feature_spec,
        feature_dim=temp_rej.feature_dim,
        scaler_mean=temp_rej.scaler_mean,
        scaler_scale=temp_rej.scaler_scale,
        weights=temp_rej.weights,
        bias=temp_rej.bias,
        threshold=best_tau,
    )

    # Calibration positive 46-class & 34-label metrics (strictly on calibration data)
    b_gold = bitext_cal_df["intent"].tolist()
    b_preds = [STANDARD_INTENTS_46[int(np.argmax(bitext_cal_probs[i]))] for i in range(len(b_gold))]
    b_confs = [float(np.max(bitext_cal_probs[i])) for i in range(len(b_gold))]
    b_corrs = [p == g for p, g in zip(b_preds, b_gold)]

    all_cal_pos_probs = np.vstack([cal_dom_probs, bitext_cal_probs])
    all_cal_pos_gold = cal_dom_pos_intents + b_gold
    all_cal_preds = [STANDARD_INTENTS_46[int(np.argmax(all_cal_pos_probs[i]))] for i in range(len(all_cal_pos_gold))]
    all_cal_confs = [float(np.max(all_cal_pos_probs[i])) for i in range(len(all_cal_pos_gold))]
    all_cal_corrs = [p == g for p, g in zip(all_cal_preds, all_cal_pos_gold)]
    cal_ece, _ = M.expected_calibration_error(all_cal_confs, all_cal_corrs, n_bins=10)
    cal_brier = sum((c - (1.0 if y else 0.0)) ** 2 for c, y in zip(all_cal_confs, all_cal_corrs)) / max(1, len(all_cal_corrs))

    b34_idx = [i for i, y in enumerate(b_gold) if y in ESCALATED_34_INTENTS]
    b34_acc = accuracy_score([b_gold[i] for i in b34_idx], [b_preds[i] for i in b34_idx]) if b34_idx else 0.0
    b46_acc = accuracy_score(b_gold, b_preds) if b_gold else 0.0

    sel_utility = (
        (best_tau_stats["cal_dom_correct_draft"] / sup11_cal_n)
        + 0.5 * float(b46_acc)
        - 2.0 * (best_tau_stats["cal_neg_false_draft"] / neg_cal_n)
        - 0.25 * float(cal_ece)
        - 0.25 * float(cal_brier)
    )

    cal_summary = {
        "temperature": round(float(temperature), 4),
        "feature_spec": feature_spec,
        "rejector_c": rejector_c,
        "rejector_threshold_selection": best_tau_stats,
        "cal_bitext_46_n": len(b_gold),
        "cal_bitext_46_accuracy": round(float(b46_acc), 4),
        "cal_bitext_34_n": len(b34_idx),
        "cal_bitext_34_accuracy": round(float(b34_acc), 4),
        "cal_pos_ece_10bin": round(float(cal_ece), 4),
        "cal_pos_brier": round(float(cal_brier), 4),
        "calibration_selection_utility": round(float(sel_utility), 5),
    }
    return temperature, final_rej, cal_summary


def write_calibration_manifest(
    *,
    model_dir: Path,
    model_version: str,
    fit_name: str,
    temperature: float,
    rejector: SelectiveRejectorParams,
    train_split_sha256: str,
    calibration_split_sha256: str,
) -> Path:
    """Write and validate calibration_manifest.json matching B & C's agreed schema."""
    art_hashes = {
        fname: compute_sha256(model_dir / fname).lower()
        for fname in ("model.safetensors", "tokenizer.json", "config.json")
    }
    manifest = {
        "schema_version": CALIBRATION_SCHEMA_VERSION,
        "model_version": model_version,
        "tokenization": {
            "max_length": 64,
            "padding": "max_length",
            "truncation": True,
        },
        "label_space": {
            "num_labels": 46,
            "valid_46_label_bijection": True,
            "id2label": {str(i): lbl for i, lbl in enumerate(STANDARD_INTENTS_46)},
        },
        "calibration": {
            "method": "temperature_scaling",
            "temperature": round(float(temperature), 6),
            "min_temperature": 1.0,
            "fit_split": "calibration",
            "calibrated": True,
        },
        "selective_rejector": rejector.to_dict(),
        "semantics": {
            "raw_score_kind": "uncalibrated_softmax",
            "calibrated_score_kind": "calibrated_probability",
            "raw_probs_formula": "softmax(logits)",
            "calibrated_probs_formula": "softmax(logits / temperature)",
            "in_scope_prob_formula": "sigmoid(dot((x - scaler_mean) / scaler_scale, weights) + bias)",
            "selective_accepted_formula": "in_scope_probability >= threshold",
            "intent_probs_separate_from_rejection": True,
        },
        "artifact_hashes": art_hashes,
        "provenance": {
            "fit_name": fit_name,
            "train_split_sha256": train_split_sha256,
            "calibration_split_sha256": calibration_split_sha256,
        },
    }
    validate_calibration_manifest(manifest, model_dir)
    out = model_dir / "calibration_manifest.json"
    out.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return out


def _evaluate_adapter_mode(
    adapter: SelectiveCandidateAdapter,
    *,
    repo_root: Path,
    eval_pos_rows: Sequence[Dict[str, Any]],
    eval_neg_rows: Sequence[Dict[str, Any]],
    bitext_test_df: pd.DataFrame,
    policy_v2: Any,
    retriever: RetrievalAdapter,
) -> Dict[str, Any]:
    """Evaluate one locked adapter mode across new holdout, Bitext test, noise, OOD, and regression."""
    engine = Engine(
        model=adapter,
        retriever=retriever,
        llm=_OfflineSpyLLM(),
        versions={"engine": "2.0.0", "policy": policy_v2.version, "model": adapter.version},
        policy=policy_v2.model_dump(),
    )

    # 1. New unseen group-isolated positive holdout (72 rows)
    pos_texts = [r["instruction"] for r in eval_pos_rows]
    pos_gold = [r["intent"] for r in eval_pos_rows]
    pos_preds = adapter.predict_batch(pos_texts, batch_size=64)
    pos_pred_labels = [p["intent"] for p in pos_preds]

    pos_raw_draft = pos_corr_draft = pos_human_esc = pos_sup11_n = 0
    for r, p in zip(eval_pos_rows, pos_preds):
        ans, _ = _engine_analyse_selective(engine, adapter, text=r["instruction"])
        rec = ans["routing"]["recommendation"]
        if r["intent"] in SUPPORTED_11_DRAFT_INTENTS:
            pos_sup11_n += 1
            if rec == "draft":
                pos_raw_draft += 1
                if p["intent"] == r["intent"]:
                    pos_corr_draft += 1
        elif r["intent"] == "human_agent":
            if rec == "escalate" and p["intent"] == "human_agent":
                pos_human_esc += 1

    # 2. New unseen group-isolated negative holdout (27 rows)
    neg_false_draft = 0
    neg_false_accept_any = 0
    neg_false_draft_ids: List[str] = []
    for r in eval_neg_rows:
        pred = adapter.predict(r["instruction"])
        ans, _ = _engine_analyse_selective(engine, adapter, text=r["instruction"])
        if pred["selective_accepted"]:
            neg_false_accept_any += 1
        if ans["routing"]["recommendation"] == "draft":
            neg_false_draft += 1
            neg_false_draft_ids.append(r["sample_id"])

    # 3. Original 46-label verified Bitext test split
    test_preds = adapter.predict_batch(bitext_test_df["instruction"].tolist(), batch_size=128)
    test_pred_lbls = [p["intent"] for p in test_preds]
    test_gold = bitext_test_df["intent"].tolist()
    sup12_idx = [i for i, y in enumerate(test_gold) if y in CORE_PRODUCT_INTENTS]
    oth34_idx = [i for i, y in enumerate(test_gold) if y not in CORE_PRODUCT_INTENTS]
    oth34_unsafe_draft = 0
    for i in oth34_idx:
        p = test_preds[i]
        dec = decide_route(
            IntentPrediction(intent=p["intent"], confidence=p["confidence"], margin=p["margin"], model_version=adapter.version),
            RoutingContext(ticket_customer_id="bitext-test", extracted_slots={}, is_personal_lookup=False),
            policy_v2,
        )
        if dec.action == "retrieve_draft" and p["selective_accepted"]:
            oth34_unsafe_draft += 1

    # 4. AutoEval ml_noise_420
    noise_cases = [
        json.loads(l)
        for l in (repo_root / "data/benchmarks/autoeval/v1/ml_noise.jsonl").read_text(encoding="utf-8").splitlines()
        if l.strip()
    ]
    noise_preds = adapter.predict_batch([c["text"] for c in noise_cases], batch_size=64)
    n_confs, n_corrs = [], []
    n_safe = 0
    for c, p in zip(noise_cases, noise_preds):
        corr = p["intent"] == c["true_intent"]
        n_confs.append(p["confidence"])
        n_corrs.append(corr)
        if corr or p["confidence"] < policy_v2.default_confidence_threshold or p["intent"] not in SUPPORTED_12_INTENTS or not p["selective_accepted"]:
            n_safe += 1
    noise_ece, _ = M.expected_calibration_error(n_confs, n_corrs, n_bins=10)
    noise_brier = sum((cf - (1.0 if y else 0.0)) ** 2 for cf, y in zip(n_confs, n_corrs)) / max(1, len(noise_cases))

    # 5. AutoEval ml_oos_80
    oos_cases = [
        json.loads(l)
        for l in (repo_root / "data/benchmarks/autoeval/v1/ml_oos.jsonl").read_text(encoding="utf-8").splitlines()
        if l.strip()
    ]
    oos_leak_ids: List[str] = []
    for c in oos_cases:
        ans, _ = _engine_analyse_selective(engine, adapter, text=c["text"])
        if ans["routing"]["recommendation"] == "draft":
            oos_leak_ids.append(c["id"])

    # 6. Known regression: system_acceptance_156
    sa_cases = [
        json.loads(l)
        for l in (repo_root / "data/benchmarks/system/v2/acceptance/cases.jsonl").read_text(encoding="utf-8").splitlines()
        if l.strip()
    ]
    sa_raw_draft = sa_corr_draft = sa_ans_tot = 0
    sa_mand_tot = sa_mand_strict = 0
    sa_mand_real_leaks: List[str] = []
    sa_mand_uninjected_leaks: List[str] = []
    sa_esc34_true, sa_esc34_pred = [], []
    for c in sa_cases:
        order_ctx = c.get("context", {}).get("extracted_slots", {})
        ans, _ = _engine_analyse_selective(engine, adapter, text=c["text"], order_ctx=order_ctx)
        rec = ans["routing"]["recommendation"]
        act = {"draft": "retrieve_draft", "abstain": "manual_fallback"}.get(rec, rec)
        pred_i = ans["intent"]["label"]
        exp = c.get("expected", {})
        ti = c.get("true_intent")
        if ti in ESCALATED_34_INTENTS:
            sa_esc34_true.append(ti)
            sa_esc34_pred.append(pred_i)
        if exp.get("answerable") or exp.get("draft_expected"):
            sa_ans_tot += 1
            if rec == "draft":
                sa_raw_draft += 1
                if pred_i == ti:
                    sa_corr_draft += 1
        if exp.get("must_escalate"):
            sa_mand_tot += 1
            if act in exp.get("actions", []):
                sa_mand_strict += 1
            if rec == "draft":
                if c["id"] in KNOWN_UNINJECTED_ACCEPTANCE_IDS:
                    sa_mand_uninjected_leaks.append(c["id"])
                else:
                    sa_mand_real_leaks.append(c["id"])

    # 7. Known regression: final_acceptance_24
    fa_cases = [
        json.loads(l)
        for l in (repo_root / "data/benchmarks/final_acceptance/cases.jsonl").read_text(encoding="utf-8").splitlines()
        if l.strip()
    ]
    fa_ans_tot = fa_raw_draft = fa_corr_draft = 0
    fa_unans_tot = fa_unans_real_leaks = 0
    fa_unans_uninjected: List[str] = []
    fa_unans_real_ids: List[str] = []
    fa_wrong_draft_ids: List[str] = []
    for c in fa_cases:
        order_ctx = {"order_id": c["order_id"]} if c.get("order_id") else {}
        ans, _ = _engine_analyse_selective(
            engine,
            adapter,
            text=c["query"],
            as_of=c.get("as_of") or "2026-11-13T00:00:00Z",
            order_ctx=order_ctx,
        )
        rec = ans["routing"]["recommendation"]
        pred_i = ans["intent"]["label"]
        if c.get("is_answerable"):
            fa_ans_tot += 1
            if rec == "draft":
                fa_raw_draft += 1
                if pred_i == c["intent"]:
                    fa_corr_draft += 1
                else:
                    fa_wrong_draft_ids.append(c["id"])
        else:
            fa_unans_tot += 1
            if rec == "draft":
                if c["id"] in KNOWN_UNINJECTED_FINAL_IDS or c.get("fixture_boundary") != "active_kb":
                    fa_unans_uninjected.append(c["id"])
                else:
                    fa_unans_real_leaks += 1
                    fa_unans_real_ids.append(c["id"])

    return {
        "evaluation_mode": adapter.mode,
        "temperature_used": 1.0 if adapter.mode == "raw_uncalibrated" else adapter.temperature,
        "rejector_active": adapter.mode == "calibrated_with_rejector",
        "new_holdout_positive_72": {
            "n_total": len(eval_pos_rows),
            "accuracy": round(float(accuracy_score(pos_gold, pos_pred_labels)), 4),
            "macro_f1": round(float(f1_score(pos_gold, pos_pred_labels, average="macro", zero_division=0)), 4),
            "sup11_total": pos_sup11_n,
            "raw_draft_eligible_count": pos_raw_draft,
            "correct_intent_draft_eligible_count": pos_corr_draft,
            "precision_among_eligible": round(pos_corr_draft / max(1, pos_raw_draft), 4) if pos_raw_draft else 1.0,
            "human_agent_escalated_count": pos_human_esc,
        },
        "new_holdout_negative_27": {
            "n_total": len(eval_neg_rows),
            "false_draft_count": neg_false_draft,
            "false_draft_ids": neg_false_draft_ids,
            "false_accept_any_count": neg_false_accept_any,
        },
        "original_46_label_test": {
            "n_total": len(test_gold),
            "all_46_accuracy": round(float(accuracy_score(test_gold, test_pred_lbls)), 4),
            "all_46_macro_f1": round(float(f1_score(test_gold, test_pred_lbls, average="macro", zero_division=0)), 4),
            "supported_12_accuracy": round(
                float(accuracy_score([test_gold[i] for i in sup12_idx], [test_pred_lbls[i] for i in sup12_idx])), 4
            ),
            "other_34_accuracy": round(
                float(accuracy_score([test_gold[i] for i in oth34_idx], [test_pred_lbls[i] for i in oth34_idx])), 4
            ),
            "other_34_macro_f1": round(
                float(
                    f1_score(
                        [test_gold[i] for i in oth34_idx],
                        [test_pred_lbls[i] for i in oth34_idx],
                        labels=list(ESCALATED_34_INTENTS),
                        average="macro",
                        zero_division=0,
                    )
                ),
                4,
            ),
            "other_34_unsafe_draft_count": oth34_unsafe_draft,
        },
        "ml_noise_420": {
            "n_total": len(noise_cases),
            "overall_accuracy": round(sum(n_corrs) / max(1, len(noise_cases)), 4),
            "ece_10bin": round(float(noise_ece), 4),
            "binary_top_label_brier": round(float(noise_brier), 4),
            "safe_routing_rate": round(n_safe / max(1, len(noise_cases)), 4),
        },
        "ml_oos_80": {
            "n_total": len(oos_cases),
            "false_draft_count": len(oos_leak_ids),
            "false_draft_ids": oos_leak_ids,
        },
        "known_regression_system_acceptance_156": {
            "suite_role": "known_acceptance_regression_not_unseen_holdout",
            "answerable_total": sa_ans_tot,
            "raw_draft_eligible_count": sa_raw_draft,
            "correct_intent_draft_eligible_count": sa_corr_draft,
            "precision_among_eligible": round(sa_corr_draft / max(1, sa_raw_draft), 4) if sa_raw_draft else 1.0,
            "escalated_34_macro_f1": round(
                float(f1_score(sa_esc34_true, sa_esc34_pred, labels=list(ESCALATED_34_INTENTS), average="macro", zero_division=0)),
                4,
            ) if sa_esc34_true else 0.0,
            "mandatory_total": sa_mand_tot,
            "mandatory_strict_match": sa_mand_strict,
            "mandatory_real_unsafe_draft_leaks": sa_mand_real_leaks,
            "mandatory_known_uninjected_fault_cases": sa_mand_uninjected_leaks,
        },
        "known_regression_final_acceptance_24": {
            "suite_role": "known_acceptance_regression_not_unseen_holdout",
            "answerable_total": fa_ans_tot,
            "raw_draft_eligible_count": fa_raw_draft,
            "correct_intent_draft_eligible_count": fa_corr_draft,
            "precision_among_eligible": round(fa_corr_draft / max(1, fa_raw_draft), 4) if fa_raw_draft else 1.0,
            "wrong_intent_draft_ids": fa_wrong_draft_ids,
            "unanswerable_total": fa_unans_tot,
            "unanswerable_real_active_kb_leaks": fa_unans_real_ids,
            "unanswerable_known_uninjected_fault_cases": fa_unans_uninjected,
        },
    }


def _git_head_sha(repo_root: Path) -> str:
    try:
        out = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(repo_root), text=True).strip()
        return out
    except Exception:
        return "unknown"


def run_selective_candidate_pipeline(
    *,
    repo_root: Path = REPO_ROOT,
    output_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Execute bounded 2-fit training, calibration selection, locking, and evaluation."""
    out_root = output_root or (repo_root / "artifacts/evaluation/task_a_selective_20261113")
    out_root.mkdir(parents=True, exist_ok=True)
    datasets_dir = out_root / "datasets"
    fits_dir = out_root / "fits"
    cand_dir = out_root / "candidate_model"
    serving_dir = repo_root / "artifacts/models/trained/distilbert-supportiq"

    # 1. Verify original 46-label Bitext lineage + export audited selective datasets
    lineage: VerifiedOriginalLineage = verify_original_46_label_lineage(repo_root=repo_root)
    ds_manifest = export_selective_datasets(datasets_dir, repo_root=repo_root, fail_on_audit=True)
    compute_inv = collect_compute_and_model_inventory(repo_root=repo_root)

    pos_train = [json.loads(l) for l in (datasets_dir / "positive_train.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    neg_train = [json.loads(l) for l in (datasets_dir / "negative_train.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    pos_cal = [json.loads(l) for l in (datasets_dir / "positive_calibration.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    neg_cal = [json.loads(l) for l in (datasets_dir / "negative_calibration.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    pos_eval = [json.loads(l) for l in (datasets_dir / "positive_evaluation.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    neg_eval = [json.loads(l) for l in (datasets_dir / "negative_evaluation.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]

    # Build Bitext replay train + disjoint Bitext cal
    replay_domain_train_df, bitext_cal_df = build_replay_and_domain_train_df(
        lineage,
        pos_train,
        replay_per_other_label=60,
        replay_per_supported_label=30,
        domain_train_repeat=3,
        cal_per_label=5,
        seed=42,
    )
    label2id = {lbl: idx for idx, lbl in enumerate(STANDARD_INTENTS_46)}

    pos_train_texts = replay_domain_train_df["instruction"].tolist()
    pos_train_labels = [label2id[x] for x in replay_domain_train_df["intent"].tolist()]
    pos_train_flags = [0] * len(pos_train_texts)

    # Rejector training set (strictly TRAIN only: balanced Bitext train replay + pos_train vs neg_train)
    rng = np.random.default_rng(42)
    bitext_train_only = lineage.train_df[~lineage.train_df["sample_id"].isin(set(bitext_cal_df["sample_id"]))].copy()
    rej_bitext_parts = [
        bitext_train_only[bitext_train_only["intent"] == lbl].sample(
            n=min(10, len(bitext_train_only[bitext_train_only["intent"] == lbl])),
            random_state=42 + i,
        )
        for i, lbl in enumerate(STANDARD_INTENTS_46)
    ]
    rej_bitext_df = pd.concat(rej_bitext_parts, ignore_index=True)
    rej_train_texts = (
        [r["instruction"] for r in pos_train]
        + rej_bitext_df["instruction"].tolist()
        + [r["instruction"] for r in neg_train]
    )
    rej_train_y = (
        [1] * len(pos_train)
        + [1] * len(rej_bitext_df)
        + [0] * len(neg_train)
    )

    policy_path = repo_root / "apps/core_backend/config/policies/intent_policy.v2.json"
    policy_v2 = load_policy_v2(str(policy_path))
    release = json.loads((repo_root / "apps/ai_service/kb-release.json").read_text(encoding="utf-8"))
    allowed_docs = {(d["document_id"], d["version"]) for d in release["documents"]}
    retriever = RetrievalAdapter(allowed_document_versions=allowed_docs)

    cal_pos_df = pd.DataFrame(pos_cal)
    cal_neg_df = pd.DataFrame(neg_cal)

    train_budget_start = time.perf_counter()

    # ------------------------------------------------------------------
    # Fit 1: Clean 46-class CE + Separate CLS+Logit Selective Rejector
    # ------------------------------------------------------------------
    fit1_dir = fits_dir / "fit1_selective_head"
    fit1_train_meta = _train_single_fit(
        fit_name="fit1_selective_head",
        objective_mode="clean_positive_ce",
        base_model_dir=serving_dir,
        output_dir=fit1_dir,
        train_texts=pos_train_texts,
        train_labels=pos_train_labels,
        train_is_negative=pos_train_flags,
        seed=42,
        epochs=2,
    )
    fit1_temp, fit1_rej, fit1_cal = _build_calibrated_rejector_on_train_and_cal(
        fit_name="fit1_selective_head",
        model_dir=fit1_dir,
        feature_spec="cls_l2_plus_logit_geometry_v1",
        rejector_c=0.25,
        rej_train_texts=rej_train_texts,
        rej_train_y=rej_train_y,
        cal_pos_df=cal_pos_df,
        cal_neg_df=cal_neg_df,
        bitext_cal_df=bitext_cal_df,
        policy_v2=policy_v2,
    )

    # ------------------------------------------------------------------
    # Fit 2: Confidence-Preserving Selective Margin + Logit Rejector
    # ------------------------------------------------------------------
    neg_repeat = 4
    fit2_texts = pos_train_texts + [r["instruction"] for _ in range(neg_repeat) for r in neg_train]
    fit2_labels = pos_train_labels + ([0] * (len(neg_train) * neg_repeat))
    fit2_flags = pos_train_flags + ([1] * (len(neg_train) * neg_repeat))
    perm = rng.permutation(len(fit2_texts))
    fit2_texts = [fit2_texts[i] for i in perm]
    fit2_labels = [fit2_labels[i] for i in perm]
    fit2_flags = [fit2_flags[i] for i in perm]

    fit2_dir = fits_dir / "fit2_selective_margin"
    fit2_train_meta = _train_single_fit(
        fit_name="fit2_selective_margin",
        objective_mode="selective_margin_hinge",
        base_model_dir=serving_dir,
        output_dir=fit2_dir,
        train_texts=fit2_texts,
        train_labels=fit2_labels,
        train_is_negative=fit2_flags,
        seed=1042,
        epochs=2,
    )
    fit2_temp, fit2_rej, fit2_cal = _build_calibrated_rejector_on_train_and_cal(
        fit_name="fit2_selective_margin",
        model_dir=fit2_dir,
        feature_spec="logit_geometry_v1",
        rejector_c=1.0,
        rej_train_texts=rej_train_texts,
        rej_train_y=rej_train_y,
        cal_pos_df=cal_pos_df,
        cal_neg_df=cal_neg_df,
        bitext_cal_df=bitext_cal_df,
        policy_v2=policy_v2,
    )

    total_train_elapsed = round(time.perf_counter() - train_budget_start, 2)
    if total_train_elapsed > MAX_TRAINING_BUDGET_SECONDS:
        raise RuntimeError(
            f"Exceeded 1800s training budget: {total_train_elapsed}s"
        )

    # ------------------------------------------------------------------
    # Select winner STRICTLY on isolated calibration split and LOCK
    # ------------------------------------------------------------------
    fit_records = {
        "fit1_selective_head": {
            "dir": fit1_dir,
            "train": fit1_train_meta,
            "temperature": fit1_temp,
            "rejector": fit1_rej,
            "calibration": fit1_cal,
        },
        "fit2_selective_margin": {
            "dir": fit2_dir,
            "train": fit2_train_meta,
            "temperature": fit2_temp,
            "rejector": fit2_rej,
            "calibration": fit2_cal,
        },
    }
    winner_name = max(
        fit_records.keys(),
        key=lambda k: fit_records[k]["calibration"]["calibration_selection_utility"],
    )
    winner = fit_records[winner_name]

    if cand_dir.exists():
        shutil.rmtree(cand_dir)
    shutil.copytree(winner["dir"], cand_dir)

    cal_manifest_path = write_calibration_manifest(
        model_dir=cand_dir,
        model_version=f"supportiq-{winner_name}-20261113",
        fit_name=winner_name,
        temperature=winner["temperature"],
        rejector=winner["rejector"],
        train_split_sha256=ds_manifest["files"]["combined_train.jsonl"]["sha256"],
        calibration_split_sha256=ds_manifest["files"]["combined_calibration.jsonl"]["sha256"],
    )

    git_sha = _git_head_sha(repo_root)
    prov_manifest = {
        "provenance_status": "verified",
        "model_version": f"supportiq-{winner_name}-20261113",
        "selected_fit": winner_name,
        "training_lineage": {
            "bitext_preparation_run_id": lineage.run_id,
            "cleaned_csv_sha256": lineage.cleaned_sha256,
            "split_assignments_csv_sha256": lineage.splits_sha256,
            "selective_origin": "task_a_selective_20261113",
            "two_fit_budget_seconds": MAX_TRAINING_BUDGET_SECONDS,
            "total_training_elapsed_seconds": total_train_elapsed,
        },
        "dataset_hashes": {
            "bitext_cleaned_csv": lineage.cleaned_sha256,
            "bitext_split_assignments_csv": lineage.splits_sha256,
            **{k: v["sha256"] for k, v in ds_manifest["files"].items()},
        },
        "base_model": {
            "name": "distilbert-supportiq",
            "path": "artifacts/models/trained/distilbert-supportiq",
            "weights_sha256": compute_sha256(serving_dir / "model.safetensors").lower(),
            "tokenizer_sha256": compute_sha256(serving_dir / "tokenizer.json").lower(),
        },
        "git_commit": git_sha,
        "artifact_hashes": {
            "model.safetensors": compute_sha256(cand_dir / "model.safetensors").lower(),
            "tokenizer.json": compute_sha256(cand_dir / "tokenizer.json").lower(),
            "config.json": compute_sha256(cand_dir / "config.json").lower(),
        },
        "calibration_manifest_path": "artifacts/evaluation/task_a_selective_20261113/candidate_model/calibration_manifest.json",
        "calibration_manifest_sha256": compute_sha256(cal_manifest_path).lower(),
    }
    prov_path = cand_dir / "candidate_provenance_manifest.json"
    prov_path.write_text(json.dumps(prov_manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    cal_selection_doc = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "selection_policy": "Selected solely on isolated calibration split before any holdout/regression eval.",
        "total_training_elapsed_seconds": total_train_elapsed,
        "budget_cap_seconds": MAX_TRAINING_BUDGET_SECONDS,
        "selected_winner": winner_name,
        "candidates": {
            k: {
                "train_summary": v["train"],
                "calibration_summary": v["calibration"],
            }
            for k, v in fit_records.items()
        },
    }
    (out_root / "calibration_selection.json").write_text(
        json.dumps(cal_selection_doc, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # ------------------------------------------------------------------
    # Single post-decision locked evaluation (Raw vs Calibrated vs Selective)
    # ------------------------------------------------------------------
    eval_modes: Dict[str, Any] = {}
    for mode_name in ("raw_uncalibrated", "calibrated_without_rejector", "calibrated_with_rejector"):
        adapter = SelectiveCandidateAdapter(
            prov_manifest["model_version"],
            cand_dir,
            prov_manifest["model_version"],
            mode=mode_name,
            validate_manifest=True,
        )
        eval_modes[mode_name] = _evaluate_adapter_mode(
            adapter,
            repo_root=repo_root,
            eval_pos_rows=pos_eval,
            eval_neg_rows=neg_eval,
            bitext_test_df=lineage.test_df,
            policy_v2=policy_v2,
            retriever=retriever,
        )

    # Serving baseline reference on exact same new_holdout + regression suites
    srv_adapter = SelectiveCandidateAdapter(
        "distilbert-supportiq",
        serving_dir,
        "distilbert-supportiq",
        mode="raw_uncalibrated",
        validate_manifest=False,
    )
    serving_eval = _evaluate_adapter_mode(
        srv_adapter,
        repo_root=repo_root,
        eval_pos_rows=pos_eval,
        eval_neg_rows=neg_eval,
        bitext_test_df=lineage.test_df,
        policy_v2=policy_v2,
        retriever=retriever,
    )

    # Run Task C acceptance gate compatibility check (positive_evaluation.jsonl as eval_split)
    c_gate = run_classifier_acceptance_gate(
        repo_root=repo_root,
        candidate_name=prov_manifest["model_version"],
        candidate_dir=cand_dir,
        serving_dir=serving_dir,
        candidate_manifest_path=prov_path,
        train_split_path=datasets_dir / "combined_train.jsonl",
        calibration_split_path=datasets_dir / "combined_calibration.jsonl",
        eval_split_path=datasets_dir / "positive_evaluation.jsonl",
    )

    final_eval = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "compute_inventory": compute_inv,
        "dataset_manifest": ds_manifest,
        "calibration_selection": cal_selection_doc,
        "provenance_manifest": prov_manifest,
        "serving_baseline_evaluation": serving_eval,
        "locked_candidate_evaluations": eval_modes,
        "task_c_gate_raw_compat_check": c_gate,
    }
    (out_root / "selective_evaluation_results.json").write_text(
        json.dumps(final_eval, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return final_eval


if __name__ == "__main__":
    res = run_selective_candidate_pipeline()
    print(
        json.dumps(
            {
                "selected_winner": res["calibration_selection"]["selected_winner"],
                "total_training_elapsed_seconds": res["calibration_selection"]["total_training_elapsed_seconds"],
                "serving": res["serving_baseline_evaluation"],
                "candidate_modes": res["locked_candidate_evaluations"],
                "task_c_gate_decision": res["task_c_gate_raw_compat_check"]["gate_decision"],
                "task_c_gate_failure_reasons": res["task_c_gate_raw_compat_check"]["failure_reasons"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
