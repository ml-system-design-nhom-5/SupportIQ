"""Unit tests for taxonomy-clean contrast splits, draft eligibility, rejector calibration, and fail-closed preflight."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
import torch

import pipeline.evaluation.classifier_acceptance_gate as gate_mod
import pipeline.training.train_boundary_candidate as tbc
import scripts.run_boundary_contrast_fit as contrast_mod
from apps.core_backend.intent.routing import STANDARD_INTENTS_46, load_policy_v2
from pipeline.training.boundary_contrast_data import (
    AUTHORED_COMPOUND_FAMILIES,
    AUTHORED_NONRETAIL_OOD_FAMILIES,
    prepare_and_lock_contrast_splits,
    validate_contrast_semantic_consistency,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_contrast_splits_group_isolation_semantic_and_balanced_targets(tmp_path: Path) -> None:
    """Real prepare_and_lock_contrast_splits enforces isolation, semantic consistency, and 8-12 contrast balance."""
    class _StubTok:
        def encode(self, text, truncation=False, add_special_tokens=True):
            return [1] * len(text.split())

        def __call__(self, texts, truncation=False, max_length=64):
            return {"input_ids": [[1] * min(len(t.split()), max_length) for t in texts]}

    art_root = tmp_path / "art"
    with patch("pipeline.training.train_boundary_candidate.AutoTokenizer.from_pretrained", return_value=_StubTok()):
        lock = prepare_and_lock_contrast_splits(
            worktree_root=REPO_ROOT,
            data_repo_root=REPO_ROOT,
            init_model_dir=contrast_mod.FIT2_BASELINE_DIR,
            artifact_root=art_root,
        )

    ext = lock["contrast_extension"]
    assert ext["isolation_passed"] is True
    assert ext["semantic_consistency_passed"] is True
    assert ext["neg_intents_in_standard_46_count"] == 0
    assert ext["pos_non_46_count"] == 0
    assert len(ext["removed_contradictory_base_ids"]) >= 3  # cls_trk_live_gps + driver/rider base contradictions removed
    for sup_intent in ("track_order", "return_policy", "return_product"):
        cnt = ext["authored_contrast_train_by_intent"][sup_intent]
        assert 8 <= cnt <= 12, f"Expected balanced 8-12 contrast rows for {sup_intent}, got {cnt}"

    exp = lock["effective_exposure_counts"]
    pos_exp = exp["positive_46_ce_mask"]
    neg_exp = exp["negative_uniform_kl_mask"]
    assert pos_exp["domain_pos_total_raw"] == lock["counts"]["domain_pos_train"]
    assert neg_exp["baseline_neg_raw"] == 99
    assert neg_exp["new_compound_neg_raw"] == 16
    assert neg_exp["new_nonretail_ood_raw"] == 12
    assert neg_exp["total_neg_effective"] == (99 + 16 + 12) * 12
    assert exp["total_effective_train_rows"] == pos_exp["total_positive_ce_effective"] + neg_exp["total_neg_effective"]

    ds = art_root / "datasets"
    s46 = set(STANDARD_INTENTS_46)
    trn = tbc._read_jsonl(ds / "full_train_split.jsonl")
    cal = tbc._read_jsonl(ds / "full_cal_split.jsonl")
    evl = tbc._read_jsonl(ds / "boundary_pos_evaluation.jsonl") + tbc._read_jsonl(ds / "boundary_neg_evaluation.jsonl")

    assert not ({r["group_id"] for r in trn} & {r["group_id"] for r in cal})
    assert not ({r["group_id"] for r in trn} & {r["group_id"] for r in evl})
    assert not ({r["group_id"] for r in cal} & {r["group_id"] for r in evl})

    trn_p = {r["parent_sample_id"] for r in trn if r.get("parent_sample_id")}
    cal_p = {r["parent_sample_id"] for r in cal if r.get("parent_sample_id")}
    evl_p = {r["parent_sample_id"] for r in evl if r.get("parent_sample_id")}
    assert not (trn_p & cal_p)
    assert not (trn_p & evl_p)
    assert not (cal_p & evl_p)

    for split_suffix in ("train", "calibration", "evaluation"):
        pos_rows = tbc._read_jsonl(ds / f"boundary_pos_{split_suffix}.jsonl")
        neg_rows = tbc._read_jsonl(ds / f"boundary_neg_{split_suffix}.jsonl")
        assert {r["intent"] for r in pos_rows} <= s46
        assert ({r["intent"] for r in neg_rows} & s46) == set()
        assert {"out_of_scope", "multi_intent", "other_domain"} <= {r["intent"] for r in neg_rows}
        validate_contrast_semantic_consistency(pos_rows, neg_rows, split_suffix, check_train_balance=(split_suffix == "train"))


def test_contrast_semantic_validator_rejects_contradictions() -> None:
    """Semantic validator fails closed on track_order GPS/truck overlap, return_policy in-store, or imbalance."""
    with pytest.raises(ValueError, match="Semantic contradiction in test track_order"):
        validate_contrast_semantic_consistency(
            [{"sample_id": "bad_1", "intent": "track_order", "text": "Where is my delivery truck on GPS?"}],
            [],
            "test",
        )
    with pytest.raises(ValueError, match="Semantic contradiction in test return_policy"):
        validate_contrast_semantic_consistency(
            [{"sample_id": "bad_2", "intent": "return_policy", "text": "Can I return at a brick-and-mortar branch?"}],
            [],
            "test",
        )
    with pytest.raises(ValueError, match="Unbalanced authored supported contrast exposure"):
        validate_contrast_semantic_consistency(
            [{"sample_id": "only_one", "intent": "track_order", "text": "Check my order status", "source": "authored_contrast_pos_train"}],
            [],
            "train",
            check_train_balance=True,
        )


def test_draft_eligibility_separates_selective_label_from_sup11() -> None:
    """selective_label=1 denotes 46-class membership, NOT draft eligibility; only SUPPORTED_11 is draft-eligible."""
    rows = [
        {"sample_id": "sup11", "intent": "track_order", "selective_label": 1, "is_negative": 0},
        {"sample_id": "human", "intent": "human_agent", "selective_label": 1, "is_negative": 0},
        {"sample_id": "esc34_td", "intent": "track_delivery", "selective_label": 1, "is_negative": 0},
        {"sample_id": "esc34_oh", "intent": "order_history", "selective_label": 1, "is_negative": 0},
        {"sample_id": "esc34_rp", "intent": "return_product_in_store", "selective_label": 1, "is_negative": 0},
        {"sample_id": "neg_ood", "intent": "other_domain", "selective_label": 0, "is_negative": 1},
    ]
    assert tbc.compute_rejector_eligibility_labels(rows) == [1, 0, 0, 0, 0, 0]


def test_rejector_fit_polarity_and_cal_only_selection(tmp_path: Path) -> None:
    """CPU logistic rejector fits on TRAIN only, tunes (C, tau) on CAL only, and passes gate schema + polarity."""
    rng = np.random.default_rng(7)
    policy_v2 = load_policy_v2(str(REPO_ROOT / "apps/core_backend/config/policies/intent_policy.v2.json"))
    idx_sup = STANDARD_INTENTS_46.index("return_policy")
    idx_esc = STANDARD_INTENTS_46.index("track_delivery")
    idx_hum = STANDARD_INTENTS_46.index("human_agent")

    def _make_split(n_sup: int, n_esc: int, n_neg: int):
        cls_sup = np.zeros((n_sup, 768), dtype=np.float64)
        cls_sup[:, 0] = 3.0
        cls_sup += rng.normal(0.0, 0.15, size=cls_sup.shape)
        lg_sup = np.full((n_sup, 46), -2.0, dtype=np.float64)
        lg_sup[:, idx_sup] = 5.0

        cls_esc = np.zeros((n_esc, 768), dtype=np.float64)
        cls_esc[:, 1] = 3.0
        cls_esc += rng.normal(0.0, 0.15, size=cls_esc.shape)
        lg_esc = np.full((n_esc, 46), -2.0, dtype=np.float64)
        lg_esc[: n_esc // 2, idx_esc] = 4.5
        lg_esc[n_esc // 2 :, idx_hum] = 4.5

        cls_neg = np.zeros((n_neg, 768), dtype=np.float64)
        cls_neg[:, 2] = 3.0
        cls_neg += rng.normal(0.0, 0.15, size=cls_neg.shape)
        lg_neg = np.full((n_neg, 46), -0.5, dtype=np.float64)
        # Deliberately include high supported-11 logit spike on negative to test rejector rescue
        lg_neg[:, idx_sup] = 4.0

        return cls_sup, lg_sup, cls_esc, lg_esc, cls_neg, lg_neg

    t_cs, t_ls, t_ce, t_le, t_cn, t_ln = _make_split(30, 20, 20)
    trn_logits = np.vstack([t_ls, t_le, t_ln])
    trn_cls = np.vstack([t_cs, t_ce, t_cn])
    trn_y = ([1] * 30) + ([0] * 40)

    c_cs, c_ls, c_ce, c_le, c_cn, c_ln = _make_split(12, 8, 8)
    cal_dom_logits = np.vstack([c_ls, c_le])
    cal_dom_cls = np.vstack([c_cs, c_ce])
    cal_dom_intents = (["return_policy"] * 12) + (["track_delivery"] * 4) + (["human_agent"] * 4)

    rej, stats = tbc.fit_selective_rejector_from_arrays(
        model_version="fit2-test-v4",
        trn_logits=trn_logits,
        trn_cls=trn_cls,
        trn_y=trn_y,
        cal_dom_logits=cal_dom_logits,
        cal_dom_cls=cal_dom_cls,
        cal_dom_intents=cal_dom_intents,
        bitext_cal_logits=c_ls[:4],
        bitext_cal_cls=c_cs[:4],
        bitext_cal_intents=["return_policy"] * 4,
        cal_neg_logits=c_ln,
        cal_neg_cls=c_cn,
        temperature=1.0,
        policy_v2=policy_v2,
        c_grid=(0.15, 0.35, 0.75, 1.5),
    )

    assert rej.enabled is True
    assert rej.feature_spec == "cls_l2_plus_logit_geometry_v1"
    assert rej.feature_dim == 776
    assert stats["zero_cal_unsafe"] is True
    assert stats["cal_neg_false_draft"] == 0
    assert stats["cal_dom_correct_draft"] == 12

    rej_dict = rej.to_dict()
    rej_dict["reject_when"] = "below"
    assert gate_mod._validate_rejector_schema(rej_dict) == []

    # Verify runtime parity polarity via classifier_acceptance_gate._evaluate_experimental_rejector
    sup_probs = torch.softmax(torch.tensor(c_ls[0]), dim=-1).tolist()
    sup_rejected, sup_score = gate_mod._evaluate_experimental_rejector(
        rej_dict, c_ls[0], sup_probs, sup_probs, cls_embedding=c_cs[0]
    )
    neg_probs = torch.softmax(torch.tensor(c_ln[0]), dim=-1).tolist()
    neg_rejected, neg_score = gate_mod._evaluate_experimental_rejector(
        rej_dict, c_ln[0], neg_probs, neg_probs, cls_embedding=c_cn[0]
    )
    assert sup_rejected is False
    assert neg_rejected is True
    assert sup_score > rej.threshold > neg_score


def test_preflight_fails_closed_on_wrong_checkpoint_or_tampered_sha(tmp_path: Path) -> None:
    """Wrong starting checkpoint SHA/T/rejector or tampered Serving SHA fails closed before any fit."""
    fake_init = tmp_path / "bad_init"
    fake_init.mkdir()
    (fake_init / "model.safetensors").write_bytes(b"not-fit2")
    with pytest.raises(ValueError, match="Starting Fit2 weights SHA mismatch"):
        contrast_mod.verify_fit2_starting_checkpoint(fake_init)

    with (
        patch.object(contrast_mod, "EXPECTED_SERVING_SHA256", "0" * 64),
        patch.object(contrast_mod, "run_fit_and_lock_candidate") as mock_fit,
        patch.object(sys, "argv", ["prog", "--dry-run"]),
    ):
        with pytest.raises(ValueError, match="Serving weights SHA mismatch"):
            contrast_mod.main()
        mock_fit.assert_not_called()


def test_contrast_runner_dryrun_zero_fit_and_archive_orchestration(tmp_path: Path) -> None:
    """Zero-GPU orchestration test: dryrun performs 0 fits; run-contrast-fit verifies archival hashes BEFORE fit."""
    main_cand = tmp_path / "main_cand"
    main_cand.mkdir(parents=True)
    local_root = tmp_path / "local"
    ds_dir = local_root / "dryrun" / "datasets"
    ds_dir.mkdir(parents=True)
    pos_bytes = b'{"text":"hi","intent":"track_order"}\n'
    pos_sha = hashlib.sha256(pos_bytes).hexdigest()
    split_bytes = b'{"schema_version":"boundary_curriculum_split.v1"}\n'
    split_sha = hashlib.sha256(split_bytes).hexdigest()
    (ds_dir / "boundary_pos_train.jsonl").write_bytes(pos_bytes)
    (ds_dir / "split_manifest.json").write_bytes(split_bytes)
    (ds_dir / "dataset_lock_manifest.json").write_text(json.dumps({"counts": {}}), encoding="utf-8")

    records_dir = main_cand / "run-records-fit2-boundary-contrast-v4"
    fit_calls = []

    def _fake_fit(**kwargs):
        fit_calls.append(kwargs)
        assert (records_dir / "inputs" / "inputs_sha256_inventory.json").exists()
        assert (records_dir / "environment.json").exists()
        rc = json.loads((records_dir / "run_config.json").read_text(encoding="utf-8"))
        assert rc["enable_selective_rejector"] is True
        assert rc["rejector_c_grid"] == [0.15, 0.35, 0.75, 1.5]
        st = json.loads((records_dir / "status.json").read_text(encoding="utf-8"))
        assert st["status"] == "training"

        cand = kwargs["artifact_root"] / kwargs["output_subdir"]
        cand.mkdir(parents=True, exist_ok=True)
        (cand / "model.safetensors").write_bytes(b"stub_weights")
        (cand / "tokenizer.json").write_bytes(b"{}")
        (cand / "config.json").write_text(
            json.dumps({"id2label": {str(i): lbl for i, lbl in enumerate(STANDARD_INTENTS_46)}}),
            encoding="utf-8",
        )
        (cand / "candidate_provenance_manifest.json").write_bytes(b"{}")
        art_hashes = {
            fname: hashlib.sha256((cand / fname).read_bytes()).hexdigest()
            for fname in ("model.safetensors", "tokenizer.json", "config.json")
        }
        (cand / "calibration_manifest.json").write_text(
            json.dumps(
                {
                    "schema_version": "selective_calibration.v1",
                    "artifact_hashes": art_hashes,
                    "label_space": {"num_labels": 46, "valid_46_label_bijection": True, "id2label": {str(i): lbl for i, lbl in enumerate(STANDARD_INTENTS_46)}},
                    "calibration": {"temperature": 1.0, "min_temperature": 1.0, "calibrated": True},
                    "selective_rejector": {"enabled": False, "type": "logistic_regression_v1", "feature_spec": "logit_geometry_v1", "feature_dim": 8, "scaler_mean": [0.0]*8, "scaler_scale": [1.0]*8, "weights": [0.0]*8, "bias": 0.0, "threshold": 0.0},
                }
            ),
            encoding="utf-8",
        )
        return {"fit_mode": kwargs["fit_mode"]}

    preflight_stub = {
        "dry_run": True,
        "canonical_prep": {"cleaned_sha256": "8bc10cfa", "splits_sha256": "1d366e89"},
        "dataset_hashes": {"boundary_pos_train": pos_sha, "boundary_split_manifest": split_sha},
        "effective_exposure_counts": {},
    }
    with (
        patch.object(contrast_mod, "MAIN_CANDIDATES_DIR", main_cand),
        patch.object(contrast_mod, "LOCAL_CONTRAST_ROOT", local_root),
        patch.object(contrast_mod, "run_preflight_validation", return_value=preflight_stub),
        patch.object(contrast_mod, "run_fit_and_lock_candidate", side_effect=_fake_fit),
        patch.object(contrast_mod, "verify_reload_from_archive", autospec=True, return_value={"reload_verified": True, "num_labels": 46}) as mock_reload,
        patch.object(sys, "argv", ["prog", "--run-contrast-fit", "--run-id", "fit2-boundary-contrast-v4", "--enable-selective-rejector"]),
    ):
        contrast_mod.main()

    assert len(fit_calls) == 1
    assert fit_calls[0]["enable_selective_rejector"] is True
    assert fit_calls[0]["candidate_name"] == "fit2-boundary-contrast-v4"
    assert fit_calls[0]["epochs"] == 2
    assert fit_calls[0]["lr"] == 1e-5
    mock_reload.assert_called_once_with(main_cand / "fit2-boundary-contrast-v4")
    assert (main_cand / "fit2-boundary-contrast-v4" / "archive_sha_inventory.json").exists()
    assert (records_dir / "sidecar_sha_inventory.json").exists()


def test_trainer_consumes_locked_weighted_schedule_and_preserves_default(tmp_path: Path) -> None:
    """run_fit_and_lock_candidate respects neg_repeat while preserving default 12 and default rejector=False."""
    art = tmp_path / "art"
    ds = art / "datasets"
    ds.mkdir(parents=True)
    (ds / "dataset_lock_manifest.json").write_text('{"counts":{}}', encoding="utf-8")
    (ds / "boundary_pos_train.jsonl").write_text('{"text":"where is package","intent":"track_order"}\n', encoding="utf-8")
    (ds / "bitext_train_clean.jsonl").write_text('{"text":"track parcel","intent":"track_order"}\n', encoding="utf-8")
    (ds / "bitext_train_noisy.jsonl").write_text("", encoding="utf-8")
    (ds / "boundary_pos_calibration.jsonl").write_text('{"text":"cal pos","intent":"track_order"}\n', encoding="utf-8")
    (ds / "boundary_neg_calibration.jsonl").write_text('{"text":"cal neg","intent":"multi_intent"}\n', encoding="utf-8")
    (ds / "bitext_cal.jsonl").write_text('{"text":"cal bitext","intent":"track_order"}\n', encoding="utf-8")
    (ds / "boundary_neg_train.jsonl").write_text(
        '{"text":"base neg","intent":"multi_intent"}\n'
        '{"text":"low weight neg","intent":"other_domain","neg_repeat":4}\n',
        encoding="utf-8",
    )

    class _Tok:
        def __call__(self, texts, max_length=64, padding="max_length", truncation=True, return_tensors="pt"):
            n = len(texts)
            return {"input_ids": torch.ones((n, 4), dtype=torch.long), "attention_mask": torch.ones((n, 4), dtype=torch.long)}

    class _StopTraining(Exception):
        pass

    captured_len = []

    def _capture_loader(dataset, **kwargs):
        captured_len.append(len(dataset))
        raise _StopTraining("captured")

    with (
        patch.object(tbc.AutoTokenizer, "from_pretrained", return_value=_Tok()),
        patch.object(tbc.AutoModelForSequenceClassification, "from_pretrained", return_value=torch.nn.Linear(4, 46)),
        patch.object(tbc, "DataLoader", side_effect=_capture_loader),
    ):
        with pytest.raises(_StopTraining):
            tbc.run_fit_and_lock_candidate(
                worktree_root=REPO_ROOT,
                data_repo_root=REPO_ROOT,
                init_model_dir=tmp_path,
                artifact_root=art,
                fit_mode="fit2_supcon_energy",
                epochs=2,
            )

    # 1 pos_train * 4 + 1 bitext_clean + 12 (default) + 4 (override) = 21
    assert captured_len == [21]
    assert tbc.resolve_neg_repeat({"sample_id": "ok"}, 12) == 12
    with pytest.raises(ValueError, match="Invalid neg_repeat"):
        tbc.resolve_neg_repeat({"sample_id": "bad", "neg_repeat": True}, 12)
    assert AUTHORED_COMPOUND_FAMILIES and AUTHORED_NONRETAIL_OOD_FAMILIES
