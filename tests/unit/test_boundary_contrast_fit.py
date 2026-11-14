"""Unit tests for taxonomy-clean contrast splits, draft eligibility, rejector calibration, and fail-closed preflight."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pandas as pd
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

    bitext_test_rows = tbc._read_jsonl(ds / "bitext_test_6690.jsonl")
    test_norms = {gate_mod.normalize_text(r["text"]) for r in bitext_test_rows}
    noisy_rows = tbc._read_jsonl(ds / "bitext_train_noisy.jsonl")
    clean_rows = tbc._read_jsonl(ds / "bitext_train_clean.jsonl")
    assert not ({gate_mod.normalize_text(r["text"]) for r in noisy_rows} & test_norms)
    assert not ({gate_mod.normalize_text(r["text"]) for r in trn} & test_norms)

    # All 46 labels preserved in replay while Bitext return_policy physical-store parents + noisy typo children are quarantined
    assert {r["intent"] for r in (clean_rows + noisy_rows)} == s46
    assert ext["quarantined_total"] == 25
    assert len(ext["quarantined_bitext_ids"]) == 20
    assert "bitext_trn_aug_sample_029457_32" in set(ext["quarantined_bitext_ids"])
    td_audit = exp["track_delivery_exposure"]
    assert td_audit["total_train_raw"] == 270
    assert td_audit["total_train_effective"] == 390
    assert td_audit["ambiguous_retained_train_raw"] == 263

    # Finding 3 reconciliation: per-split split_summaries preserve pre-filter counts and sum to total (25, incl. 8 noisy aug children)
    sem = lock["semantic_audit"]
    by_split = {s["split"]: s for s in sem["split_summaries"]}
    assert by_split["bitext_train_clean"]["input_rows"] == 7360
    assert by_split["bitext_train_clean"]["kept_rows"] == len(clean_rows) == 7348
    assert by_split["bitext_train_clean"]["quarantined_rows"] == 12
    assert by_split["bitext_train_noisy"]["input_rows"] == 3677
    assert by_split["bitext_train_noisy"]["kept_rows"] == len(noisy_rows) == 3669
    assert by_split["bitext_train_noisy"]["quarantined_rows"] == 8
    assert by_split["bitext_cal"]["kept_rows"] == 690
    assert by_split["bitext_cal"]["quarantined_rows"] == 0
    assert by_split["contrast_pos_train"]["kept_rows"] == lock["counts"]["domain_pos_train"] == 300
    assert by_split["contrast_pos_train"]["quarantined_rows"] == 3
    assert by_split["contrast_pos_calibration"]["kept_rows"] == lock["counts"]["domain_pos_cal"] == 135
    assert by_split["contrast_pos_calibration"]["quarantined_rows"] == 2
    assert by_split["contrast_pos_evaluation"]["quarantined_rows"] == 0
    active_q_sum = sum(s["quarantined_rows"] for k, s in by_split.items() if not k.endswith("_readonly"))
    assert active_q_sum == sem["quarantined_total"] == sem["active_quarantined_sum"] == 25


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
    assert stats["cal_bitext_correct_draft"] == 4
    assert stats["cal_human_agent_unsafe_draft"] == 0
    assert stats["feasible_candidates"] > 0

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

    records_dir = main_cand / "run-records-fit2-boundary-contrast-v4p1"
    fit_calls = []

    src_rel = "scripts/run_boundary_contrast_fit.py"
    src_sha = hashlib.sha256((REPO_ROOT / src_rel).read_bytes()).hexdigest()
    prov_stub = {"git_commit": "b" * 40, "source_hashes": {src_rel: src_sha}}

    def _fake_fit(**kwargs):
        fit_calls.append(kwargs)
        assert (records_dir / "inputs" / "inputs_sha256_inventory.json").exists()
        assert (records_dir / "source_snapshot" / "scripts" / "run_boundary_contrast_fit.py").exists()
        assert (records_dir / "environment.json").exists()
        rc = json.loads((records_dir / "run_config.json").read_text(encoding="utf-8"))
        assert rc["enable_selective_rejector"] is True
        assert rc["rejector_c_grid"] == [0.15, 0.35, 0.75, 1.5]
        assert rc["source_hashes"][src_rel] == src_sha
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
        art_hashes = {
            fname: hashlib.sha256((cand / fname).read_bytes()).hexdigest()
            for fname in ("model.safetensors", "tokenizer.json", "config.json")
        }
        (cand / "candidate_provenance_manifest.json").write_text(
            json.dumps(
                {
                    "schema_version": "candidate_provenance.v1",
                    "provenance_status": "verified",
                    "git_commit": "b" * 40,
                    "base_model": {"init_weights_sha256": contrast_mod.EXPECTED_FIT2_SHA256},
                    "training_lineage": {"fit_id": "fit2_supcon_energy"},
                    "dataset_hashes": {"boundary_pos_train": pos_sha},
                    "artifact_hashes": art_hashes,
                }
            ),
            encoding="utf-8",
        )
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
        patch.object(contrast_mod, "verify_relevant_source_provenance", return_value=prov_stub),
        patch.object(contrast_mod, "run_preflight_validation", return_value=preflight_stub),
        patch.object(contrast_mod, "run_fit_and_lock_candidate", side_effect=_fake_fit),
        patch.object(contrast_mod, "verify_reload_from_archive", autospec=True, return_value={"reload_verified": True, "num_labels": 46}) as mock_reload,
        patch.object(sys, "argv", ["prog", "--run-contrast-fit", "--run-id", "fit2-boundary-contrast-v4p1", "--enable-selective-rejector"]),
    ):
        contrast_mod.main()

    assert len(fit_calls) == 1
    assert fit_calls[0]["enable_selective_rejector"] is True
    assert fit_calls[0]["candidate_name"] == "fit2-boundary-contrast-v4p1"
    assert fit_calls[0]["epochs"] == 2
    assert fit_calls[0]["lr"] == 1e-5
    mock_reload.assert_called_once_with(main_cand / "fit2-boundary-contrast-v4p1")
    assert (main_cand / "fit2-boundary-contrast-v4p1" / "archive_sha_inventory.json").exists()
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


def test_rejector_selector_rejects_all_abstain_unsafe_and_human_agent_leaks() -> None:
    """Selector fails closed on all-abstain-only, unsafe-only (incl. human_agent), and 0-Bitext-coverage grids."""
    policy_v2 = load_policy_v2(str(REPO_ROOT / "apps/core_backend/config/policies/intent_policy.v2.json"))
    idx_sup = STANDARD_INTENTS_46.index("return_policy")
    lg_sup = np.full((2, 46), -2.0, dtype=np.float64)
    lg_sup[:, idx_sup] = 5.0
    zeros_cls = np.zeros((2, 768), dtype=np.float64)

    class _StubLogReg:
        def __init__(self, **kwargs):
            self.coef_ = np.zeros((1, 776), dtype=np.float64)
            self.intercept_ = np.array([0.0], dtype=np.float64)

        def fit(self, X, y):
            return self

    def _run_selector(p_dom, p_bit, p_neg, cal_dom_intents=("return_policy", "human_agent"), bit_intents=("return_policy",)):
        def _fake_score(feats, params):
            n = feats.shape[0]
            if n == 2 and p_dom is not None:
                return np.asarray(p_dom, dtype=np.float64)
            return np.asarray(p_bit if n == len(bit_intents) else p_neg, dtype=np.float64)

        scores = [np.asarray(p_dom, dtype=np.float64), np.asarray(p_bit, dtype=np.float64), np.asarray(p_neg, dtype=np.float64)]
        call_idx = {"i": 0}

        def _seq_score(feats, params):
            out = scores[call_idx["i"] % 3]
            call_idx["i"] += 1
            return out

        with (
            patch.object(tbc, "LogisticRegression", _StubLogReg),
            patch.object(tbc, "score_rejector", side_effect=_seq_score),
        ):
            return tbc.fit_selective_rejector_from_arrays(
                model_version="v4p1-stub",
                trn_logits=lg_sup,
                trn_cls=zeros_cls,
                trn_y=[1, 0],
                cal_dom_logits=lg_sup[: len(cal_dom_intents)],
                cal_dom_cls=zeros_cls[: len(cal_dom_intents)],
                cal_dom_intents=list(cal_dom_intents),
                bitext_cal_logits=lg_sup[: len(bit_intents)],
                bitext_cal_cls=zeros_cls[: len(bit_intents)],
                bitext_cal_intents=list(bit_intents),
                cal_neg_logits=lg_sup[:1],
                cal_neg_cls=zeros_cls[:1],
                temperature=1.0,
                policy_v2=policy_v2,
                c_grid=(0.15, 0.35),
            )

    # 1. All-abstain-only grid: scores < 0.25 -> 0 drafts, 0 unsafe -> must fail closed
    with pytest.raises(ValueError, match="No feasible CAL rejector point found.*max_dom_corr_when_safe=0/1"):
        _run_selector([0.10, 0.10], [0.10], [0.10])

    # 2. Unsafe-only grid via misclassified human_agent row routed to retrieve_draft -> must fail closed (never prefer coverage over safety)
    with pytest.raises(ValueError, match="min_unsafe_when_nonzero_cov=1"):
        _run_selector([0.85, 0.95], [0.85], [0.10])

    # 3. Domain feasible but 0 Bitext SUPPORTED_11 coverage -> must fail closed
    with pytest.raises(ValueError, match="max_bitext_corr_when_safe=0/1"):
        _run_selector([0.85, 0.10], [0.10], [0.10])

    # 4. Feasible selection succeeds only on safe tau separating human_agent/neg from dom + bitext SUPPORTED_11
    rej, stats = _run_selector([0.70, 0.40], [0.70], [0.40])
    assert stats["zero_cal_unsafe"] is True
    assert stats["cal_human_agent_unsafe_draft"] == 0
    assert stats["cal_dom_correct_draft"] == 1
    assert stats["cal_bitext_correct_draft"] == 1
    assert 0.41 <= rej.threshold <= 0.70


def test_prepare_splits_excludes_noisy_overlap_with_test(tmp_path: Path) -> None:
    """prepare_and_lock_splits excludes normalized overlaps between bitext_train_noisy and held-out Bitext test."""
    init_dir = tmp_path / "init"
    init_dir.mkdir()
    (init_dir / "model.safetensors").write_bytes(b"weights")
    art = tmp_path / "art"

    colliding_text = "wheres my order check status"
    train_rows = []
    for i, lbl in enumerate(STANDARD_INTENTS_46):
        if lbl == "track_order":
            train_rows.append({"sample_id": "trn_cal_to", "instruction": "where is my order cal item", "intent": lbl})
            train_rows.append({"sample_id": "trn_a_to", "instruction": "where is my order alpha", "intent": lbl})
            train_rows.append({"sample_id": "trn_b_to", "instruction": "where is my order beta", "intent": lbl})
        else:
            txt = f"{lbl.replace('_', ' ')} unique base {i}"
            train_rows.append({"sample_id": f"trn_cal_{i}", "instruction": txt + " cal only", "intent": lbl})
            train_rows.append({"sample_id": f"trn_a_{i}", "instruction": txt, "intent": lbl})
            train_rows.append({"sample_id": f"trn_b_{i}", "instruction": f"{lbl.replace('_', ' ')} second train item {i}", "intent": lbl})
    test_df = pd.DataFrame([{"sample_id": "tst_0", "instruction": colliding_text, "intent": "track_order"}])
    fake_lineage = SimpleNamespace(cleaned_sha256="c" * 64, splits_sha256="d" * 64, train_df=pd.DataFrame(train_rows), test_df=test_df)

    def _fixed_audit(datasets_dir: Path, repo_root: Path):
        datasets_dir.mkdir(parents=True, exist_ok=True)
        (datasets_dir / "split_manifest.json").write_text("{}\n", encoding="utf-8")
        for fn, row in (
            ("boundary_pos_train.jsonl", {"sample_id": "p1", "instruction": "dom pos trn", "text": "dom pos trn", "intent": "track_order", "group_id": "g_pt"}),
            ("boundary_neg_train.jsonl", {"sample_id": "n1", "instruction": "dom neg trn", "text": "dom neg trn", "intent": "out_of_scope", "group_id": "g_nt"}),
            ("boundary_pos_calibration.jsonl", {"sample_id": "p2", "instruction": "dom pos cal", "text": "dom pos cal", "intent": "track_order", "group_id": "g_pc"}),
            ("boundary_neg_calibration.jsonl", {"sample_id": "n2", "instruction": "dom neg cal", "text": "dom neg cal", "intent": "out_of_scope", "group_id": "g_nc"}),
            ("boundary_pos_evaluation.jsonl", {"sample_id": "p3", "instruction": "dom pos evl", "text": "dom pos evl", "intent": "track_order", "group_id": "g_pe"}),
            ("boundary_neg_evaluation.jsonl", {"sample_id": "n3", "instruction": "dom neg evl", "text": "dom neg evl", "intent": "out_of_scope", "group_id": "g_ne"}),
        ):
            (datasets_dir / fn).write_text(json.dumps(row) + "\n", encoding="utf-8")
        return {"token_truncation_audit": {}, "overlap_audit": {}}

    class _StubTok:
        def encode(self, text, truncation=False, add_special_tokens=True):
            return [1]

    with (
        patch.object(tbc, "audit_and_export_boundary_datasets", side_effect=_fixed_audit),
        patch.object(tbc, "verify_original_46_label_lineage", return_value=fake_lineage),
        patch.object(tbc, "_load_frozen_benchmark_texts", return_value=[]),
        patch.object(tbc, "apply_realistic_noise", side_effect=lambda txt, _rng: colliding_text if "where is my order" in txt else f"noisy {txt}"),
        patch.object(tbc.AutoTokenizer, "from_pretrained", return_value=_StubTok()),
    ):
        tbc.prepare_and_lock_splits(
            worktree_root=REPO_ROOT,
            data_repo_root=REPO_ROOT,
            init_model_dir=init_dir,
            artifact_root=art,
            replay_per_class=1,
            noise_aug_per_class=1,
            bitext_cal_per_class=1,
        )

    noisy_rows = tbc._read_jsonl(art / "datasets" / "bitext_train_noisy.jsonl")
    clean_rows = tbc._read_jsonl(art / "datasets" / "bitext_train_clean.jsonl")
    assert any(r["intent"] == "track_order" for r in clean_rows)
    assert len(noisy_rows) == 45
    assert all(tbc._normalize_text(r["text"]) != tbc._normalize_text(colliding_text) for r in noisy_rows)


def test_runner_source_provenance_ignores_unrelated_dirty_and_fails_on_relevant_dirty(tmp_path: Path) -> None:
    """Relevant source guard ignores unrelated PPTX/.gitkeep/audit dirt and fails closed on relevant tracked edits."""
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)

    for rel in contrast_mod.RELEVANT_SOURCE_PATHS:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f"# {rel}\n", encoding="utf-8")
    keep = tmp_path / "artifacts" / "models" / ".gitkeep"
    keep.parent.mkdir(parents=True, exist_ok=True)
    keep.write_text("", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    # Unrelated user files: deleted .gitkeep + untracked PPTX + untracked audit doc -> MUST pass
    keep.unlink()
    (tmp_path / "docs").mkdir(exist_ok=True)
    (tmp_path / "docs" / "report.pptx").write_bytes(b"pptx")
    (tmp_path / "docs" / "audit-b.md").write_text("audit", encoding="utf-8")
    prov = contrast_mod.verify_relevant_source_provenance(tmp_path)
    assert len(prov["git_commit"]) == 40
    assert set(prov["source_hashes"]) == set(contrast_mod.RELEVANT_SOURCE_PATHS)

    # Modify a relevant tracked file -> MUST fail closed
    rel_file = tmp_path / "pipeline/training/boundary_contrast_data.py"
    rel_file.write_text("# modified\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="Uncommitted changes in relevant source files"):
        contrast_mod.verify_relevant_source_provenance(tmp_path)


def test_gate_sequence_classifier_disabled_rejector_parity(tmp_path: Path) -> None:
    """GateSequenceClassifier with disabled rejector matches runtime metadata (selective_accepted=None) and preserves routing."""
    (tmp_path / "config.json").write_text(
        json.dumps({"id2label": {str(i): lbl for i, lbl in enumerate(STANDARD_INTENTS_46)}}),
        encoding="utf-8",
    )
    seen_hidden_flags = []
    logits = torch.full((1, 46), -3.0, dtype=torch.float32)
    logits[0, STANDARD_INTENTS_46.index("return_policy")] = 6.0

    class _StubModel:
        def eval(self):
            return self

        def to(self, _dev):
            return self

        def __call__(self, **kwargs):
            seen_hidden_flags.append(bool(kwargs.get("output_hidden_states", False)))
            return SimpleNamespace(logits=logits)

    class _StubTok:
        def __call__(self, text, **kwargs):
            return {"input_ids": torch.ones((1, 8), dtype=torch.long), "attention_mask": torch.ones((1, 8), dtype=torch.long)}

    disabled_rejector = {
        "enabled": False,
        "type": "logistic_regression_v1",
        "feature_spec": "cls_l2_plus_logit_geometry_v1",
        "feature_dim": 776,
    }
    with (
        patch.object(gate_mod.AutoTokenizer, "from_pretrained", return_value=_StubTok()),
        patch.object(gate_mod.AutoModelForSequenceClassification, "from_pretrained", return_value=_StubModel()),
    ):
        clf = gate_mod.GateSequenceClassifier(
            "disabled-rej-parity",
            tmp_path,
            temperature=1.0,
            calibrated=True,
            rejector=disabled_rejector,
        )
    out = clf.predict("What is your return policy?")
    assert seen_hidden_flags == [False]
    assert out["selective_accepted"] is None
    assert out["rejector_decision"] is None
    assert out["rejected_by_experimental_adapter"] is False
    assert out["rejection_score"] is None
    assert out["intent"] == "return_policy"


def test_runner_post_fit_provenance_failure_marks_incomplete(tmp_path: Path) -> None:
    """Invalid archived candidate provenance fails closed and marks status=incomplete while preserving dirs."""
    main_cand = tmp_path / "main_cand"
    main_cand.mkdir(parents=True)
    local_root = tmp_path / "local"
    ds_dir = local_root / "dryrun" / "datasets"
    ds_dir.mkdir(parents=True)
    (ds_dir / "boundary_pos_train.jsonl").write_bytes(b"{}\n")
    (ds_dir / "dataset_lock_manifest.json").write_text("{}", encoding="utf-8")

    def _bad_prov_fit(**kwargs):
        cand = kwargs["artifact_root"] / kwargs["output_subdir"]
        cand.mkdir(parents=True, exist_ok=True)
        (cand / "model.safetensors").write_bytes(b"w")
        (cand / "tokenizer.json").write_bytes(b"{}")
        (cand / "config.json").write_text(
            json.dumps({"id2label": {str(i): lbl for i, lbl in enumerate(STANDARD_INTENTS_46)}}),
            encoding="utf-8",
        )
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
        (cand / "candidate_provenance_manifest.json").write_text(json.dumps({"provenance_status": "unknown"}), encoding="utf-8")
        return {}

    prov_stub = {"git_commit": "b" * 40, "source_hashes": {"scripts/run_boundary_contrast_fit.py": "a" * 64}}
    with (
        patch.object(contrast_mod, "MAIN_CANDIDATES_DIR", main_cand),
        patch.object(contrast_mod, "LOCAL_CONTRAST_ROOT", local_root),
        patch.object(contrast_mod, "_snapshot_relevant_sources"),
        patch.object(contrast_mod, "verify_relevant_source_provenance", return_value=prov_stub),
        patch.object(contrast_mod, "run_preflight_validation", return_value={"dry_run": True, "canonical_prep": {}, "dataset_hashes": {}, "effective_exposure_counts": {}}),
        patch.object(contrast_mod, "run_fit_and_lock_candidate", side_effect=_bad_prov_fit),
        patch.object(sys, "argv", ["prog", "--run-contrast-fit", "--run-id", "fit2-bad-prov"]),
    ):
        with pytest.raises(ValueError, match="Archived candidate_provenance_manifest invalid"):
            contrast_mod.main()

    st = json.loads((main_cand / "run-records-fit2-bad-prov" / "status.json").read_text(encoding="utf-8"))
    assert st["status"] == "incomplete"
    assert (main_cand / "fit2-bad-prov").exists()


def test_active_kb_semantic_classifier_phrasing_and_fail_closed_guards() -> None:
    """Shared KB classifier catches Bitext store/shop typos, keeps merchant-policy/locker text, and preserves non-GPS track_delivery."""
    # 1. Bitext store/shop phrasings missed by old narrow regex MUST be quarantined
    for sid, txt in (
        ("b1", "can I ask for the exchange of an item in store?"),
        ("b2", "can I make returns at the shop?"),
        ("b3", "what is the process to return a product a the store?"),
        ("b4", "tell me if I can return a product at te store"),
    ):
        rec = tbc.classify_row_kb_semantics({"sample_id": sid, "parent_sample_id": sid, "intent": "return_policy", "text": txt, "source": "bitext_train_partition_clean"})
        assert rec["status"] == "quarantined_kb_contradiction", (sid, rec)

    # 2. Genuine merchant-policy, online store, and locker phrasing MUST remain valid
    for sid, intent, txt in (
        ("v1", "return_policy", "Can I review your standard store rules and store return policy?"),
        ("v2", "refund_policy", "Do you refund as store credit for online purchases?"),
        ("v3", "return_product", "Drop off your return at any convenience-store locker nearby."),
        ("v4", "return_policy", "I bought it from your online store and want to return it online."),
    ):
        rec = tbc.classify_row_kb_semantics({"sample_id": sid, "parent_sample_id": sid, "intent": intent, "text": txt, "source": "authored"})
        assert rec["status"] == "valid", (sid, rec)

    # 3. Generic track_delivery lacking GPS keywords MUST be ambiguous_retained (never blanket-dropped); track_order+GPS quarantined
    td_rec = tbc.classify_row_kb_semantics({"sample_id": "td1", "parent_sample_id": "td1", "intent": "track_delivery", "text": "help me track my shipment please", "source": "bitext_train_partition_clean"})
    assert td_rec["status"] == "ambiguous_retained"
    to_rec = tbc.classify_row_kb_semantics({"sample_id": "to1", "parent_sample_id": "to1", "intent": "track_order", "text": "track delivery truck on live gps", "source": "domain"})
    assert to_rec["status"] == "quarantined_kb_contradiction"

    # 4. Fail-closed provenance & unknown semantic status checks
    with pytest.raises(ValueError, match="Missing parent_sample_id provenance"):
        tbc.classify_row_kb_semantics({"sample_id": "b_missing", "intent": "return_policy", "text": "return online", "source": "bitext_train_partition_clean"})
    with pytest.raises(ValueError, match="Unknown semantic audit status"):
        tbc.validate_semantic_status("invented_status")


def test_prepare_splits_quarantines_parent_and_typo_noisy_child(tmp_path: Path) -> None:
    """If clean parent return_policy row is quarantined, its typo noisy child ('at the stoe') is also quarantined."""
    init_dir = tmp_path / "init"
    init_dir.mkdir()
    (init_dir / "model.safetensors").write_bytes(b"weights")
    art = tmp_path / "art"

    train_rows = []
    for i, lbl in enumerate(STANDARD_INTENTS_46):
        if lbl == "return_policy":
            train_rows.append({"sample_id": "rp_cal_0", "instruction": "can i return something bought online", "intent": lbl})
            train_rows.append({"sample_id": "rp_bad_parent", "instruction": "can i return a product at the store", "intent": lbl})
            train_rows.append({"sample_id": "rp_good_parent", "instruction": "what is your standard online return policy window", "intent": lbl})
        else:
            txt = f"{lbl.replace('_', ' ')} unique base {i}"
            train_rows.append({"sample_id": f"cal_{i}", "instruction": txt + " cal", "intent": lbl})
            train_rows.append({"sample_id": f"trn_{i}", "instruction": txt, "intent": lbl})
    test_df = pd.DataFrame([{"sample_id": "tst_0", "instruction": "unrelated test order item", "intent": "track_order"}])
    fake_lineage = SimpleNamespace(cleaned_sha256="c" * 64, splits_sha256="d" * 64, train_df=pd.DataFrame(train_rows), test_df=test_df)

    def _fixed_audit(datasets_dir: Path, repo_root: Path):
        datasets_dir.mkdir(parents=True, exist_ok=True)
        (datasets_dir / "split_manifest.json").write_text("{}\n", encoding="utf-8")
        for fn, row in (
            ("boundary_pos_train.jsonl", {"sample_id": "p1", "instruction": "dom pos trn", "text": "dom pos trn", "intent": "track_order", "group_id": "g_pt"}),
            ("boundary_neg_train.jsonl", {"sample_id": "n1", "instruction": "dom neg trn", "text": "dom neg trn", "intent": "out_of_scope", "group_id": "g_nt"}),
            ("boundary_pos_calibration.jsonl", {"sample_id": "p2", "instruction": "dom pos cal", "text": "dom pos cal", "intent": "track_order", "group_id": "g_pc"}),
            ("boundary_neg_calibration.jsonl", {"sample_id": "n2", "instruction": "dom neg cal", "text": "dom neg cal", "intent": "out_of_scope", "group_id": "g_nc"}),
            ("boundary_pos_evaluation.jsonl", {"sample_id": "p3", "instruction": "dom pos evl", "text": "dom pos evl", "intent": "track_order", "group_id": "g_pe"}),
            ("boundary_neg_evaluation.jsonl", {"sample_id": "n3", "instruction": "dom neg evl", "text": "dom neg evl", "intent": "out_of_scope", "group_id": "g_ne"}),
        ):
            (datasets_dir / fn).write_text(json.dumps(row) + "\n", encoding="utf-8")
        return {"token_truncation_audit": {}, "overlap_audit": {}}

    class _StubTok:
        def encode(self, text, truncation=False, add_special_tokens=True):
            return [1]

    def _typo_noise(txt: str, _rng) -> str:
        return "can i return a fucking product at the stoe" if "at the store" in txt else f"noisy {txt}"

    with (
        patch.object(tbc, "audit_and_export_boundary_datasets", side_effect=_fixed_audit),
        patch.object(tbc, "verify_original_46_label_lineage", return_value=fake_lineage),
        patch.object(tbc, "_load_frozen_benchmark_texts", return_value=[]),
        patch.object(tbc, "apply_realistic_noise", side_effect=_typo_noise),
        patch.object(tbc.AutoTokenizer, "from_pretrained", return_value=_StubTok()),
        patch.object(pd.DataFrame, "sample", lambda self, **kw: self),
    ):
        # Default apply_active_kb_audit=False leaves faithful d7ddaf2 preparation untouched
        faithful_lock = tbc.prepare_and_lock_splits(
            worktree_root=REPO_ROOT,
            data_repo_root=REPO_ROOT,
            init_model_dir=init_dir,
            artifact_root=tmp_path / "art_faithful",
            replay_per_class=2,
            noise_aug_per_class=2,
            bitext_cal_per_class=1,
        )
        assert "quarantine_records" not in faithful_lock["dataset_hashes"]
        assert "bitext_trn_rp_bad_parent" in {
            r["sample_id"] for r in tbc._read_jsonl(tmp_path / "art_faithful" / "datasets" / "bitext_train_clean.jsonl")
        }

        # Opt-in apply_active_kb_audit=True quarantines both parent and typo noisy child
        tbc.prepare_and_lock_splits(
            worktree_root=REPO_ROOT,
            data_repo_root=REPO_ROOT,
            init_model_dir=init_dir,
            artifact_root=art,
            replay_per_class=2,
            noise_aug_per_class=2,
            bitext_cal_per_class=1,
            apply_active_kb_audit=True,
        )

    clean_ids = {r["sample_id"] for r in tbc._read_jsonl(art / "datasets" / "bitext_train_clean.jsonl")}
    noisy_ids = {r["sample_id"] for r in tbc._read_jsonl(art / "datasets" / "bitext_train_noisy.jsonl")}
    q_recs = tbc._read_jsonl(art / "datasets" / "quarantine_records.jsonl")
    assert "bitext_trn_rp_bad_parent" not in clean_ids
    assert "bitext_trn_rp_good_parent" in clean_ids
    assert all(not sid.startswith("bitext_trn_aug_rp_bad_parent") for sid in noisy_ids)
    assert any(r["parent_sample_id"] == "rp_bad_parent" and r["split"] == "bitext_train_clean" for r in q_recs)
    assert any(r["parent_sample_id"] == "rp_bad_parent" and r["split"] == "bitext_train_noisy" and r["reason"].startswith("parent_quarantined:") for r in q_recs)


def test_archive_prep_refuses_overwrite_collision_and_disallows_fit(tmp_path: Path) -> None:
    """--archive-prep uses distinct -prep path, emits non-colliding planned_future_cli, and fails closed on reuse/fit."""
    main_cand = tmp_path / "main_cand"
    local_root = tmp_path / "local_root"
    existing_prep = main_cand / "run-records-v5-prep-test-prep"
    existing_prep.mkdir(parents=True)
    with (
        patch.object(contrast_mod, "MAIN_CANDIDATES_DIR", main_cand),
        patch.object(contrast_mod, "LOCAL_CONTRAST_ROOT", local_root),
        patch.object(sys, "argv", ["prog", "--archive-prep", "--run-id", "v5-prep-test"]),
    ):
        with pytest.raises(FileExistsError, match="MAIN prep records already exist"):
            contrast_mod.main()

    # Pre-existing target fit path also blocks --archive-prep upfront before any write
    (main_cand / "run-records-fit-taken").mkdir(parents=True)
    with (
        patch.object(contrast_mod, "MAIN_CANDIDATES_DIR", main_cand),
        patch.object(contrast_mod, "LOCAL_CONTRAST_ROOT", local_root),
        patch.object(sys, "argv", ["prog", "--archive-prep", "--run-id", "fit-taken"]),
    ):
        with pytest.raises(FileExistsError, match="Planned future fit path already exists"):
            contrast_mod.main()

    with patch.object(sys, "argv", ["prog", "--archive-prep", "--run-contrast-fit", "--run-id", "v5-prep-test"]):
        with pytest.raises(ValueError, match="strictly zero-fit"):
            contrast_mod.main()


def test_archive_prep_zero_fit_and_planned_future_cli_noncolliding(tmp_path: Path) -> None:
    """Running --archive-prep creates -prep archive whose planned_future_cli targets unused fit paths."""
    main_cand = tmp_path / "main_cand"
    main_cand.mkdir(parents=True)
    local_root = tmp_path / "local_root"
    ds_dir = local_root / "dryrun" / "datasets"
    ds_dir.mkdir(parents=True)
    pos_bytes = b'{"sample_id":"p0","text":"where is order","intent":"track_order","selective_label":1,"is_negative":0}\n'
    pos_sha = hashlib.sha256(pos_bytes).hexdigest()
    (ds_dir / "boundary_pos_train.jsonl").write_bytes(pos_bytes)
    (ds_dir / "quarantine_records.jsonl").write_bytes(b"")
    (ds_dir / "semantic_audit_manifest.json").write_text('{"quarantined_total":0,"split_summaries":[]}\n', encoding="utf-8")
    (ds_dir / "dataset_lock_manifest.json").write_text("{}\n", encoding="utf-8")

    src_rel = "scripts/run_boundary_contrast_fit.py"
    src_sha = hashlib.sha256((REPO_ROOT / src_rel).read_bytes()).hexdigest()
    prov_stub = {"git_commit": "b" * 40, "source_hashes": {src_rel: src_sha}}
    preflight_stub = {
        "dry_run": True,
        "fits_executed": 0,
        "canonical_prep": {"cleaned_sha256": "8bc10cfa", "splits_sha256": "1d366e89"},
        "dataset_hashes": {"boundary_pos_train": pos_sha},
        "effective_exposure_counts": {},
    }

    with (
        patch.object(contrast_mod, "MAIN_CANDIDATES_DIR", main_cand),
        patch.object(contrast_mod, "LOCAL_CONTRAST_ROOT", local_root),
        patch.object(contrast_mod, "verify_relevant_source_provenance", return_value=prov_stub),
        patch.object(contrast_mod, "run_preflight_validation", return_value=dict(preflight_stub)),
        patch.object(sys, "argv", ["prog", "--archive-prep", "--run-id", "v5-clean-r2"]),
    ):
        contrast_mod.main()

    prep_dir = main_cand / "run-records-v5-clean-r2-prep"
    assert prep_dir.is_dir()
    assert not (main_cand / "run-records-v5-clean-r2").exists()
    assert not (main_cand / "v5-clean-r2").exists()
    pm = json.loads((prep_dir / "prep_manifest.json").read_text(encoding="utf-8"))
    assert pm["planned_future_cli"][-3:] == ["--run-id", "v5-clean-r2", "--enable-selective-rejector"]
    assert pm["planned_future_paths"]["records_dir"] == str(main_cand / "run-records-v5-clean-r2")
    assert json.loads((prep_dir / "status.json").read_text(encoding="utf-8"))["status"] == "complete"


def test_semantic_audit_manifest_fails_closed_on_mismatched_split_sums() -> None:
    """build_semantic_audit_manifest rejects lossy second-pass summaries (0 vs 25) matching Finding 3."""
    lossy_summary = {
        "split": "bitext_train_clean",
        "input_rows": 7348,
        "kept_rows": 7348,
        "quarantined_rows": 0,
        "status_counts": {"valid": 7348},
        "reason_counts": {},
        "quarantined_by_intent": {},
        "ambiguous_retained_by_intent": {},
    }
    q_rec = {
        "sample_id": "bitext_trn_sample_029467",
        "parent_sample_id": "sample_029467",
        "text_sha256": "0" * 64,
        "intent": "return_policy",
        "source": "bitext_train_partition_clean",
        "reason": "kb_pol_ret_001_physical_instore_channel_contradiction",
        "status": "quarantined_kb_contradiction",
        "split": "bitext_train_clean",
    }
    with pytest.raises(ValueError, match="quarantined sum"):
        tbc.build_semantic_audit_manifest(split_summaries=[lossy_summary], quarantine_records=[q_rec])


def test_faithful_fit2_restore_real_preflight_hashes_unaffected(tmp_path: Path) -> None:
    """Real zero-fit check: scripts/run_faithful_fit2_restore.py matches exact 8/8 Closure + 7/7 Boundary hashes."""
    import scripts.run_faithful_fit2_restore as restore_mod

    class _StubTok:
        def encode(self, text, truncation=False, add_special_tokens=True):
            return [1] * len(text.split())

        def __call__(self, texts, truncation=False, max_length=64):
            return {"input_ids": [[1] * min(len(t.split()), max_length) for t in texts]}

    with patch("pipeline.training.train_boundary_candidate.AutoTokenizer.from_pretrained", return_value=_StubTok()):
        res = restore_mod.run_preflight_validation(REPO_ROOT, tmp_path / "restore_scratch")
    assert res["fits_executed"] == 0
    s1_hashes = res["stage1_c6cae7a_dataset_hashes_match"]
    s2_hashes = res["stage2_d7ddaf2_dataset_hashes_match"]
    assert len(s1_hashes) == 8 and all(s1_hashes.values()), s1_hashes
    assert len(s2_hashes) == 7 and all(s2_hashes.values()), s2_hashes
