"""Bounded 46-label candidate training & evaluation pipeline for Task A.

Enforces:
1. Verified original 46-label Bitext data lineage (cleaned.csv + split_assignments.csv
   checksum-verified against preparation manifest/split_report). Fails closed with
   MissingLineageBlockerError if absent—never invents missing 34-label data or
   substitutes gold benchmarks.
2. Independent policy-derived domain templates (train / calibration / evaluation
   disjoint by template_group_id before paraphrasing, gold-leakage audited).
3. 34-label + 12-label replay from original train split alongside domain train groups.
4. Bounded training attempt (max 30 minutes / 1800s), existing dependencies only,
   no serving weight overwrites, no threshold/engine edits, no provider calls.
5. Disjoint post-hoc temperature scaling on calibration groups only, followed by
   evaluation across domain evaluation groups, 46-label test split, ml_noise,
   ml_oos, and frozen acceptance (tracked strictly as known regression suites).
"""

from __future__ import annotations

import datetime
import json
import math
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
import torch
from sklearn.metrics import accuracy_score, f1_score
from torch.utils.data import DataLoader, Dataset
from transformers import AutoModelForSequenceClassification, AutoTokenizer, get_linear_schedule_with_warmup

from apps.ai_service.engine import Engine
from apps.core_backend.intent.routing import SUPPORTED_12_INTENTS, load_policy_v2
from apps.core_backend.retrieval.adapter import RetrievalAdapter
from pipeline.evaluation.autoeval import metrics as M
from pipeline.preparation.utils import CORE_PRODUCT_INTENTS, STANDARD_INTENTS, compute_sha256
from pipeline.training.domain_templates import check_gold_benchmark_leakage, export_domain_dataset

REPO_ROOT = Path(__file__).resolve().parents[2]
MAX_TRAINING_BUDGET_SECONDS = 1800.0  # Hard 30-minute cap per plan


class MissingLineageBlockerError(RuntimeError):
    """Raised when verified original 46-label training data is absent or invalid."""

    def __init__(self, message: str, blocker_details: Dict[str, Any]) -> None:
        super().__init__(message)
        self.blocker_details = blocker_details


@dataclass(frozen=True)
class VerifiedOriginalLineage:
    """Verified original 46-label train/test split DataFrames and hashes."""

    train_df: pd.DataFrame
    test_df: pd.DataFrame
    cleaned_path: Path
    splits_path: Path
    cleaned_sha256: str
    splits_sha256: str
    run_id: str


class _TokenizedDataset(Dataset):
    """Minimal map-style dataset for sequence classification."""

    def __init__(self, encodings: Dict[str, torch.Tensor], labels: Sequence[int]) -> None:
        self.encodings = encodings
        self.labels = torch.tensor(list(labels), dtype=torch.long)

    def __len__(self) -> int:
        return len(self.labels)

    def __getitem__(self, idx: int) -> Dict[str, torch.Tensor]:
        item = {k: v[idx] for k, v in self.encodings.items()}
        item["labels"] = self.labels[idx]
        return item


class _OfflineSpyLLM:
    """Fails immediately if any live/external LLM drafting call occurs."""

    def draft(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        raise AssertionError("VIOLATION: External LLM invoked during offline Task A evaluation.")


class _CandidateEngineAdapter:
    """Offline model adapter compatible with Engine._analyse, supporting temperature scaling."""

    def __init__(
        self,
        name: str,
        model_dir: Path,
        version: str,
        *,
        temperature: float = 1.0,
    ) -> None:
        self.name = name
        self.version = version
        self.temperature = float(temperature)
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.weights_sha256 = compute_sha256(model_dir / "model.safetensors").lower()
        self.tokenizer_sha256 = compute_sha256(model_dir / "tokenizer.json").lower()
        cfg = json.loads((model_dir / "config.json").read_text(encoding="utf-8"))
        self.id2label = {int(k): v for k, v in cfg["id2label"].items()}
        if set(self.id2label.values()) != set(STANDARD_INTENTS) or len(self.id2label) != 46:
            raise ValueError(f"Model {name} does not satisfy 46-label bijection.")
        self.tokenizer = AutoTokenizer.from_pretrained(str(model_dir))
        self.model = AutoModelForSequenceClassification.from_pretrained(str(model_dir))
        self.model.eval()
        self.model.to(self.device)
        self.verified_model_version = version
        self.model_version = version
        self.model_mode = "trained"
        self.verified = True

    def predict(self, text: str, top_k_count: int = 5) -> Dict[str, Any]:
        inputs = self.tokenizer(
            text, max_length=64, padding="max_length", truncation=True, return_tensors="pt"
        )
        inputs = {k: v.to(self.device) for k, v in inputs.items()}
        with torch.inference_mode():
            logits = self.model(**inputs).logits[0] / self.temperature
            probs = torch.softmax(logits, dim=-1).cpu().tolist()
        sorted_idx = sorted(range(len(probs)), key=lambda i: probs[i], reverse=True)
        top1_idx = sorted_idx[0]
        top1_prob = probs[top1_idx]
        top2_prob = probs[sorted_idx[1]] if len(sorted_idx) > 1 else 0.0
        return {
            "intent": self.id2label[top1_idx],
            "confidence": top1_prob,
            "margin": top1_prob - top2_prob,
            "top_k": [
                {"intent": self.id2label[i], "probability": probs[i]}
                for i in sorted_idx[:top_k_count]
            ],
            "score_kind": "temperature_scaled_softmax" if self.temperature != 1.0 else "uncalibrated_softmax",
            "model_version": self.version,
            "model_checksum": self.weights_sha256,
            "tokenizer_checksum": self.tokenizer_sha256,
            "model_mode": self.model_mode,
            "verified": self.verified,
        }

    def predict_batch(self, texts: Sequence[str], batch_size: int = 64) -> List[Dict[str, Any]]:
        """Run batched single-label inference returning intent + top-1 confidence."""
        results: List[Dict[str, Any]] = []
        text_list = list(texts)
        for start in range(0, len(text_list), batch_size):
            chunk = text_list[start : start + batch_size]
            inputs = self.tokenizer(
                chunk, max_length=64, padding="max_length", truncation=True, return_tensors="pt"
            )
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
            with torch.inference_mode():
                logits = self.model(**inputs).logits / self.temperature
                probs = torch.softmax(logits, dim=-1).cpu().numpy()
            top1_indices = probs.argmax(axis=-1)
            for row_idx, top1_idx in enumerate(top1_indices):
                results.append(
                    {
                        "intent": self.id2label[int(top1_idx)],
                        "confidence": float(probs[row_idx, int(top1_idx)]),
                    }
                )
        return results


def collect_compute_and_model_inventory(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    """Inventory local compute capabilities and immutable serving/pretrained model hashes."""
    serving_weights = repo_root / "artifacts/models/trained/distilbert-supportiq/model.safetensors"
    serving_tok = repo_root / "artifacts/models/trained/distilbert-supportiq/tokenizer.json"
    pretrained_weights = repo_root / "artifacts/models/pretrained/distilbert-base-uncased/model.safetensors"
    return {
        "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "torch_version": torch.__version__,
        "cuda_available": bool(torch.cuda.is_available()),
        "cuda_device_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "serving_model": {
            "weights_path": str(serving_weights.relative_to(repo_root)),
            "weights_present": serving_weights.exists(),
            "weights_sha256": compute_sha256(serving_weights) if serving_weights.exists() else None,
            "tokenizer_sha256": compute_sha256(serving_tok) if serving_tok.exists() else None,
        },
        "pretrained_base": {
            "weights_path": str(pretrained_weights.relative_to(repo_root)),
            "weights_present": pretrained_weights.exists(),
        },
        "all_46_labels_count": len(STANDARD_INTENTS),
        "supported_12_labels_count": len(CORE_PRODUCT_INTENTS),
        "other_34_labels_count": len(STANDARD_INTENTS - CORE_PRODUCT_INTENTS),
    }


def verify_original_46_label_lineage(
    *,
    preparation_manifest_path: Optional[Path] = None,
    split_report_path: Optional[Path] = None,
    cleaned_csv_override: Optional[Path] = None,
    splits_csv_override: Optional[Path] = None,
    repo_root: Path = REPO_ROOT,
) -> VerifiedOriginalLineage:
    """Verify original 46-label cleaned dataset + split assignments against preparation manifest."""
    prep_dir = repo_root / "artifacts/preparation/03-11-2026-02"
    restored_prep = repo_root / "data/datasets/restored/bitext-12dd624/prep/artifacts/preparation/13-11-2026-00"
    if not (repo_root / "data/datasets/processed/03-11-2026-02/cleaned.csv").is_file() and restored_prep.exists():
        prep_dir = restored_prep
    manifest_p = preparation_manifest_path or (prep_dir / "manifest.json")
    split_rep_p = split_report_path or (prep_dir / "split_report.json")

    if not manifest_p.exists() or not split_rep_p.exists():
        raise MissingLineageBlockerError(
            "Preparation manifest or split_report missing.",
            {
                "status": "BLOCKED_MISSING_PREPARATION_MANIFEST",
                "manifest_exists": manifest_p.exists(),
                "split_report_exists": split_rep_p.exists(),
            },
        )

    manifest = json.loads(manifest_p.read_text(encoding="utf-8"))
    split_rep = json.loads(split_rep_p.read_text(encoding="utf-8"))
    run_id = str(manifest.get("run_id", "03-11-2026-02"))
    expected_cleaned_sha = str(split_rep.get("cleaned_sha256", "")).upper()
    expected_splits_sha = str(split_rep.get("splits_sha256", "")).upper()
    expected_raw_sha = str(manifest.get("input_files", {}).get("raw_sha256", "")).upper()

    def _maybe_path(val: Any) -> Optional[Path]:
        if val is None:
            return None
        s = str(val).strip()
        return Path(s) if s else None

    candidate_cleaned = [
        p for p in (
            cleaned_csv_override,
            repo_root / f"data/datasets/processed/{run_id}/cleaned.csv",
            _maybe_path(manifest.get("output_artifacts", {}).get("cleaned_csv")),
        )
        if p is not None
    ]
    candidate_splits = [
        p for p in (
            splits_csv_override,
            repo_root / f"data/datasets/splits/{run_id}/split_assignments.csv",
            _maybe_path(manifest.get("output_artifacts", {}).get("split_assignments")),
        )
        if p is not None
    ]
    raw_candidates = [
        p for p in (
            repo_root / "data/datasets/bitext-retail-ecommerce-llm-chatbot-training-dataset.csv",
            _maybe_path(manifest.get("input_files", {}).get("raw_dataset")),
        )
        if p is not None
    ]

    cleaned_path = next((p for p in candidate_cleaned if p.is_file()), None)
    splits_path = next((p for p in candidate_splits if p.is_file()), None)

    if cleaned_path is None or splits_path is None:
        details = {
            "status": "BLOCKED_MISSING_ORIGINAL_46_LABEL_DATA",
            "reason": (
                "Verified original 46-label Bitext training data (cleaned.csv and split_assignments.csv) "
                "is absent on disk. Cannot perform 34-label replay or train a valid 46-class candidate "
                "without substituting gold benchmarks or inventing training data."
            ),
            "preparation_run_id": run_id,
            "expected_checksums": {
                "raw_bitext_csv_sha256": expected_raw_sha,
                "cleaned_csv_sha256": expected_cleaned_sha,
                "split_assignments_csv_sha256": expected_splits_sha,
            },
            "checked_paths": {
                "cleaned_csv": [str(p) for p in candidate_cleaned],
                "split_assignments_csv": [str(p) for p in candidate_splits],
                "raw_bitext_csv": [str(p) for p in raw_candidates],
            },
            "present_on_disk": {
                "cleaned_csv": False if cleaned_path is None else str(cleaned_path),
                "split_assignments_csv": False if splits_path is None else str(splits_path),
                "raw_bitext_csv": any(p.is_file() for p in raw_candidates),
            },
        }
        raise MissingLineageBlockerError(details["reason"], details)

    actual_cleaned_sha = compute_sha256(cleaned_path).upper()
    actual_splits_sha = compute_sha256(splits_path).upper()
    if expected_cleaned_sha and actual_cleaned_sha != expected_cleaned_sha:
        raise MissingLineageBlockerError(
            "cleaned.csv SHA-256 mismatch against split_report.json.",
            {
                "status": "BLOCKED_CHECKSUM_MISMATCH",
                "file": str(cleaned_path),
                "expected_sha256": expected_cleaned_sha,
                "actual_sha256": actual_cleaned_sha,
            },
        )
    if expected_splits_sha and actual_splits_sha != expected_splits_sha:
        raise MissingLineageBlockerError(
            "split_assignments.csv SHA-256 mismatch against split_report.json.",
            {
                "status": "BLOCKED_CHECKSUM_MISMATCH",
                "file": str(splits_path),
                "expected_sha256": expected_splits_sha,
                "actual_sha256": actual_splits_sha,
            },
        )

    cleaned_df = pd.read_csv(cleaned_path)
    splits_df = pd.read_csv(splits_path)
    merged = cleaned_df.merge(splits_df, on="sample_id", how="inner", validate="one_to_one")
    if len(merged) != len(cleaned_df):
        raise MissingLineageBlockerError(
            "Sample count mismatch between cleaned.csv and split_assignments.csv.",
            {"status": "BLOCKED_LINEAGE_MISMATCH", "cleaned_len": len(cleaned_df), "merged_len": len(merged)},
        )

    train_df = merged[merged["partition"] == "train"].copy().reset_index(drop=True)
    test_df = merged[merged["partition"] == "test"].copy().reset_index(drop=True)

    if not set(train_df["sample_id"]).isdisjoint(set(test_df["sample_id"])):
        raise MissingLineageBlockerError(
            "Train/test sample_id overlap detected.",
            {"status": "BLOCKED_SPLIT_LEAKAGE"},
        )

    train_intents = set(train_df["intent"].astype(str))
    missing_train = sorted(set(STANDARD_INTENTS) - train_intents)
    if missing_train:
        raise MissingLineageBlockerError(
            f"Original train split missing {len(missing_train)} of 46 labels.",
            {"status": "BLOCKED_INCOMPLETE_46_LABELS", "missing_labels": missing_train},
        )

    return VerifiedOriginalLineage(
        train_df=train_df,
        test_df=test_df,
        cleaned_path=cleaned_path,
        splits_path=splits_path,
        cleaned_sha256=actual_cleaned_sha,
        splits_sha256=actual_splits_sha,
        run_id=run_id,
    )


def compute_baseline_coverage_and_regression(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    """Recompute serving model baseline raw vs correct-intent coverage & strict mandatory metrics."""
    raw_path = repo_root / "artifacts/evaluation/candidate_comparison_20261113/raw_predictions.jsonl"
    acc_path = repo_root / "data/benchmarks/system/v2/acceptance/cases.jsonl"
    fa_path = repo_root / "data/benchmarks/final_acceptance/cases.jsonl"
    noise_path = repo_root / "data/benchmarks/autoeval/v1/ml_noise.jsonl"
    oos_path = repo_root / "data/benchmarks/autoeval/v1/ml_oos.jsonl"

    raw_rows = [json.loads(l) for l in raw_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    acc_gold = {c["id"]: c for c in (json.loads(l) for l in acc_path.read_text(encoding="utf-8").splitlines() if l.strip())}
    fa_gold = {c["id"]: c for c in (json.loads(l) for l in fa_path.read_text(encoding="utf-8").splitlines() if l.strip())}
    noise_gold = {c["id"]: c for c in (json.loads(l) for l in noise_path.read_text(encoding="utf-8").splitlines() if l.strip())}

    cand = "distilbert-supportiq"
    sys_rows = [r for r in raw_rows if r["candidate"] == cand and r["suite"] == "system_acceptance_156"]
    ans_sys = [r for r in sys_rows if acc_gold[r["case_id"]]["expected"].get("answerable") or acc_gold[r["case_id"]]["expected"].get("draft_expected")]
    raw_draft_sys = [r for r in ans_sys if r["engine_recommendation"] == "draft"]
    corr_draft_sys = [r for r in raw_draft_sys if r["predicted_intent"] == acc_gold[r["case_id"]].get("true_intent")]
    mand_rows = [r for r in sys_rows if acc_gold[r["case_id"]]["expected"].get("must_escalate")]
    mand_strict = [r for r in mand_rows if r["adapted_routing_action"] in acc_gold[r["case_id"]]["expected"]["actions"]]
    mand_draft = [r for r in mand_rows if r["engine_recommendation"] == "draft"]

    fa_rows = [r for r in raw_rows if r["candidate"] == cand and r["suite"] == "final_acceptance_24"]
    fa_ans = [r for r in fa_rows if fa_gold[r["case_id"]].get("is_answerable")]
    fa_raw_draft = [r for r in fa_ans if r["engine_recommendation"] == "draft"]
    fa_corr_draft = [r for r in fa_raw_draft if r["predicted_intent"] == fa_gold[r["case_id"]]["intent"]]
    fa_unans = [r for r in fa_rows if not fa_gold[r["case_id"]].get("is_answerable")]
    fa_unans_strict = [r for r in fa_unans if r["action_match"]]

    noise_rows = [r for r in raw_rows if r["candidate"] == cand and r["suite"] == "ml_noise"]
    n_confs = [r["confidence"] for r in noise_rows]
    n_corrs = [r["predicted_intent"] == noise_gold[r["case_id"]]["true_intent"] for r in noise_rows]
    n_ece, _ = M.expected_calibration_error(n_confs, n_corrs, n_bins=10)
    n_brier = sum((c - (1.0 if y else 0.0)) ** 2 for c, y in zip(n_confs, n_corrs)) / len(noise_rows)

    oos_rows = [r for r in raw_rows if r["candidate"] == cand and r["suite"] == "ml_oos"]
    oos_flagged = sum(1 for r in oos_rows if r["recommendation"] in ("abstain", "escalate"))
    oos_drafted = sum(1 for r in oos_rows if r["recommendation"] == "draft")

    return {
        "model_identity": cand,
        "source_raw_predictions": str(raw_path.relative_to(repo_root)),
        "note": "Known regression baseline (frozen acceptance is regression, not new holdout).",
        "system_acceptance_156": {
            "n_total": len(sys_rows),
            "answerable_total": len(ans_sys),
            "raw_draft_eligible_count": len(raw_draft_sys),
            "raw_draft_eligible_rate": round(len(raw_draft_sys) / len(ans_sys), 4),
            "correct_intent_draft_eligible_count": len(corr_draft_sys),
            "correct_intent_draft_eligible_rate": round(len(corr_draft_sys) / len(ans_sys), 4),
            "mandatory_escalation_total": len(mand_rows),
            "mandatory_strict_action_match_count": len(mand_strict),
            "mandatory_strict_action_match_rate": round(len(mand_strict) / len(mand_rows), 4),
            "mandatory_draft_leak_count": len(mand_draft),
            "mandatory_uninjected_fault_cases": [r["case_id"] for r in mand_draft],
        },
        "final_acceptance_24": {
            "n_total": len(fa_rows),
            "answerable_total": len(fa_ans),
            "raw_draft_eligible_count": len(fa_raw_draft),
            "raw_draft_eligible_rate": round(len(fa_raw_draft) / len(fa_ans), 4),
            "correct_intent_draft_eligible_count": len(fa_corr_draft),
            "correct_intent_draft_eligible_rate": round(len(fa_corr_draft) / len(fa_ans), 4),
            "unanswerable_total": len(fa_unans),
            "unanswerable_strict_action_match_count": len(fa_unans_strict),
            "unanswerable_strict_action_match_rate": round(len(fa_unans_strict) / len(fa_unans), 4),
        },
        "ml_noise_420": {
            "n_total": len(noise_rows),
            "overall_accuracy": round(sum(n_corrs) / len(noise_rows), 4),
            "expected_calibration_error": round(float(n_ece), 4),
            "binary_top_label_brier_score": round(float(n_brier), 4),
        },
        "ml_oos_80": {
            "n_total": len(oos_rows),
            "flagged_safe_count": oos_flagged,
            "flagged_safe_rate": round(oos_flagged / len(oos_rows), 4),
            "false_draft_count": oos_drafted,
        },
    }


def fit_temperature_on_calibration_logits(
    logits: np.ndarray,
    labels: np.ndarray,
    *,
    min_temperature: float = 0.75,
    max_temperature: float = 2.5,
) -> float:
    """Fit scalar post-hoc temperature T on disjoint calibration logits via NLL."""
    logits_t = torch.tensor(logits, dtype=torch.float32)
    labels_t = torch.tensor(labels, dtype=torch.long)
    best_t = 1.0
    best_nll = float("inf")
    loss_fn = torch.nn.CrossEntropyLoss()
    for t_cand in np.linspace(min_temperature, max_temperature, 71):
        with torch.no_grad():
            nll = float(loss_fn(logits_t / float(t_cand), labels_t).item())
        if nll < best_nll:
            best_nll = nll
            best_t = float(t_cand)
    return round(best_t, 4)


def build_replay_and_domain_train_df(
    lineage: VerifiedOriginalLineage,
    domain_records: Sequence[Dict[str, Any]],
    *,
    replay_per_other_label: int = 60,
    replay_per_supported_label: int = 30,
    domain_train_repeat: int = 3,
    cal_per_label: int = 5,
    seed: int = 42,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Build balanced 46-label training DataFrame and disjoint original calibration slice."""
    rng = np.random.RandomState(seed)
    replay_frames: List[pd.DataFrame] = []
    cal_bitext_frames: List[pd.DataFrame] = []
    for intent, grp in lineage.train_df.groupby("intent"):
        shuffled = grp.sample(frac=1.0, random_state=rng).reset_index(drop=True)
        cap = replay_per_supported_label if intent in CORE_PRODUCT_INTENTS else replay_per_other_label
        take_replay = min(cap, len(shuffled))
        replay_frames.append(shuffled.iloc[:take_replay][["sample_id", "instruction", "intent"]])
        rem = shuffled.iloc[take_replay:]
        if cal_per_label > 0 and len(rem) > 0:
            take_cal = min(cal_per_label, len(rem))
            cal_bitext_frames.append(rem.iloc[:take_cal][["sample_id", "instruction", "intent"]])

    replay_df = pd.concat(replay_frames, ignore_index=True)
    replay_df["source"] = "bitext_train_replay"

    cal_bitext_df = (
        pd.concat(cal_bitext_frames, ignore_index=True)
        if cal_bitext_frames
        else pd.DataFrame(columns=["sample_id", "instruction", "intent"])
    )
    if not cal_bitext_df.empty:
        cal_bitext_df["source"] = "bitext_train_disjoint_cal"
        if not set(replay_df["sample_id"]).isdisjoint(set(cal_bitext_df["sample_id"])):
            raise AssertionError("Replay and calibration Bitext sample_ids must remain disjoint.")

    dom_train = pd.DataFrame([r for r in domain_records if r["partition"] == "train"])
    dom_train = dom_train[["sample_id", "instruction", "intent"]].copy()
    dom_train["source"] = "policy_domain_train"
    dom_train_repeated = (
        pd.concat([dom_train] * max(1, int(domain_train_repeat)), ignore_index=True)
        if not dom_train.empty
        else dom_train
    )

    combined = pd.concat([replay_df, dom_train_repeated], ignore_index=True)
    if set(combined["intent"].astype(str)) != set(STANDARD_INTENTS):
        raise ValueError("Combined training dataset lost one or more of the 46 required labels.")
    return combined.sample(frac=1.0, random_state=rng).reset_index(drop=True), cal_bitext_df


def evaluate_adapter_on_suites(
    adapter: _CandidateEngineAdapter,
    *,
    repo_root: Path,
    eval_df: pd.DataFrame,
    test_df: pd.DataFrame,
    policy_v2: Any,
    retriever: RetrievalAdapter,
) -> Dict[str, Any]:
    """Evaluate a 46-label adapter offline across holdout, domain, noise, OOD, and regression suites."""
    engine = Engine(
        model=adapter,
        retriever=retriever,
        llm=_OfflineSpyLLM(),
        versions={"engine": "2.0.0", "policy": policy_v2.version, "model": adapter.version},
        policy=policy_v2.model_dump(),
    )

    # 1. Held-out policy domain evaluation groups (separate template families)
    dom_preds_raw = adapter.predict_batch(eval_df["instruction"].tolist(), batch_size=64)
    dom_preds = [r["intent"] for r in dom_preds_raw]
    dom_gold = eval_df["intent"].tolist()
    dom_ans_raw_draft = dom_ans_corr_draft = 0
    for rec_row in eval_df.to_dict(orient="records"):
        ans, _ = engine._analyse({"message": rec_row["instruction"], "as_of": "2026-11-13T00:00:00Z", "order_context": {}})
        if ans["routing"]["recommendation"] == "draft":
            dom_ans_raw_draft += 1
            if ans["intent"]["label"] == rec_row["intent"]:
                dom_ans_corr_draft += 1

    # 2. Original 46-label verified Bitext test split
    test_preds_raw = adapter.predict_batch(test_df["instruction"].tolist(), batch_size=128)
    test_preds = [r["intent"] for r in test_preds_raw]
    test_gold = test_df["intent"].tolist()
    sup_12_mask = [i for i, y in enumerate(test_gold) if y in CORE_PRODUCT_INTENTS]
    other_34_mask = [i for i, y in enumerate(test_gold) if y not in CORE_PRODUCT_INTENTS]

    # 3. AutoEval ml_noise (420 cases)
    noise_cases = [
        json.loads(l)
        for l in (repo_root / "data/benchmarks/autoeval/v1/ml_noise.jsonl").read_text(encoding="utf-8").splitlines()
        if l.strip()
    ]
    noise_preds_raw = adapter.predict_batch([c["text"] for c in noise_cases], batch_size=64)
    noise_by_kind: Dict[str, List[Tuple[str, str, float]]] = defaultdict(list)
    n_confs: List[float] = []
    n_corrs: List[bool] = []
    n_safe = 0
    for c, pred in zip(noise_cases, noise_preds_raw):
        vkind = c.get("kind", c.get("variant_kind", "clean"))
        gold_i = c["true_intent"]
        pred_i = pred["intent"]
        conf = pred["confidence"]
        corr = pred_i == gold_i
        n_confs.append(conf)
        n_corrs.append(corr)
        if corr or conf < 0.65 or pred_i not in SUPPORTED_12_INTENTS:
            n_safe += 1
        noise_by_kind[vkind].append((gold_i, pred_i, conf))

    noise_ece, _ = M.expected_calibration_error(n_confs, n_corrs, n_bins=10)
    noise_brier = sum((c - (1.0 if y else 0.0)) ** 2 for c, y in zip(n_confs, n_corrs)) / max(1, len(noise_cases))
    noise_kind_metrics: Dict[str, Dict[str, Any]] = {}
    for vk in ("clean", "casual", "typo"):
        rows = noise_by_kind[vk]
        g_list = [r[0] for r in rows]
        p_list = [r[1] for r in rows]
        noise_kind_metrics[vk] = {
            "n": len(rows),
            "accuracy": round(float(accuracy_score(g_list, p_list)), 4) if rows else 0.0,
            "macro_f1": round(float(f1_score(g_list, p_list, average="macro", zero_division=0)), 4) if rows else 0.0,
        }

    # 4. AutoEval ml_oos (80 cases) via Engine._analyse
    oos_cases = [
        json.loads(l)
        for l in (repo_root / "data/benchmarks/autoeval/v1/ml_oos.jsonl").read_text(encoding="utf-8").splitlines()
        if l.strip()
    ]
    oos_flagged = oos_drafted = oos_low_conf = 0
    for c in oos_cases:
        ans, _ = engine._analyse({"message": c["text"], "as_of": "2026-11-13T00:00:00Z", "order_context": {}})
        rec = ans["routing"]["recommendation"]
        reasons = ans["routing"]["reason_codes"]
        if rec in ("abstain", "escalate"):
            oos_flagged += 1
        if rec == "draft":
            oos_drafted += 1
        if "low_confidence" in reasons or ans["intent"]["probability"] < 0.65:
            oos_low_conf += 1

    # 5. Known Regression: system_acceptance_156
    acc_cases = [
        json.loads(l)
        for l in (repo_root / "data/benchmarks/system/v2/acceptance/cases.jsonl").read_text(encoding="utf-8").splitlines()
        if l.strip()
    ]
    sys_ans_tot = sys_ans_raw_draft = sys_ans_corr_draft = 0
    sys_mand_tot = sys_mand_strict = sys_mand_draft = 0
    sys_action_match = sys_sens_tot = sys_sens_auth = 0
    sys_mand_leak_ids: List[str] = []
    for c in acc_cases:
        order_ctx = c.get("context", {}).get("extracted_slots", {})
        ans, _ = engine._analyse({"message": c["text"], "as_of": "2026-11-13T00:00:00Z", "order_context": order_ctx})
        rec = ans["routing"]["recommendation"]
        reasons = ans["routing"]["reason_codes"]
        pred_i = ans["intent"]["label"]
        adapted = {"draft": "retrieve_draft", "abstain": "manual_fallback"}.get(rec, rec)
        exp = c.get("expected", {})
        if adapted in exp.get("actions", []):
            sys_action_match += 1
        if exp.get("answerable") or exp.get("draft_expected"):
            sys_ans_tot += 1
            if rec == "draft":
                sys_ans_raw_draft += 1
                if pred_i == c.get("true_intent"):
                    sys_ans_corr_draft += 1
        if c.get("true_intent") in policy_v2.sensitive_action_intents or pred_i in policy_v2.sensitive_action_intents:
            sys_sens_tot += 1
            if "requires_authority" in reasons:
                sys_sens_auth += 1
        if exp.get("must_escalate"):
            sys_mand_tot += 1
            if adapted in exp.get("actions", []):
                sys_mand_strict += 1
            if rec == "draft":
                sys_mand_draft += 1
                sys_mand_leak_ids.append(c["id"])

    # 6. Known Regression: final_acceptance_24
    fa_cases = [
        json.loads(l)
        for l in (repo_root / "data/benchmarks/final_acceptance/cases.jsonl").read_text(encoding="utf-8").splitlines()
        if l.strip()
    ]
    fa_ans_tot = fa_ans_raw_draft = fa_ans_corr_draft = fa_ans_corr_intent = 0
    fa_unans_tot = fa_unans_strict = fa_unans_draft = 0
    fa_case_details: List[Dict[str, Any]] = []
    for c in fa_cases:
        order_ctx = {"order_id": c["order_id"]} if c.get("order_id") else {}
        ans, _ = engine._analyse({"message": c["query"], "as_of": "2026-11-13T00:00:00Z", "order_context": order_ctx})
        rec = ans["routing"]["recommendation"]
        adapted = {"draft": "retrieve_draft", "abstain": "manual_fallback"}.get(rec, rec)
        pred_i = ans["intent"]["label"]
        conf = round(float(ans["intent"]["probability"]), 4)
        exp_mapped = {"draft": "retrieve_draft", "abstain": "manual_fallback"}.get(c["expected_action"], c["expected_action"])
        action_match = adapted == exp_mapped
        if c.get("is_answerable"):
            fa_ans_tot += 1
            if pred_i == c["intent"]:
                fa_ans_corr_intent += 1
            if rec == "draft":
                fa_ans_raw_draft += 1
                if pred_i == c["intent"]:
                    fa_ans_corr_draft += 1
        else:
            fa_unans_tot += 1
            if action_match:
                fa_unans_strict += 1
            if rec == "draft":
                fa_unans_draft += 1
        fa_case_details.append(
            {
                "case_id": c["id"],
                "is_answerable": bool(c.get("is_answerable")),
                "true_intent": c["intent"],
                "predicted_intent": pred_i,
                "confidence": conf,
                "recommendation": rec,
                "adapted_action": adapted,
                "expected_action": exp_mapped,
                "action_match": action_match,
            }
        )

    return {
        "model_identity": {
            "name": adapter.name,
            "version": adapter.version,
            "weights_sha256": adapter.weights_sha256,
            "tokenizer_sha256": adapter.tokenizer_sha256,
            "temperature": adapter.temperature,
        },
        "held_out_domain_eval": {
            "n_total": len(dom_gold),
            "accuracy": round(float(accuracy_score(dom_gold, dom_preds)), 4),
            "macro_f1": round(float(f1_score(dom_gold, dom_preds, average="macro", zero_division=0)), 4),
            "raw_draft_eligible_count": dom_ans_raw_draft,
            "raw_draft_eligible_rate": round(dom_ans_raw_draft / max(1, len(dom_gold)), 4),
            "correct_intent_draft_eligible_count": dom_ans_corr_draft,
            "correct_intent_draft_eligible_rate": round(dom_ans_corr_draft / max(1, len(dom_gold)), 4),
        },
        "original_46_label_test": {
            "n_total": len(test_gold),
            "all_46_accuracy": round(float(accuracy_score(test_gold, test_preds)), 4),
            "all_46_macro_f1": round(float(f1_score(test_gold, test_preds, average="macro", zero_division=0)), 4),
            "supported_12_n": len(sup_12_mask),
            "supported_12_accuracy": round(
                float(accuracy_score([test_gold[i] for i in sup_12_mask], [test_preds[i] for i in sup_12_mask])),
                4,
            ) if sup_12_mask else None,
            "other_34_n": len(other_34_mask),
            "other_34_accuracy": round(
                float(accuracy_score([test_gold[i] for i in other_34_mask], [test_preds[i] for i in other_34_mask])),
                4,
            ) if other_34_mask else None,
        },
        "ml_noise_420": {
            "n_total": len(noise_cases),
            "overall_accuracy": round(sum(n_corrs) / max(1, len(noise_cases)), 4),
            "expected_calibration_error": round(float(noise_ece), 4),
            "binary_top_label_brier_score": round(float(noise_brier), 4),
            "safe_routing_count": n_safe,
            "safe_routing_rate": round(n_safe / max(1, len(noise_cases)), 4),
            "casual_f1_drop": round(noise_kind_metrics["clean"]["macro_f1"] - noise_kind_metrics["casual"]["macro_f1"], 4),
            "typo_f1_drop": round(noise_kind_metrics["clean"]["macro_f1"] - noise_kind_metrics["typo"]["macro_f1"], 4),
            "by_kind": noise_kind_metrics,
        },
        "ml_oos_80": {
            "n_total": len(oos_cases),
            "flagged_safe_count": oos_flagged,
            "flagged_safe_rate": round(oos_flagged / max(1, len(oos_cases)), 4),
            "low_conf_count": oos_low_conf,
            "false_draft_count": oos_drafted,
        },
        "known_regression_system_acceptance_156": {
            "n_total": len(acc_cases),
            "overall_action_match_count": sys_action_match,
            "overall_action_match_rate": round(sys_action_match / max(1, len(acc_cases)), 4),
            "answerable_total": sys_ans_tot,
            "raw_draft_eligible_count": sys_ans_raw_draft,
            "raw_draft_eligible_rate": round(sys_ans_raw_draft / max(1, sys_ans_tot), 4),
            "correct_intent_draft_eligible_count": sys_ans_corr_draft,
            "correct_intent_draft_eligible_rate": round(sys_ans_corr_draft / max(1, sys_ans_tot), 4),
            "sensitive_cases_total": sys_sens_tot,
            "sensitive_authority_count": sys_sens_auth,
            "sensitive_authority_rate": round(sys_sens_auth / max(1, sys_sens_tot), 4),
            "mandatory_escalation_total": sys_mand_tot,
            "mandatory_strict_action_match_count": sys_mand_strict,
            "mandatory_strict_action_match_rate": round(sys_mand_strict / max(1, sys_mand_tot), 4),
            "mandatory_draft_leak_count": sys_mand_draft,
            "mandatory_draft_leak_cases": sys_mand_leak_ids,
        },
        "known_regression_final_acceptance_24": {
            "n_total": len(fa_cases),
            "answerable_total": fa_ans_tot,
            "answerable_correct_intent_count": fa_ans_corr_intent,
            "answerable_correct_intent_rate": round(fa_ans_corr_intent / max(1, fa_ans_tot), 4),
            "raw_draft_eligible_count": fa_ans_raw_draft,
            "raw_draft_eligible_rate": round(fa_ans_raw_draft / max(1, fa_ans_tot), 4),
            "correct_intent_draft_eligible_count": fa_ans_corr_draft,
            "correct_intent_draft_eligible_rate": round(fa_ans_corr_draft / max(1, fa_ans_tot), 4),
            "unanswerable_total": fa_unans_tot,
            "unanswerable_strict_action_match_count": fa_unans_strict,
            "unanswerable_strict_action_match_rate": round(fa_unans_strict / max(1, fa_unans_tot), 4),
            "unanswerable_draft_leak_count": fa_unans_draft,
            "cases": fa_case_details,
        },
    }


def run_bounded_candidate_experiment(
    output_dir: Path,
    *,
    repo_root: Path = REPO_ROOT,
    base_model_dir: Optional[Path] = None,
    preparation_manifest_path: Optional[Path] = None,
    split_report_path: Optional[Path] = None,
    cleaned_csv_override: Optional[Path] = None,
    splits_csv_override: Optional[Path] = None,
    max_budget_seconds: float = MAX_TRAINING_BUDGET_SECONDS,
    epochs: int = 2,
    batch_size: int = 32,
    lr: float = 2e-5,
    replay_per_other_label: int = 60,
    replay_per_supported_label: int = 30,
    domain_train_repeat: int = 3,
    cal_per_label: int = 5,
    freeze_bottom_layers: int = 2,
    seed: int = 42,
) -> Dict[str, Any]:
    """Execute Task A experiment, failing closed if verified 46-label lineage is absent."""
    if max_budget_seconds > MAX_TRAINING_BUDGET_SECONDS:
        raise ValueError(f"max_budget_seconds={max_budget_seconds} exceeds 30-min cap ({MAX_TRAINING_BUDGET_SECONDS}s).")

    start_wall = time.perf_counter()
    output_dir.mkdir(parents=True, exist_ok=True)

    compute_inv = collect_compute_and_model_inventory(repo_root)
    domain_manifest = export_domain_dataset(output_dir / "domain_templates", repo_root=repo_root)
    domain_path = Path(domain_manifest["dataset_path"])
    if not domain_path.is_absolute():
        domain_path = repo_root / domain_path
    domain_records = [json.loads(l) for l in domain_path.read_text(encoding="utf-8").splitlines() if l.strip()]

    try:
        lineage = verify_original_46_label_lineage(
            preparation_manifest_path=preparation_manifest_path,
            split_report_path=split_report_path,
            cleaned_csv_override=cleaned_csv_override,
            splits_csv_override=splits_csv_override,
            repo_root=repo_root,
        )
    except MissingLineageBlockerError as exc:
        baseline = compute_baseline_coverage_and_regression(repo_root)
        blocker_report = {
            "status": "BLOCKED",
            "blocker": exc.blocker_details,
            "budget_policy": {"max_training_seconds": max_budget_seconds, "training_executed": False},
            "compute_and_model_inventory": compute_inv,
            "domain_templates_manifest": domain_manifest,
            "baseline_serving_accounting": baseline,
        }
        (output_dir / "blocker_and_baseline_report.json").write_text(
            json.dumps(blocker_report, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return blocker_report

    model_src = base_model_dir or (repo_root / "artifacts/models/trained/distilbert-supportiq")
    if not (model_src / "model.safetensors").exists():
        raise FileNotFoundError(f"Base model weights missing at {model_src}")

    torch.manual_seed(seed)
    np.random.seed(seed)

    classes = sorted(STANDARD_INTENTS)
    label2id = {c: i for i, c in enumerate(classes)}
    id2label = {i: c for i, c in enumerate(classes)}

    train_df, cal_bitext_df = build_replay_and_domain_train_df(
        lineage,
        domain_records,
        replay_per_other_label=replay_per_other_label,
        replay_per_supported_label=replay_per_supported_label,
        domain_train_repeat=domain_train_repeat,
        cal_per_label=cal_per_label,
        seed=seed,
    )
    dom_cal_df = pd.DataFrame([r for r in domain_records if r["partition"] == "calibration"])[["sample_id", "instruction", "intent"]].copy()
    dom_cal_df["source"] = "policy_domain_cal"
    cal_df = pd.concat([dom_cal_df, cal_bitext_df], ignore_index=True) if not cal_bitext_df.empty else dom_cal_df
    eval_df = pd.DataFrame([r for r in domain_records if r["partition"] == "evaluation"])

    tokenizer = AutoTokenizer.from_pretrained(str(model_src))
    model = AutoModelForSequenceClassification.from_pretrained(
        str(model_src),
        num_labels=len(classes),
        id2label=id2label,
        label2id=label2id,
        ignore_mismatched_sizes=False,
    )
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)

    n_freeze = max(0, min(freeze_bottom_layers, len(model.distilbert.transformer.layer)))
    for layer in model.distilbert.transformer.layer[:n_freeze]:
        for param in layer.parameters():
            param.requires_grad = False

    train_enc = tokenizer(train_df["instruction"].tolist(), truncation=True, padding=True, max_length=64, return_tensors="pt")
    train_ds = _TokenizedDataset(train_enc, [label2id[y] for y in train_df["intent"]])
    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True)

    optimizer = torch.optim.AdamW(filter(lambda p: p.requires_grad, model.parameters()), lr=lr)
    total_steps = max(1, len(train_loader) * epochs)
    scheduler = get_linear_schedule_with_warmup(optimizer, num_warmup_steps=max(1, total_steps // 10), num_training_steps=total_steps)
    loss_fn = torch.nn.CrossEntropyLoss()

    budget_exceeded = False
    model.train()
    for _epoch in range(epochs):
        for batch in train_loader:
            if time.perf_counter() - start_wall > max_budget_seconds:
                budget_exceeded = True
                break
            optimizer.zero_grad()
            out = model(
                input_ids=batch["input_ids"].to(device),
                attention_mask=batch["attention_mask"].to(device),
            )
            loss = loss_fn(out.logits, batch["labels"].to(device))
            loss.backward()
            optimizer.step()
            scheduler.step()
        if budget_exceeded:
            break
    train_elapsed_seconds = round(time.perf_counter() - start_wall, 2)

    candidate_dir = output_dir / "candidate_model"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(candidate_dir)
    tokenizer.save_pretrained(candidate_dir)

    # Fit post-hoc temperature scaling ONLY on disjoint calibration split
    model.eval()
    cal_logits_list: List[np.ndarray] = []
    cal_texts = cal_df["instruction"].tolist()
    for start in range(0, len(cal_texts), 64):
        cal_enc = tokenizer(cal_texts[start : start + 64], truncation=True, padding="max_length", max_length=64, return_tensors="pt")
        with torch.inference_mode():
            logits_chunk = model(
                input_ids=cal_enc["input_ids"].to(device),
                attention_mask=cal_enc["attention_mask"].to(device),
            ).logits.cpu().numpy()
        cal_logits_list.append(logits_chunk)
    cal_logits = np.concatenate(cal_logits_list, axis=0)
    cal_labels = np.array([label2id[y] for y in cal_df["intent"]], dtype=np.int64)
    temperature = fit_temperature_on_calibration_logits(cal_logits, cal_labels)

    policy_v2 = load_policy_v2()
    retriever = RetrievalAdapter(kb_path=str(repo_root / "data/knowledge/approved_kb.v2.json"))

    baseline_adapter = _CandidateEngineAdapter(
        "distilbert-supportiq",
        model_src,
        "v1.0.0-serving",
        temperature=1.0,
    )
    candidate_adapter = _CandidateEngineAdapter(
        "distilbert-supportiq-task-a-candidate",
        candidate_dir,
        "v1.2.0-task-a-candidate",
        temperature=temperature,
    )

    baseline_eval = evaluate_adapter_on_suites(
        baseline_adapter,
        repo_root=repo_root,
        eval_df=eval_df,
        test_df=lineage.test_df,
        policy_v2=policy_v2,
        retriever=retriever,
    )
    candidate_eval = evaluate_adapter_on_suites(
        candidate_adapter,
        repo_root=repo_root,
        eval_df=eval_df,
        test_df=lineage.test_df,
        policy_v2=policy_v2,
        retriever=retriever,
    )

    report = {
        "status": "SUCCEEDED",
        "budget_policy": {
            "max_training_seconds": max_budget_seconds,
            "training_elapsed_seconds": train_elapsed_seconds,
            "total_elapsed_seconds": round(time.perf_counter() - start_wall, 2),
            "budget_exceeded": budget_exceeded,
            "epochs": epochs,
            "batch_size": batch_size,
            "lr": lr,
            "freeze_bottom_layers": n_freeze,
        },
        "training_composition": {
            "total_train_rows": int(len(train_df)),
            "bitext_replay_rows": int((train_df["source"] == "bitext_train_replay").sum()),
            "policy_domain_train_rows": int((train_df["source"] == "policy_domain_train").sum()),
            "domain_train_repeat": domain_train_repeat,
            "calibration_rows": int(len(cal_df)),
            "domain_calibration_rows": int(len(dom_cal_df)),
            "bitext_calibration_rows": int(len(cal_bitext_df)),
            "eval_domain_rows": int(len(eval_df)),
        },
        "candidate_identity": {
            "name": candidate_adapter.name,
            "version": candidate_adapter.version,
            "model_dir": str(candidate_dir.relative_to(repo_root)) if candidate_dir.is_relative_to(repo_root) else str(candidate_dir),
            "weights_sha256": candidate_adapter.weights_sha256,
            "tokenizer_sha256": candidate_adapter.tokenizer_sha256,
            "temperature": temperature,
            "serving_assets_modified": False,
        },
        "lineage": {
            "run_id": lineage.run_id,
            "cleaned_sha256": lineage.cleaned_sha256,
            "splits_sha256": lineage.splits_sha256,
        },
        "compute_and_model_inventory": compute_inv,
        "domain_templates_manifest": domain_manifest,
        "baseline_serving_evaluation": baseline_eval,
        "candidate_evaluation": candidate_eval,
    }
    (output_dir / "candidate_experiment_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return report


if __name__ == "__main__":
    out_dir = REPO_ROOT / "artifacts/evaluation/task_a_20261113"
    res = run_bounded_candidate_experiment(out_dir)
    print(json.dumps(res, indent=2, ensure_ascii=False))
