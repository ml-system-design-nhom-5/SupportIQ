"""Fine-tune pre-trained DistilBERT on SupportIQ customer-support intent classification."""

from __future__ import annotations

import argparse
import datetime
import json
import sys
import time
from pathlib import Path

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

from pipeline.preparation.utils import STANDARD_INTENTS, compute_sha256, save_json

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


def train_distilbert(
    pretrained_model_dir: str | Path,
    cleaned_csv: str | Path,
    splits_csv: str | Path,
    output_dir: str | Path,
    samples_per_class: int = 250,
    val_per_class: int = 50,
    epochs: int = 2,
    batch_size: int = 32,
    lr: float = 3e-5,
    max_length: int = 64,
    seed: int = 42,
) -> dict[str, Any]:
    """Fine-tune pre-trained DistilBERT base model on stratified development partition."""
    torch.manual_seed(seed)
    np.random.seed(seed)

    pretrained_path = Path(pretrained_model_dir)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print(f"SupportIQ DistilBERT Intent Classifier Training")
    print(f"Pretrained base: {pretrained_path}")
    print(f"Target directory: {out_dir}")
    print("=" * 60)

    # 1. Label mapping
    classes = sorted(STANDARD_INTENTS)
    num_labels = len(classes)
    label2id = {c: i for i, c in enumerate(classes)}
    id2label = {i: c for i, c in enumerate(classes)}

    # 2. Load dataset
    print(f"Loading development training split...")
    df_clean = pd.read_csv(cleaned_csv)
    df_splits = pd.read_csv(splits_csv)

    merged = df_clean.merge(df_splits, on="sample_id")
    train_dev = merged[merged["partition"] == "train"].copy()

    # Stratified sampling strictly from development train
    rng = np.random.RandomState(seed)
    train_indices = []
    val_indices = []

    for intent, group in train_dev.groupby("intent"):
        shuffled = group.sample(frac=1.0, random_state=rng)
        n_train = min(samples_per_class, len(shuffled))
        n_val = min(val_per_class, len(shuffled) - n_train)

        train_indices.extend(shuffled.iloc[:n_train].index)
        val_indices.extend(shuffled.iloc[n_train : n_train + n_val].index)

    df_train_sub = train_dev.loc[train_indices].reset_index(drop=True)
    df_val_sub = train_dev.loc[val_indices].reset_index(drop=True)

    print(f"Training samples: {len(df_train_sub)} ({samples_per_class}/class)")
    print(f"Validation samples: {len(df_val_sub)} ({val_per_class}/class)")

    # 3. Tokenize
    print(f"Tokenizing text inputs (max_length={max_length})...")
    tokenizer = AutoTokenizer.from_pretrained(pretrained_path)

    train_encodings = tokenizer(
        df_train_sub["instruction"].tolist(),
        truncation=True,
        padding=True,
        max_length=max_length,
        return_tensors="pt",
    )
    val_encodings = tokenizer(
        df_val_sub["instruction"].tolist(),
        truncation=True,
        padding=True,
        max_length=max_length,
        return_tensors="pt",
    )

    train_labels = [label2id[c] for c in df_train_sub["intent"]]
    val_labels = [label2id[c] for c in df_val_sub["intent"]]

    train_dataset = IntentDataset(train_encodings, train_labels)
    val_dataset = IntentDataset(val_encodings, val_labels)

    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False)

    # 4. Initialize model with 46-class classification head
    print(f"Initializing Sequence Classification head for {num_labels} classes...")
    model = AutoModelForSequenceClassification.from_pretrained(
        pretrained_path,
        num_labels=num_labels,
        id2label=id2label,
        label2id=label2id,
    )

    # Freeze lower layers to retain language representations and accelerate CPU training
    print("Freezing bottom 3 transformer layers...")
    for p in model.distilbert.transformer.layer[:3].parameters():
        p.requires_grad = False

    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total_params = sum(p.numel() for p in model.parameters())
    print(f"Trainable parameters: {trainable_params:,} / {total_params:,} ({trainable_params/total_params:.1%})")

    # 5. Optimizer & Scheduler
    optimizer = torch.optim.AdamW(filter(lambda p: p.requires_grad, model.parameters()), lr=lr)
    total_steps = len(train_loader) * epochs
    warmup_steps = int(0.1 * total_steps)
    scheduler = get_linear_schedule_with_warmup(
        optimizer,
        num_warmup_steps=warmup_steps,
        num_training_steps=total_steps,
    )

    # 6. Training loop
    print("\nStarting training loop...")
    start_time = time.time()
    epoch_histories = []

    model.train()
    for epoch in range(1, epochs + 1):
        epoch_start = time.time()
        running_loss = 0.0
        step_count = 0

        for step, batch in enumerate(train_loader, 1):
            optimizer.zero_grad()
            outputs = model(
                input_ids=batch["input_ids"],
                attention_mask=batch["attention_mask"],
                labels=batch["labels"],
            )
            loss = outputs.loss
            loss.backward()
            optimizer.step()
            scheduler.step()

            running_loss += loss.item()
            step_count += 1

            if step % 50 == 0 or step == len(train_loader):
                avg_loss = running_loss / step_count
                elapsed = time.time() - epoch_start
                print(
                    f"Epoch [{epoch}/{epochs}] Step [{step}/{len(train_loader)}] "
                    f"Loss: {loss.item():.4f} (Avg: {avg_loss:.4f}) "
                    f"Elapsed: {elapsed:.1f}s"
                )

        # Validation at epoch end
        model.eval()
        val_preds = []
        val_targets = []
        val_loss = 0.0

        with torch.no_grad():
            for batch in val_loader:
                outputs = model(
                    input_ids=batch["input_ids"],
                    attention_mask=batch["attention_mask"],
                    labels=batch["labels"],
                )
                val_loss += outputs.loss.item()
                preds = outputs.logits.argmax(dim=-1).cpu().numpy()
                val_preds.extend(preds)
                val_targets.extend(batch["labels"].cpu().numpy())

        avg_val_loss = val_loss / len(val_loader)
        val_acc = accuracy_score(val_targets, val_preds)
        val_f1 = f1_score(val_targets, val_preds, average="macro", zero_division=0)

        epoch_time = time.time() - epoch_start
        print(
            f"--> Epoch {epoch} Complete! Val Loss: {avg_val_loss:.4f} | "
            f"Val Accuracy: {val_acc:.4f} | Val Macro-F1: {val_f1:.4f} | "
            f"Duration: {epoch_time:.1f}s\n"
        )

        epoch_histories.append({
            "epoch": epoch,
            "train_loss": running_loss / step_count,
            "val_loss": avg_val_loss,
            "val_accuracy": float(val_acc),
            "val_macro_f1": float(val_f1),
            "epoch_duration_seconds": round(epoch_time, 2),
        })
        model.train()

    total_duration = time.time() - start_time
    print(f"Total training time: {total_duration:.2f} seconds ({total_duration/60:.2f} minutes).")

    # 7. Save model and tokenizer
    print(f"Saving fine-tuned model and tokenizer to {out_dir}...")
    model.save_pretrained(out_dir)
    tokenizer.save_pretrained(out_dir)

    report = {
        "model_architecture": "DistilBertForSequenceClassification",
        "base_model": str(pretrained_path),
        "num_labels": num_labels,
        "classes": classes,
        "epochs": epochs,
        "batch_size": batch_size,
        "learning_rate": lr,
        "train_samples": len(df_train_sub),
        "val_samples": len(df_val_sub),
        "total_training_seconds": round(total_duration, 2),
        "final_val_accuracy": epoch_histories[-1]["val_accuracy"],
        "final_val_macro_f1": epoch_histories[-1]["val_macro_f1"],
        "epoch_history": epoch_histories,
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    save_json(report, out_dir / "training_report.json")
    print(f"Training report saved to {out_dir / 'training_report.json'}")

    return report


def main() -> None:
    """CLI entrypoint for training DistilBERT."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

    parser = argparse.ArgumentParser(description="Fine-tune pretrained DistilBERT on SupportIQ.")
    parser.add_argument(
        "--pretrained-model-dir",
        default="artifacts/models/pretrained/distilbert-base-uncased",
        help="Path to pretrained base DistilBERT",
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
        help="Directory to save fine-tuned model",
    )
    parser.add_argument("--samples-per-class", type=int, default=250, help="Train samples per class")
    parser.add_argument("--val-per-class", type=int, default=50, help="Val samples per class")
    parser.add_argument("--epochs", type=int, default=2, help="Number of training epochs")
    parser.add_argument("--batch-size", type=int, default=32, help="Batch size")
    parser.add_argument("--lr", type=float, default=3e-5, help="Learning rate")

    args = parser.parse_args()

    train_distilbert(
        pretrained_model_dir=args.pretrained_model_dir,
        cleaned_csv=args.cleaned_csv,
        splits_csv=args.splits_csv,
        output_dir=args.output_dir,
        samples_per_class=args.samples_per_class,
        val_per_class=args.val_per_class,
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
    )


if __name__ == "__main__":
    main()
