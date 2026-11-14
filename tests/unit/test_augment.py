"""Tests for pipeline.training.augment and the calibration helpers of train_distilbert_robust."""
import random

import numpy as np
import pandas as pd
import pytest

from pipeline.training import augment as A


def _frame(n: int = 20) -> pd.DataFrame:
    return pd.DataFrame({
        "sample_id": [f"sample_{i:06d}" for i in range(n)],
        "instruction": ["I would like to know the status of my refund please"] * n,
        "intent": ["refund_status"] * n,
        "fold": list(range(n)),
    })


def test_variant_changes_text_and_is_deterministic_per_seed():
    a = A.make_variant("Where is my order? I need it before Friday.", random.Random(1))
    b = A.make_variant("Where is my order? I need it before Friday.", random.Random(1))
    assert a == b
    assert a != "Where is my order? I need it before Friday."


def test_augment_frame_preserves_labels_and_traces_sample_ids():
    df = _frame()
    out = A.augment_frame(df, variants_per_row=2, seed=7)
    assert len(out) == 40
    assert (out["intent"] == "refund_status").all()
    assert set(out["sample_id"].str.split("::").str[0]) == set(df["sample_id"])
    assert set(out["sample_id"].str.split("::").str[1]) == {"aug0", "aug1"}


def test_augment_fraction_limits_rows_and_rejects_bad_values():
    assert len(A.augment_frame(_frame(), fraction=0.5)) == 10
    with pytest.raises(ValueError):
        A.augment_frame(_frame(), fraction=0.0)


def test_typo_word_keeps_short_words():
    assert A.typo_word("is", random.Random(0)) == "is"


def test_temperature_fit_reduces_ece_on_overconfident_logits():
    pytest.importorskip("torch")  # module imports torch/transformers
    from pipeline.training.train_distilbert_robust import expected_calibration_error, fit_temperature, nll

    rng = np.random.default_rng(0)
    labels = rng.integers(0, 5, 4000)
    logits = rng.normal(size=(4000, 5))
    logits[np.arange(4000), labels] += 2.0
    logits *= 4.0  # overconfident
    t = fit_temperature(logits, labels)
    assert t > 1.0
    assert nll(logits, labels, t) < nll(logits, labels, 1.0)
    assert expected_calibration_error(logits, labels, t) < expected_calibration_error(logits, labels, 1.0)


def test_temperature_floor_prevents_sharpening_underconfident_logits():
    pytest.importorskip("torch")
    from pipeline.training.train_distilbert_robust import fit_temperature

    rng = np.random.default_rng(1)
    labels = rng.integers(0, 5, 4000)
    logits = rng.normal(size=(4000, 5))
    logits[np.arange(4000), labels] += 6.0
    logits *= 0.5  # underconfident: an unconstrained fit sharpens (T < 1)
    assert fit_temperature(logits, labels) < 1.0
    assert fit_temperature(logits, labels, min_temperature=1.0) == 1.0


def test_outlier_exposure_loss_pushes_oos_rows_towards_uniform():
    torch = pytest.importorskip("torch")
    from torch.utils.data import DataLoader

    from pipeline.training.train_distilbert_robust import train_epoch_smoothed

    class Toy(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.w = torch.nn.Parameter(torch.tensor([[4.0, 0.0, 0.0]]))

        def forward(self, input_ids, attention_mask):
            return type("Out", (), {"logits": self.w.expand(len(input_ids), -1)})()

    model = Toy()
    batch = [{"input_ids": torch.zeros(2, dtype=torch.long), "attention_mask": torch.ones(2), "labels": torch.tensor(-1)}] * 4
    opt = torch.optim.SGD(model.parameters(), lr=0.5)
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda _: 1.0)
    for _ in range(30):
        train_epoch_smoothed(model, DataLoader(batch, batch_size=4), opt, sched, None, torch.device("cpu"), 0.0, oos_weight=1.0)
    probs = torch.softmax(model.w, dim=-1)[0]
    assert float(probs.max()) < 0.4  # was ~0.96 before training


def test_progress_reporter_prints_percent_overall_progress_and_eta():
    pytest.importorskip("torch")
    from pipeline.training.train_distilbert_robust import ProgressReporter

    now = iter(range(0, 1000))
    lines = []
    reporter = ProgressReporter(total_fits=2, every_percent=50, clock=lambda: next(now), out=lines.append)
    reporter.start_fit("Fold 0", steps=4)
    for _ in range(4):
        reporter.advance()
    reporter.end_fit()
    assert len(lines) == 2  # at 50% and 100% of the fit, not on every batch
    assert "50.0%" in lines[0] and "run  25.0% (1/2 fits)" in lines[0]
    assert "100.0%" in lines[1] and "run  50.0%" in lines[1] and "ETA" in lines[1]
    reporter.start_fit("Final", steps=2)
    reporter.advance(); reporter.advance()
    assert "run 100.0% (2/2 fits)" in lines[-1] and "ETA 0m00s" in lines[-1]


def test_unknown_protocol_is_rejected():
    pytest.importorskip("torch")
    from pipeline.training.train_distilbert_robust import run_robust_training

    with pytest.raises(ValueError, match="protocol"):
        run_robust_training("unused", "unused.csv", "unused.csv", "unused", protocol="bogus")
