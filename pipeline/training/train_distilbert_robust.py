"""Robustness-oriented DistilBERT training: noise augmentation + temperature calibration.

Two protocols over the development partition (the hold-out test partition and data/benchmarks/
are never read):

* ``cv`` (default): 10-fold cross-validation. Each fold trains on the other folds plus noisy
  variants of them and is scored on its clean rows and on freshly drawn noisy variants. The
  temperature is fitted on all out-of-fold logits, then a final model is refitted on every
  development row (+ augmentation).
* ``single``: one split, fold ``--val-fold`` for validation/calibration, the rest for training.
  Sized for CPU-only machines where full CV takes >10 h.

Optional extra rows written to product semantics (``--extra-train``, see
data/intent/README.md) are added, with ``--extra-variants`` noisy copies each, to every fold's training
set and to the final fit. An optional dev set (``--dev-set``) is scored with the final model; it is
never trained on.

Outlier exposure (``--oos-train``): out-of-domain texts are trained towards a uniform distribution over
the 46 labels (loss weight ``--oos-weight``), so they get low confidence without a 47th label. The dev
out-of-domain file (``--oos-dev``) measures how often such texts fall below the 0.7 confidence threshold.

Optional label smoothing discourages near-1.0 probabilities. The fitted temperature T can be
floored with ``--min-temperature`` (Bitext validation is in-distribution, where the model tends to
be underconfident, so an unconstrained fit may sharpen scores that are overconfident on real
customer text). T is folded into the classifier (W/T, b/T), so every consumer that applies softmax
to logits (apps/ml_inference, the autoeval torch and numpy backends) gets calibrated confidences
without code changes; argmax predictions are unchanged.
"""

from __future__ import annotations

import argparse
import datetime
import gc
import json
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd
import torch
import transformers
from sklearn.metrics import accuracy_score, f1_score
from torch.utils.data import DataLoader
from transformers import AutoModelForSequenceClassification, AutoTokenizer, get_linear_schedule_with_warmup

from apps.ml_inference.preprocessing import normalize_placeholders
from pipeline.preparation.intent_extra import load_dev_set, load_oos, load_train_supplement
from pipeline.preparation.utils import CORE_PRODUCT_INTENTS, STANDARD_INTENTS, compute_sha256, save_json
from pipeline.training.augment import augment_frame
from pipeline.training.train_distilbert_cv import (
    IntentDataset,
    get_default_device,
    load_and_verify_cv_data,
    save_train_sample_ids,
)

OOS_LABEL = "__oos__"  # rows trained towards the uniform distribution (label id -1)
LOW_CONFIDENCE_THRESHOLD = 0.7  # default_confidence_threshold in intent_policy.v2.json


def _format_duration(seconds: float) -> str:
    minutes, secs = divmod(int(max(seconds, 0)), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h{minutes:02d}m{secs:02d}s" if hours else f"{minutes}m{secs:02d}s"


class ProgressReporter:
    """Prints percent done and an ETA for a whole run (every fold fit plus the final refit).

    One line per ``every_percent`` of the current fit, so a run in the background stays readable in its log.
    """

    def __init__(self, total_fits: int, every_percent: int = 10, clock: Callable[[], float] = time.monotonic,
                 out: Callable[[str], None] = lambda line: print(line, flush=True)) -> None:
        self.total_fits, self.every, self.clock, self.out = total_fits, every_percent, clock, out
        self.done_fits, self.started = 0, clock()
        self.tag, self.steps, self.step, self.next_report = "", 1, 0, every_percent

    def start_fit(self, tag: str, steps: int) -> None:
        self.tag, self.steps, self.step, self.next_report = tag, max(steps, 1), 0, self.every

    def advance(self) -> None:
        self.step += 1
        fit_percent = 100.0 * self.step / self.steps
        if fit_percent + 1e-9 < self.next_report and self.step < self.steps:
            return
        while self.next_report <= fit_percent:
            self.next_report += self.every
        overall = (self.done_fits + self.step / self.steps) / self.total_fits
        elapsed = self.clock() - self.started
        eta = elapsed * (1 - overall) / overall if overall > 0 else 0.0
        filled = int(round(20 * fit_percent / 100))
        self.out(f"  {self.tag} | [{'#' * filled}{'.' * (20 - filled)}] {fit_percent:5.1f}% | run "
                 f"{100 * overall:5.1f}% ({self.done_fits + 1}/{self.total_fits} fits) | elapsed "
                 f"{_format_duration(elapsed)} | ETA {_format_duration(eta)}")

    def end_fit(self) -> None:
        self.done_fits += 1


def train_epoch_smoothed(
    model: torch.nn.Module,
    dataloader: DataLoader,
    optimizer: torch.optim.Optimizer,
    scheduler: Any,
    scaler: torch.amp.GradScaler | None,
    device: torch.device,
    label_smoothing: float,
    oos_weight: float = 0.5,
    on_batch: Callable[[], None] | None = None,
) -> float:
    """One epoch: cross-entropy (+ label smoothing) on labelled rows, outlier exposure on rows labelled -1."""
    model.train()
    loss_fn = torch.nn.CrossEntropyLoss(label_smoothing=label_smoothing)
    use_cuda = device.type == "cuda"
    total = 0.0

    def batch_loss(logits: torch.Tensor, labels: torch.Tensor) -> torch.Tensor:
        in_domain = labels >= 0
        loss = loss_fn(logits[in_domain], labels[in_domain]) if in_domain.any() else logits.sum() * 0.0
        if (~in_domain).any():
            # Cross-entropy to the uniform distribution (Hendrycks et al., 2019, "Outlier Exposure").
            loss = loss + oos_weight * -torch.log_softmax(logits[~in_domain], dim=-1).mean()
        return loss

    for batch in dataloader:
        optimizer.zero_grad()
        input_ids = batch["input_ids"].to(device, non_blocking=use_cuda)
        attention_mask = batch["attention_mask"].to(device, non_blocking=use_cuda)
        labels = batch["labels"].to(device, non_blocking=use_cuda)
        if use_cuda and scaler is not None:
            with torch.amp.autocast(device_type="cuda", dtype=torch.float16):
                logits = model(input_ids=input_ids, attention_mask=attention_mask).logits
            loss = batch_loss(logits.float(), labels)
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
        else:
            loss = batch_loss(model(input_ids=input_ids, attention_mask=attention_mask).logits, labels)
            loss.backward()
            optimizer.step()
        scheduler.step()
        total += loss.item()
        if on_batch is not None:
            on_batch()
    return total / len(dataloader)


def collect_logits(model: torch.nn.Module, dataloader: DataLoader, device: torch.device) -> tuple[np.ndarray, np.ndarray]:
    """Return (logits, labels) for a labelled loader."""
    model.eval()
    all_logits, all_labels = [], []
    with torch.inference_mode():
        for batch in dataloader:
            out = model(input_ids=batch["input_ids"].to(device), attention_mask=batch["attention_mask"].to(device))
            all_logits.append(out.logits.double().cpu().numpy())
            all_labels.append(batch["labels"].numpy())
    return np.concatenate(all_logits), np.concatenate(all_labels)


def softmax(z: np.ndarray) -> np.ndarray:
    e = np.exp(z - z.max(axis=1, keepdims=True))
    return e / e.sum(axis=1, keepdims=True)


def nll(logits: np.ndarray, labels: np.ndarray, temperature: float) -> float:
    p = softmax(logits / temperature)
    return float(-np.mean(np.log(p[np.arange(len(labels)), labels] + 1e-12)))


def expected_calibration_error(logits: np.ndarray, labels: np.ndarray, temperature: float = 1.0, n_bins: int = 15) -> float:
    p = softmax(logits / temperature)
    conf, pred = p.max(axis=1), p.argmax(axis=1)
    correct = (pred == labels).astype(float)
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        mask = (conf > lo) & (conf <= hi)
        if mask.any():
            ece += mask.mean() * abs(correct[mask].mean() - conf[mask].mean())
    return float(ece)


def fit_temperature(logits: np.ndarray, labels: np.ndarray, min_temperature: float = 0.0) -> float:
    """Grid search on log T, then a finer grid around the best value (robust, no optimiser state)."""
    coarse = np.exp(np.linspace(np.log(0.25), np.log(20.0), 120))
    best = min(coarse, key=lambda t: nll(logits, labels, t))
    fine = np.linspace(best * 0.85, best * 1.15, 61)
    return float(max(min(fine, key=lambda t: nll(logits, labels, t)), min_temperature))


def classification_metrics(logits: np.ndarray, labels: np.ndarray, n_classes: int) -> dict[str, float]:
    pred = logits.argmax(axis=1)
    rng = list(range(n_classes))
    return {
        "macro_f1": float(f1_score(labels, pred, labels=rng, average="macro", zero_division=0)),
        "accuracy": float(accuracy_score(labels, pred)),
    }


def _loader(tokenizer, df: pd.DataFrame, label2id: dict[str, int], max_length: int, batch_size: int, shuffle: bool) -> DataLoader:
    # Same preprocessing as serving (DATA-59): [ORDER_ID_1] -> [ORDER_ID].
    texts = [normalize_placeholders(t) for t in df["instruction"].tolist()]
    enc = tokenizer(texts, truncation=True, padding=True, max_length=max_length, return_tensors="pt")
    labels = [-1 if c == OOS_LABEL else label2id[c] for c in df["intent"]]
    return DataLoader(IntentDataset(enc, labels), batch_size=batch_size, shuffle=shuffle)


def dev_metrics(logits: np.ndarray, labels: np.ndarray, classes: list[str], temperature: float) -> dict[str, Any]:
    """Scores on the product-semantics dev set: 46-label metrics plus the 12-vs-34 scope decision."""
    pred = logits.argmax(axis=1)
    supported = np.array([c in CORE_PRODUCT_INTENTS for c in classes])
    gold_in, pred_in = supported[labels], supported[pred]
    out: dict[str, Any] = classification_metrics(logits, labels, len(classes))
    present = sorted(set(labels.tolist()))
    out["macro_f1_present_labels"] = float(f1_score(labels, pred, labels=present, average="macro", zero_division=0))
    out["supported_accuracy"] = float((pred[gold_in] == labels[gold_in]).mean()) if gold_in.any() else None
    out["scope_accuracy"] = float((gold_in == pred_in).mean())
    out["ece_at_t"] = expected_calibration_error(logits, labels, temperature)
    out["ece_at_1"] = expected_calibration_error(logits, labels, 1.0)
    out["dev_fitted_temperature"] = fit_temperature(logits, labels)
    conf = softmax(logits / temperature).max(axis=1)
    out["confident_errors_at_0_8"] = int(((pred != labels) & (conf >= 0.8)).sum())
    out["n"] = int(len(labels))
    return out


def oos_metrics(model: torch.nn.Module, tokenizer, oos: pd.DataFrame, in_logits: np.ndarray, max_length: int,
                device: torch.device, temperature: float) -> dict[str, Any]:
    """Low-confidence rate on out-of-domain dev texts and AUROC of (1 - confidence) vs the in-domain dev set."""
    enc = tokenizer([normalize_placeholders(t) for t in oos["instruction"].tolist()], truncation=True, padding=True, max_length=max_length, return_tensors="pt")
    loader = DataLoader(IntentDataset(enc, [0] * len(oos)), batch_size=128, shuffle=False)
    oos_logits, _ = collect_logits(model, loader, device)
    oos_conf = softmax(oos_logits / temperature).max(axis=1)
    in_conf = softmax(in_logits / temperature).max(axis=1)
    # AUROC: probability that a random OOS text has lower confidence than a random in-domain text.
    auroc = float((oos_conf[:, None] < in_conf[None, :]).mean() + 0.5 * (oos_conf[:, None] == in_conf[None, :]).mean())
    by_cat = {cat: float((oos_conf[(oos["category"] == cat).to_numpy()] < LOW_CONFIDENCE_THRESHOLD).mean())
              for cat in sorted(oos["category"].unique())}
    return {
        "n": int(len(oos)),
        "low_conf_rate": float((oos_conf < LOW_CONFIDENCE_THRESHOLD).mean()),
        "low_conf_rate_by_category": by_cat,
        "median_confidence": float(np.median(oos_conf)),
        "in_domain_low_conf_rate": float((in_conf < LOW_CONFIDENCE_THRESHOLD).mean()),
        "auroc_one_minus_conf": auroc,
    }


def _with_extra(base: pd.DataFrame, extra: pd.DataFrame | None, *, variants_per_row: int, augment_fraction: float,
                extra_variants: int, seed: int, oos: pd.DataFrame | None = None, oos_variants: int = 2) -> pd.DataFrame:
    """Bitext rows + their noise, extra product-semantics rows and out-of-domain rows, each with noisy copies."""
    parts = [base, augment_frame(base, variants_per_row=variants_per_row, fraction=augment_fraction, seed=seed)]
    for frame, n_variants, offset in ((extra, extra_variants, 7), (oos, oos_variants, 11)):
        if frame is not None and len(frame):
            parts.append(frame)
            if n_variants > 0:
                parts.append(augment_frame(frame, variants_per_row=n_variants, seed=seed + offset))
    return pd.concat(parts, ignore_index=True)


def _fit_model(
    pretrained_path: Path,
    tokenizer,
    train_df: pd.DataFrame,
    classes: list[str],
    device: torch.device,
    *,
    epochs: int,
    batch_size: int,
    lr: float,
    max_length: int,
    label_smoothing: float,
    oos_weight: float,
    seed: int,
    tag: str,
    progress: ProgressReporter | None = None,
) -> tuple[torch.nn.Module, list[float]]:
    """Fine-tune a fresh model from the pretrained base (bottom 3 layers frozen, as train_distilbert_cv)."""
    torch.manual_seed(seed)
    label2id = {c: i for i, c in enumerate(classes)}
    loader = _loader(tokenizer, train_df, label2id, max_length, batch_size, shuffle=True)
    n_oos = int((train_df["intent"] == OOS_LABEL).sum())
    if n_oos:
        print(f"  {tag} | {n_oos} out-of-domain rows trained towards uniform (weight {oos_weight})", flush=True)
    model = AutoModelForSequenceClassification.from_pretrained(
        pretrained_path, num_labels=len(classes), id2label=dict(enumerate(classes)), label2id=label2id
    ).to(device)
    for p in model.distilbert.transformer.layer[:3].parameters():
        p.requires_grad = False
    optimizer = torch.optim.AdamW(filter(lambda p: p.requires_grad, model.parameters()), lr=lr)
    total_steps = len(loader) * epochs
    scheduler = get_linear_schedule_with_warmup(optimizer, int(0.1 * total_steps), total_steps)
    scaler = torch.amp.GradScaler("cuda") if device.type == "cuda" else None
    losses = []
    if progress is not None:
        progress.start_fit(tag, total_steps)
    for ep in range(1, epochs + 1):
        ep_start = time.time()
        losses.append(train_epoch_smoothed(model, loader, optimizer, scheduler, scaler, device, label_smoothing, oos_weight,
                                           on_batch=progress.advance if progress is not None else None))
        print(f"  {tag} | Epoch {ep}/{epochs} loss {losses[-1]:.4f} ({time.time() - ep_start:.1f}s)", flush=True)
    if progress is not None:
        progress.end_fit()
    del optimizer, scheduler, loader
    return model, losses


def _release(model: torch.nn.Module, device: torch.device) -> None:
    del model
    if device.type == "cuda":
        torch.cuda.empty_cache()
    gc.collect()


def run_robust_training(
    pretrained_model_dir: str | Path,
    cleaned_csv: str | Path,
    splits_csv: str | Path,
    output_dir: str | Path,
    *,
    protocol: str = "cv",
    cv_metrics_dir: str | Path | None = None,
    n_folds: int = 10,
    val_fold: int = 0,
    variants_per_row: int = 1,
    augment_fraction: float = 1.0,
    epochs: int = 2,
    batch_size: int = 32,
    lr: float = 3e-5,
    max_length: int = 64,
    label_smoothing: float = 0.0,
    min_temperature: float = 0.0,
    extra_train: str | Path | None = None,
    extra_variants: int = 4,
    dev_set: str | Path | None = None,
    oos_train: str | Path | None = None,
    oos_dev: str | Path | None = None,
    oos_weight: float = 0.5,
    oos_variants: int = 2,
    calibration_source: str = "dev",
    seed: int = 42,
) -> dict[str, Any]:
    if protocol not in ("cv", "single"):
        raise ValueError("protocol must be 'cv' or 'single'")
    if calibration_source not in ("dev", "oof"):
        raise ValueError("calibration_source must be 'dev' or 'oof'")
    if calibration_source == "dev" and not dev_set:
        raise ValueError("calibration_source 'dev' needs a dev set")
    np.random.seed(seed)
    device = get_default_device()
    pretrained_path, out_dir = Path(pretrained_model_dir), Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    train_dev, test_ids = load_and_verify_cv_data(cleaned_csv, splits_csv, n_folds=n_folds, expected_train_count=37911)
    classes = sorted(STANDARD_INTENTS)
    label2id = {c: i for i, c in enumerate(classes)}
    tokenizer = AutoTokenizer.from_pretrained(pretrained_path)
    extra = load_train_supplement(extra_train).assign(fold=-1) if extra_train else None
    dev = load_dev_set(dev_set) if dev_set else None
    oos = load_oos(oos_train, "oos-train").assign(intent=OOS_LABEL, fold=-1) if oos_train else None
    oos_dev_frame = load_oos(oos_dev, "oos-dev") if oos_dev else None
    fit_kwargs = dict(epochs=epochs, batch_size=batch_size, lr=lr, max_length=max_length,
                      label_smoothing=label_smoothing, oos_weight=oos_weight)
    extra_kwargs = dict(variants_per_row=variants_per_row, augment_fraction=augment_fraction,
                        extra_variants=extra_variants, oos=oos, oos_variants=oos_variants)

    print("=" * 70)
    print(f"SupportIQ DistilBERT robust training | protocol={protocol} | device={device}")
    print(f"Development samples: {len(train_dev)} | hold-out test samples isolated (never loaded): {len(test_ids)}")
    print(f"Label smoothing {label_smoothing} | min temperature {min_temperature} | epochs {epochs} | lr {lr}")
    print(f"Extra training rows: {0 if extra is None else len(extra)} (+{extra_variants} noisy variants each) | "
          f"dev set: {0 if dev is None else len(dev)} | out-of-domain train {0 if oos is None else len(oos)}"
          f" (+{oos_variants} variants, weight {oos_weight}), dev {0 if oos_dev_frame is None else len(oos_dev_frame)}")
    print("=" * 70)

    eval_folds = list(range(n_folds)) if protocol == "cv" else [val_fold]
    # Every fold fit plus the final refit; reports percent done and ETA for the whole run.
    fit_kwargs["progress"] = ProgressReporter(total_fits=len(eval_folds) + 1)
    fold_rows: list[dict[str, Any]] = []
    oof_rows: list[dict[str, Any]] = []
    cal_logits_parts, cal_label_parts = [], []
    cv_start = time.time()

    for fold in eval_folds:
        fold_start = time.time()
        base = train_dev[train_dev["fold"] != fold].reset_index(drop=True)
        val_clean = train_dev[train_dev["fold"] == fold].reset_index(drop=True)
        train_df = _with_extra(base, extra, seed=seed + fold, **extra_kwargs)
        # Different seed: validation noise must not be the same draws the model trained on.
        val_noisy = augment_frame(val_clean, variants_per_row=1, seed=seed + 1000 + fold)
        print(f"\n>>> Fold {fold}: train {len(train_df)} (incl. augmentation) | val {len(val_clean)} clean + {len(val_noisy)} noisy", flush=True)

        model, losses = _fit_model(pretrained_path, tokenizer, train_df, classes, device, seed=seed + fold, tag=f"Fold {fold}", **fit_kwargs)
        clean_logits, clean_labels = collect_logits(model, _loader(tokenizer, val_clean, label2id, max_length, 128, False), device)
        noisy_logits, noisy_labels = collect_logits(model, _loader(tokenizer, val_noisy, label2id, max_length, 128, False), device)
        _release(model, device)

        clean_m = classification_metrics(clean_logits, clean_labels, len(classes))
        noisy_m = classification_metrics(noisy_logits, noisy_labels, len(classes))
        fold_rows.append({
            "fold": fold, "n_train": len(train_df), "n_val": len(val_clean),
            "macro_f1": clean_m["macro_f1"], "accuracy": clean_m["accuracy"],
            "noisy_macro_f1": noisy_m["macro_f1"], "noisy_accuracy": noisy_m["accuracy"],
            "final_loss": losses[-1], "duration_seconds": round(time.time() - fold_start, 2),
        })
        print(f"  Fold {fold} macro-F1 clean {clean_m['macro_f1']:.4f} | noisy {noisy_m['macro_f1']:.4f}", flush=True)
        for kind, frame, logits in (("clean", val_clean, clean_logits), ("noisy", val_noisy, noisy_logits)):
            probs = softmax(logits)
            for sid, y_true, p in zip(frame["sample_id"], frame["intent"], probs):
                oof_rows.append({"sample_id": sid, "fold": fold, "kind": kind, "y_true": y_true,
                                 "y_pred": classes[int(p.argmax())], "confidence_uncalibrated": float(p.max())})
        cal_logits_parts += [clean_logits, noisy_logits]
        cal_label_parts += [clean_labels, noisy_labels]

    cv_seconds = time.time() - cv_start
    cal_logits, cal_labels = np.concatenate(cal_logits_parts), np.concatenate(cal_label_parts)
    oof_fitted_temperature = fit_temperature(cal_logits, cal_labels)
    # With calibration_source "dev" this is replaced after the refit by the dev-set fit (DATA-34).
    fitted_temperature = oof_fitted_temperature
    temperature = max(fitted_temperature, min_temperature)
    fold_df = pd.DataFrame(fold_rows)
    validation = {
        "folds_evaluated": eval_folds,
        "macro_f1_mean": float(fold_df["macro_f1"].mean()),
        "macro_f1_std": float(fold_df["macro_f1"].std(ddof=1)) if len(fold_df) > 1 else 0.0,
        "noisy_macro_f1_mean": float(fold_df["noisy_macro_f1"].mean()),
        "noisy_macro_f1_std": float(fold_df["noisy_macro_f1"].std(ddof=1)) if len(fold_df) > 1 else 0.0,
        "accuracy_mean": float(fold_df["accuracy"].mean()),
        "ece_before": expected_calibration_error(cal_logits, cal_labels, 1.0),
        "ece_after": expected_calibration_error(cal_logits, cal_labels, temperature),
        "nll_before": nll(cal_logits, cal_labels, 1.0),
        "nll_after": nll(cal_logits, cal_labels, temperature),
    }
    print("\n" + "=" * 60)
    print(f"Validation macro-F1 clean {validation['macro_f1_mean']:.4f} ± {validation['macro_f1_std']:.4f} | "
          f"noisy {validation['noisy_macro_f1_mean']:.4f} ± {validation['noisy_macro_f1_std']:.4f}")
    print(f"Temperature T={temperature:.3f} (fitted {fitted_temperature:.3f}) | ECE {validation['ece_before']:.4f} -> {validation['ece_after']:.4f}")
    print("=" * 60)

    if cv_metrics_dir is not None:
        cv_dir = Path(cv_metrics_dir)
        cv_dir.mkdir(parents=True, exist_ok=True)
        fold_df.to_csv(cv_dir / "fold_metrics.csv", index=False)
        pd.DataFrame(oof_rows).to_csv(cv_dir / "oof_predictions.csv", index=False)

    # Final model: CV refits on every development row; single keeps the validation fold out.
    final_base = train_dev if protocol == "cv" else train_dev[train_dev["fold"] != val_fold].reset_index(drop=True)
    final_train = _with_extra(final_base, extra, seed=seed, **extra_kwargs)
    refit_start = time.time()
    print(f"\n>>> Final fit: {len(final_base)} Bitext rows, {len(final_train)} rows incl. augmentation and extra data", flush=True)
    model, final_losses = _fit_model(pretrained_path, tokenizer, final_train, classes, device, seed=seed, tag="Final", **fit_kwargs)
    refit_seconds = time.time() - refit_start

    dev_report = None
    if dev is not None:
        dev_logits, dev_labels = collect_logits(model, _loader(tokenizer, dev, label2id, max_length, 128, False), device)
        if calibration_source == "dev":
            # Validation data written to product semantics, never test data (DATA-25, DATA-34).
            fitted_temperature = fit_temperature(dev_logits, dev_labels)
            temperature = max(fitted_temperature, min_temperature)
            print(f"Temperature from dev set: T={temperature:.3f} (fitted {fitted_temperature:.3f})", flush=True)
        dev_report = dev_metrics(dev_logits, dev_labels, classes, temperature)
        print(f"Dev set ({dev_report['n']}): macro-F1 {dev_report['macro_f1_present_labels']:.4f} | supported acc "
              f"{dev_report['supported_accuracy']:.4f} | scope acc {dev_report['scope_accuracy']:.4f} | "
              f"ECE@T {dev_report['ece_at_t']:.4f} | T fitted on dev would be {dev_report['dev_fitted_temperature']:.3f}",
              flush=True)
        if oos_dev_frame is not None:
            dev_report["out_of_domain"] = oos_metrics(model, tokenizer, oos_dev_frame, dev_logits, max_length, device, temperature)
            o = dev_report["out_of_domain"]
            print(f"Dev out-of-domain ({o['n']}): low-confidence rate {o['low_conf_rate']:.3f} | median conf "
                  f"{o['median_confidence']:.3f} | AUROC {o['auroc_one_minus_conf']:.3f} | in-domain low-conf "
                  f"{o['in_domain_low_conf_rate']:.3f}", flush=True)

    # Fold T into the classifier so softmax(logits) is already calibrated for every consumer.
    with torch.no_grad():
        model.classifier.weight.div_(temperature)
        model.classifier.bias.div_(temperature)
    model.save_pretrained(out_dir, safe_serialization=True)
    tokenizer.save_pretrained(out_dir)
    stray = out_dir / "pytorch_model.bin"
    if stray.exists():
        stray.unlink()
    _release(model, device)

    evidence_path = out_dir / "train_sample_ids.json"
    member_ids = final_base["sample_id"].tolist() + ([] if extra is None else extra["sample_id"].tolist())
    save_train_sample_ids(member_ids, test_ids, evidence_path)

    report = {
        "model_architecture": "DistilBertForSequenceClassification",
        "base_model": str(pretrained_path),
        "num_labels": len(classes),
        "classes": classes,
        "protocol": (f"{n_folds}-fold cross-validation (+ noise augmentation), refit on all development rows"
                     if protocol == "cv" else
                     f"single split: folds != {val_fold} train (+ noise augmentation), fold {val_fold} validation/calibration"),
        "epochs": epochs,
        "batch_size": batch_size,
        "learning_rate": lr,
        "max_length": max_length,
        "label_smoothing": label_smoothing,
        "seed": seed,
        "train_samples": len(final_base),
        "augmented_samples": len(final_train) - len(final_base) - (0 if extra is None else len(extra)) - (0 if oos is None else len(oos)),
        "outlier_exposure": None if oos is None else {
            "file": str(oos_train), "rows": len(oos), "noisy_variants_per_row": oos_variants, "weight": oos_weight,
            "sha256": compute_sha256(oos_train),
        },
        "extra_train": None if extra is None else {
            "file": str(extra_train), "rows": len(extra), "noisy_variants_per_row": extra_variants,
            "sha256": compute_sha256(extra_train),
        },
        "dev_set": None if dev is None else {"file": str(dev_set), "sha256": compute_sha256(dev_set), **dev_report},
        "augmentation": {"module": "pipeline/training/augment.py", "variants_per_row": variants_per_row, "fraction": augment_fraction},
        "calibration": {
            "method": ("temperature scaling on the product dev set (validation), folded into classifier"
                       if calibration_source == "dev" else
                       "temperature scaling on out-of-fold logits (clean + noisy), folded into classifier"),
            "source": calibration_source,
            "temperature": temperature,
            "fitted_temperature": fitted_temperature,
            "oof_fitted_temperature": oof_fitted_temperature,
            "min_temperature": min_temperature,
        },
        "validation": validation,
        "fold_metrics": fold_rows,
        "final_epoch_losses": final_losses,
        "cv_duration_seconds": round(cv_seconds, 2),
        "refit_duration_seconds": round(refit_seconds, 2),
        "membership_evidence": {
            "evidence_file": "train_sample_ids.json",
            "sample_count": len(member_ids),
            "sha256": compute_sha256(evidence_path),
        },
        "source_files": {"cleaned_sha256": compute_sha256(cleaned_csv), "splits_sha256": compute_sha256(splits_csv)},
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    save_json(report, out_dir / "training_report.json")
    print(f"Saved model, tokenizer and report to {out_dir}")
    return report


RUN_KEYS = {
    "pretrained_model_dir", "cleaned_csv", "splits_csv", "output_dir", "protocol", "run_dir", "val_fold",
    "variants_per_row", "augment_fraction", "epochs", "batch_size", "lr", "max_length", "label_smoothing",
    "min_temperature", "extra_train", "extra_variants", "dev_set", "oos_train", "oos_dev", "oos_weight",
    "oos_variants", "calibration_source", "seed",
}


def _git_commit() -> str | None:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5, check=False)
        return out.stdout.strip() or None
    except OSError:
        return None


def write_run_record(config_path: Path, config: dict[str, Any], report: dict[str, Any]) -> Path:
    """Run folder per DATA-30: configuration, commit, data hashes, seed, environment, metrics, artifact."""
    run_dir = Path(config["run_dir"])
    run_dir.mkdir(parents=True, exist_ok=True)
    data_files = [config[k] for k in ("cleaned_csv", "splits_csv", "extra_train", "dev_set", "oos_train", "oos_dev") if config.get(k)]
    record = {
        "config_file": config_path.as_posix(),
        "config": config,
        "code_commit": _git_commit(),
        "seed": config.get("seed", 42),
        "data_sha256": {f: compute_sha256(f) for f in data_files},
        "environment": {
            "python": platform.python_version(), "torch": torch.__version__, "transformers": transformers.__version__,
            "device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu",
            "nondeterminism": "GPU kernels are not bit-reproducible; compare metrics, not weights (DATA-31)",
        },
        "artifact": {"dir": config["output_dir"], "weights_sha256": compute_sha256(Path(config["output_dir"]) / "model.safetensors")},
        "metrics": {k: report[k] for k in ("validation", "calibration") if k in report} | {"dev_set": report.get("dev_set")},
    }
    save_json(record, run_dir / "run.json")
    return run_dir


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(description="Train DistilBERT from a committed run configuration (DATA-29).")
    parser.add_argument("--config", required=True, help="e.g. pipeline/configs/training_robust.json")
    config_path = Path(parser.parse_args().config)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    unknown = set(config) - RUN_KEYS - {"description"}
    if unknown:
        raise SystemExit(f"Unknown configuration keys: {sorted(unknown)}")
    args = {k: v for k, v in config.items() if k in RUN_KEYS}
    run_dir = args.pop("run_dir")
    pretrained, cleaned, splits, output = (args.pop(k) for k in ("pretrained_model_dir", "cleaned_csv", "splits_csv", "output_dir"))
    report = run_robust_training(pretrained, cleaned, splits, output, cv_metrics_dir=run_dir, **args)
    print(f"Run record: {write_run_record(config_path, config, report) / 'run.json'}")


if __name__ == "__main__":
    main()
