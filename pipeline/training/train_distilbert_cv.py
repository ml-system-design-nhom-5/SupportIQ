"""10-fold cross-validation and full refitting pipeline for DistilBERT on SupportIQ."""

from __future__ import annotations

import argparse
import datetime
import gc
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Collection, Sequence

import numpy as np
import pandas as pd
import torch
from sklearn.metrics import accuracy_score, f1_score
from torch.utils.data import DataLoader, Dataset
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    get_linear_schedule_with_warmup,
)

from pipeline.preparation.utils import (
    CORE_PRODUCT_INTENTS,
    STANDARD_INTENTS,
    compute_sha256,
    save_json,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


class IntentDataset(Dataset):
    """PyTorch Dataset for tokenized intent classification samples."""

    def __init__(self, encodings: dict[str, torch.Tensor], labels: list[int]) -> None:
        self.encodings = encodings
        self.labels = torch.tensor(labels, dtype=torch.long)

    def __len__(self) -> int:
        return len(self.labels)

    def __getitem__(self, idx: int) -> dict[str, torch.Tensor]:
        item = {key: val[idx] for key, val in self.encodings.items()}
        item["labels"] = self.labels[idx]
        return item


def load_and_verify_cv_data(
    cleaned_csv: str | Path,
    splits_csv: str | Path,
    *,
    n_folds: int = 10,
    expected_train_count: int | None = 37911,
    expected_intents: Collection[str] = STANDARD_INTENTS,
) -> tuple[pd.DataFrame, list[str]]:
    """Load cleaned instructions and split assignments, enforcing strict hold-out isolation."""
    c_path = Path(cleaned_csv)
    s_path = Path(splits_csv)

    if not c_path.exists():
        raise FileNotFoundError(f"cleaned_csv not found at {c_path}")
    if not s_path.exists():
        raise FileNotFoundError(f"splits_csv not found at {s_path}")

    cleaned = pd.read_csv(c_path)
    splits = pd.read_csv(s_path)

    for col in ("sample_id", "instruction", "intent"):
        if col not in cleaned.columns:
            raise ValueError(f"cleaned_csv missing required column {col!r}")
    for col in ("sample_id", "partition", "fold"):
        if col not in splits.columns:
            raise ValueError(f"splits_csv missing required column {col!r}")

    # Check taxonomy
    expected_set = set(expected_intents)
    actual_intents = set(cleaned["intent"].astype(str))
    invalid = actual_intents - expected_set
    if invalid:
        raise ValueError(f"cleaned_csv contains labels outside taxonomy: {sorted(invalid)}")

    # Merge
    merged = cleaned.merge(splits, on="sample_id", how="inner", validate="one_to_one")
    if len(merged) != len(cleaned):
        raise ValueError("Mismatch between cleaned samples and split assignments")

    # Isolate partitions
    train_df = merged[merged["partition"] == "train"].copy().reset_index(drop=True)
    test_df = merged[merged["partition"] == "test"].copy().reset_index(drop=True)

    test_ids = test_df["sample_id"].astype(str).tolist()
    train_ids = train_df["sample_id"].astype(str).tolist()

    if not set(train_ids).isdisjoint(set(test_ids)):
        raise ValueError("Data leakage detected: train and test partitions share sample IDs")

    if expected_train_count is not None and len(train_df) != expected_train_count:
        raise ValueError(f"Expected {expected_train_count} train samples, found {len(train_df)}")

    actual_folds = sorted(train_df["fold"].unique())
    expected_folds = list(range(n_folds))
    if actual_folds != expected_folds:
        raise ValueError(f"Expected folds {expected_folds}, found {actual_folds}")

    return train_df, test_ids


def aggregate_cv_metrics(fold_df: pd.DataFrame, n_folds: int = 10) -> dict[str, Any]:
    """Calculate mean and standard deviation across fold validation metrics."""
    if len(fold_df) != n_folds:
        raise ValueError(f"fold_df has {len(fold_df)} rows, expected {n_folds}")

    macro_vals = fold_df["macro_f1"].astype(float).values
    acc_vals = fold_df["accuracy"].astype(float).values
    weighted_vals = fold_df["weighted_f1"].astype(float).values

    return {
        "n_folds": n_folds,
        "macro_f1_mean": float(np.mean(macro_vals)),
        "macro_f1_std": float(np.std(macro_vals, ddof=1) if len(macro_vals) > 1 else 0.0),
        "accuracy_mean": float(np.mean(acc_vals)),
        "accuracy_std": float(np.std(acc_vals, ddof=1) if len(acc_vals) > 1 else 0.0),
        "weighted_f1_mean": float(np.mean(weighted_vals)),
        "weighted_f1_std": float(np.std(weighted_vals, ddof=1) if len(weighted_vals) > 1 else 0.0),
    }


def save_train_sample_ids(
    train_sample_ids: Sequence[str],
    test_sample_ids: Sequence[str],
    output_path: str | Path,
) -> None:
    """Save sorted train sample IDs verifying 0 overlap with hold-out test set."""
    train_list = [str(x) for x in train_sample_ids]
    test_set = set(str(x) for x in test_sample_ids)

    overlap = set(train_list) & test_set
    if overlap:
        raise ValueError(f"Cannot save membership evidence: {len(overlap)} samples overlap with test set")

    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(train_list, f, indent=2)


def get_default_device() -> torch.device:
    """Return CUDA device if available, else CPU."""
    if torch.cuda.is_available():
        return torch.device("cuda:0")
    return torch.device("cpu")


def train_epoch(
    model: torch.nn.Module,
    dataloader: DataLoader,
    optimizer: torch.optim.Optimizer,
    scheduler: Any,
    scaler: torch.amp.GradScaler | None,
    device: torch.device,
) -> float:
    """Execute one training epoch with mixed precision if available."""
    model.train()
    total_loss = 0.0
    use_cuda = device.type == "cuda"

    for batch in dataloader:
        optimizer.zero_grad()
        input_ids = batch["input_ids"].to(device, non_blocking=use_cuda)
        attention_mask = batch["attention_mask"].to(device, non_blocking=use_cuda)
        labels = batch["labels"].to(device, non_blocking=use_cuda)

        if use_cuda and scaler is not None:
            with torch.amp.autocast(device_type="cuda", dtype=torch.float16):
                outputs = model(input_ids=input_ids, attention_mask=attention_mask, labels=labels)
                loss = outputs.loss
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
        else:
            outputs = model(input_ids=input_ids, attention_mask=attention_mask, labels=labels)
            loss = outputs.loss
            loss.backward()
            optimizer.step()

        scheduler.step()
        total_loss += loss.item()

    return total_loss / len(dataloader)


def evaluate(
    model: torch.nn.Module,
    dataloader: DataLoader,
    classes: list[str],
    device: torch.device,
) -> tuple[float, float, float, list[int]]:
    """Evaluate model on validation loader returning macro_f1, accuracy, weighted_f1, and pred_ids."""
    model.eval()
    use_cuda = device.type == "cuda"
    val_preds: list[int] = []
    val_targets: list[int] = []

    with torch.inference_mode():
        for batch in dataloader:
            input_ids = batch["input_ids"].to(device, non_blocking=use_cuda)
            attention_mask = batch["attention_mask"].to(device, non_blocking=use_cuda)

            if use_cuda:
                with torch.amp.autocast(device_type="cuda", dtype=torch.float16):
                    outputs = model(input_ids=input_ids, attention_mask=attention_mask)
            else:
                outputs = model(input_ids=input_ids, attention_mask=attention_mask)

            preds = outputs.logits.argmax(dim=-1).cpu().tolist()
            val_preds.extend(preds)
            val_targets.extend(batch["labels"].tolist())

    labels_range = list(range(len(classes)))
    macro_f1 = float(f1_score(val_targets, val_preds, labels=labels_range, average="macro", zero_division=0))
    weighted_f1 = float(f1_score(val_targets, val_preds, labels=labels_range, average="weighted", zero_division=0))
    accuracy = float(accuracy_score(val_targets, val_preds))

    return macro_f1, accuracy, weighted_f1, val_preds


def run_distilbert_10fold_cv(
    pretrained_model_dir: str | Path,
    cleaned_csv: str | Path,
    splits_csv: str | Path,
    output_dir: str | Path,
    cv_metrics_dir: str | Path,
    *,
    epochs: int = 2,
    batch_size: int = 32,
    lr: float = 3e-5,
    max_length: int = 64,
    n_folds: int = 10,
    device: torch.device | None = None,
    seed: int = 42,
) -> dict[str, Any]:
    """Execute end-to-end 10-fold CV on 37,911 development samples, then refit final model."""
    torch.manual_seed(seed)
    np.random.seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)

    if device is None:
        device = get_default_device()

    pretrained_path = Path(pretrained_model_dir)
    out_dir = Path(output_dir)
    cv_dir = Path(cv_metrics_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cv_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("SupportIQ DistilBERT 10-Fold Cross-Validation & Retraining Pipeline")
    print(f"Pretrained base: {pretrained_path}")
    print(f"Device: {device} ({torch.cuda.get_device_name(device) if device.type == 'cuda' else 'CPU'})")
    print(f"Target model dir: {out_dir}")
    print(f"CV metrics dir: {cv_dir}")
    print(f"Epochs per fold: {epochs} | Batch size: {batch_size} | Learning rate: {lr}")
    print("=" * 70)

    # 1. Load data
    train_dev, test_ids = load_and_verify_cv_data(
        cleaned_csv,
        splits_csv,
        n_folds=n_folds,
        expected_train_count=37911,
    )
    classes = sorted(STANDARD_INTENTS)
    num_labels = len(classes)
    label2id = {c: i for i, c in enumerate(classes)}
    id2label = {i: c for i, c in enumerate(classes)}

    print(f"Loaded {len(train_dev)} development samples across {n_folds} folds.")
    print(f"Hold-out test samples isolated: {len(test_ids)}.")

    # 2. Tokenizer
    tokenizer = AutoTokenizer.from_pretrained(pretrained_path)

    # 3. 10-Fold CV Loop
    fold_metric_rows: list[dict[str, Any]] = []
    oof_rows: list[dict[str, Any]] = []
    cv_start_time = time.time()

    for fold in range(n_folds):
        fold_start = time.time()
        print(f"\n>>> Starting Fold {fold + 1}/{n_folds}...")

        fold_train = train_dev[train_dev["fold"] != fold].reset_index(drop=True)
        fold_val = train_dev[train_dev["fold"] == fold].reset_index(drop=True)

        # Tokenize fold splits
        train_enc = tokenizer(
            fold_train["instruction"].tolist(),
            truncation=True,
            padding=True,
            max_length=max_length,
            return_tensors="pt",
        )
        val_enc = tokenizer(
            fold_val["instruction"].tolist(),
            truncation=True,
            padding=True,
            max_length=max_length,
            return_tensors="pt",
        )

        train_labels = [label2id[c] for c in fold_train["intent"]]
        val_labels = [label2id[c] for c in fold_val["intent"]]

        train_dataset = IntentDataset(train_enc, train_labels)
        val_dataset = IntentDataset(val_enc, val_labels)

        train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
        val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False)

        # Init fresh fold model from pretrained base
        model = AutoModelForSequenceClassification.from_pretrained(
            pretrained_path,
            num_labels=num_labels,
            id2label=id2label,
            label2id=label2id,
        ).to(device)

        # Freeze bottom 3 layers to retain pretrained general knowledge and accelerate training
        for p in model.distilbert.transformer.layer[:3].parameters():
            p.requires_grad = False

        optimizer = torch.optim.AdamW(filter(lambda p: p.requires_grad, model.parameters()), lr=lr)
        total_steps = len(train_loader) * epochs
        warmup_steps = int(0.1 * total_steps)
        scheduler = get_linear_schedule_with_warmup(optimizer, warmup_steps, total_steps)
        scaler = torch.amp.GradScaler("cuda") if device.type == "cuda" else None

        # Train fold
        for ep in range(1, epochs + 1):
            ep_start = time.time()
            avg_loss = train_epoch(model, train_loader, optimizer, scheduler, scaler, device)
            ep_dur = time.time() - ep_start
            print(f"  Fold {fold} | Epoch {ep}/{epochs} Loss: {avg_loss:.4f} ({ep_dur:.1f}s)")

        # Evaluate fold
        macro_f1, acc, weighted_f1, pred_ids = evaluate(model, val_loader, classes, device)
        fold_dur = time.time() - fold_start
        print(
            f"  Fold {fold} Complete! Macro-F1: {macro_f1:.4f} | Accuracy: {acc:.4f} | "
            f"Weighted-F1: {weighted_f1:.4f} | Time: {fold_dur:.1f}s"
        )

        fold_metric_rows.append({
            "fold": fold,
            "n_train": len(fold_train),
            "n_val": len(fold_val),
            "macro_f1": macro_f1,
            "accuracy": acc,
            "weighted_f1": weighted_f1,
            "duration_seconds": round(fold_dur, 2),
        })

        for sid, y_true, pid in zip(fold_val["sample_id"], fold_val["intent"], pred_ids):
            oof_rows.append({
                "sample_id": sid,
                "fold": fold,
                "y_true": y_true,
                "y_pred": id2label[pid],
            })

        # Cleanup GPU memory
        del model, optimizer, scheduler, train_loader, val_loader, train_dataset, val_dataset
        if device.type == "cuda":
            torch.cuda.empty_cache()
        gc.collect()

    cv_total_time = time.time() - cv_start_time
    fold_df = pd.DataFrame(fold_metric_rows)
    oof_df = pd.DataFrame(oof_rows)

    fold_df.to_csv(cv_dir / "fold_metrics.csv", index=False)
    oof_df.to_csv(cv_dir / "oof_predictions.csv", index=False)

    summary_cv = aggregate_cv_metrics(fold_df, n_folds=n_folds)
    print("\n" + "=" * 60)
    print("10-Fold Cross-Validation Results across 37,911 samples:")
    print(f"  Macro-F1:    {summary_cv['macro_f1_mean']:.4f} ± {summary_cv['macro_f1_std']:.4f}")
    print(f"  Accuracy:    {summary_cv['accuracy_mean']:.4f} ± {summary_cv['accuracy_std']:.4f}")
    print(f"  Weighted-F1: {summary_cv['weighted_f1_mean']:.4f} ± {summary_cv['weighted_f1_std']:.4f}")
    print(f"  Total CV Time: {cv_total_time:.1f}s ({cv_total_time/60:.2f} mins)")
    print("=" * 60)

    # 4. Final Refit on all 37,911 samples
    print("\n>>> Refitting final DistilBERT model on all 37,911 development samples...")
    refit_start = time.time()

    all_train_enc = tokenizer(
        train_dev["instruction"].tolist(),
        truncation=True,
        padding=True,
        max_length=max_length,
        return_tensors="pt",
    )
    all_train_labels = [label2id[c] for c in train_dev["intent"]]
    all_train_dataset = IntentDataset(all_train_enc, all_train_labels)
    all_train_loader = DataLoader(all_train_dataset, batch_size=batch_size, shuffle=True)

    final_model = AutoModelForSequenceClassification.from_pretrained(
        pretrained_path,
        num_labels=num_labels,
        id2label=id2label,
        label2id=label2id,
    ).to(device)

    for p in final_model.distilbert.transformer.layer[:3].parameters():
        p.requires_grad = False

    final_optimizer = torch.optim.AdamW(filter(lambda p: p.requires_grad, final_model.parameters()), lr=lr)
    final_total_steps = len(all_train_loader) * epochs
    final_warmup = int(0.1 * final_total_steps)
    final_scheduler = get_linear_schedule_with_warmup(final_optimizer, final_warmup, final_total_steps)
    final_scaler = torch.amp.GradScaler("cuda") if device.type == "cuda" else None

    for ep in range(1, epochs + 1):
        ep_start = time.time()
        avg_loss = train_epoch(final_model, all_train_loader, final_optimizer, final_scheduler, final_scaler, device)
        print(f"  Final Refit | Epoch {ep}/{epochs} Loss: {avg_loss:.4f} ({time.time() - ep_start:.1f}s)")

    refit_dur = time.time() - refit_start
    print(f"Final Refit Complete in {refit_dur:.1f}s.")

    # 5. Save model and tokenizer as safetensors
    print(f"Saving final model and tokenizer to {out_dir}...")
    final_model.save_pretrained(out_dir, safe_serialization=True)
    tokenizer.save_pretrained(out_dir)

    # Remove any stray .bin file if created
    bin_file = out_dir / "pytorch_model.bin"
    if bin_file.exists():
        bin_file.unlink()

    # Save membership evidence (sample IDs)
    evidence_path = out_dir / "train_sample_ids.json"
    save_train_sample_ids(train_dev["sample_id"].tolist(), test_ids, evidence_path)
    print(f"Saved {len(train_dev)} train sample IDs to {evidence_path}")

    # Build and save training report
    report = {
        "model_architecture": "DistilBertForSequenceClassification",
        "base_model": str(pretrained_path),
        "num_labels": num_labels,
        "classes": classes,
        "epochs": epochs,
        "batch_size": batch_size,
        "learning_rate": lr,
        "train_samples": len(train_dev),
        "cv_protocol": "10-fold cross-validation",
        "cv_n_folds": n_folds,
        "cv_macro_f1_mean": summary_cv["macro_f1_mean"],
        "cv_macro_f1_std": summary_cv["macro_f1_std"],
        "cv_accuracy_mean": summary_cv["accuracy_mean"],
        "cv_accuracy_std": summary_cv["accuracy_std"],
        "cv_weighted_f1_mean": summary_cv["weighted_f1_mean"],
        "cv_weighted_f1_std": summary_cv["weighted_f1_std"],
        "cv_duration_seconds": round(cv_total_time, 2),
        "refit_duration_seconds": round(refit_dur, 2),
        "total_training_seconds": round(cv_total_time + refit_dur, 2),
        "fold_metrics": fold_metric_rows,
        "membership_evidence": {
            "evidence_file": "train_sample_ids.json",
            "sample_count": len(train_dev),
            "sha256": compute_sha256(evidence_path),
        },
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    save_json(report, out_dir / "training_report.json")
    print(f"Training report saved to {out_dir / 'training_report.json'}")

    # Cleanup
    del final_model, final_optimizer, final_scheduler, all_train_loader, all_train_dataset
    if device.type == "cuda":
        torch.cuda.empty_cache()
    gc.collect()

    return report


def main() -> None:
    """CLI entrypoint for DistilBERT 10-fold CV retraining."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

    parser = argparse.ArgumentParser(description="Retrain DistilBERT with 10-fold CV on SupportIQ.")
    parser.add_argument(
        "--pretrained-model-dir",
        default="artifacts/models/pretrained/distilbert-base-uncased",
        help="Path to pretrained DistilBERT base",
    )
    parser.add_argument(
        "--cleaned-csv",
        default="data/datasets/processed/03-11-2026-02/cleaned.csv",
        help="Path to cleaned dataset CSV",
    )
    parser.add_argument(
        "--splits-csv",
        default="data/datasets/splits/03-11-2026-02/split_assignments.csv",
        help="Path to split assignments CSV",
    )
    parser.add_argument(
        "--output-dir",
        default="artifacts/models/trained/distilbert-supportiq",
        help="Directory to save final model",
    )
    parser.add_argument(
        "--cv-metrics-dir",
        default="artifacts/training/distilbert_cv",
        help="Directory to save fold metrics and OOF predictions",
    )
    parser.add_argument("--epochs", type=int, default=2, help="Epochs per fold and refit")
    parser.add_argument("--batch-size", type=int, default=32, help="Batch size")
    parser.add_argument("--lr", type=float, default=3e-5, help="Learning rate")
    parser.add_argument("--max-length", type=int, default=64, help="Max token sequence length")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")

    args = parser.parse_args()

    run_distilbert_10fold_cv(
        pretrained_model_dir=args.pretrained_model_dir,
        cleaned_csv=args.cleaned_csv,
        splits_csv=args.splits_csv,
        output_dir=args.output_dir,
        cv_metrics_dir=args.cv_metrics_dir,
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
        max_length=args.max_length,
        seed=args.seed,
    )


if __name__ == "__main__":
    main()
