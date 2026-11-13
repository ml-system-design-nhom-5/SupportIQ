"""Regression tests for classifier_acceptance_gate contract fixes (B)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

import pipeline.evaluation.classifier_acceptance_gate as gate_mod
from apps.core_backend.intent.routing import STANDARD_INTENTS_46
from pipeline.evaluation.classifier_acceptance_gate import (
    audit_candidate_provenance,
    run_classifier_acceptance_gate,
    validate_calibration_manifest,
)


def _write_dummy_candidate(cand_dir: Path, *, git_commit: str = "deadbeef", rejector_enabled: bool = False) -> tuple[Path, Path]:
    id2label = {str(i): name for i, name in enumerate(STANDARD_INTENTS_46)}
    (cand_dir / "model.safetensors").write_bytes(b"0")
    (cand_dir / "tokenizer.json").write_text("{}", encoding="utf-8")
    (cand_dir / "config.json").write_text(json.dumps({"id2label": id2label}), encoding="utf-8")
    hashes = {
        fn: hashlib.sha256((cand_dir / fn).read_bytes()).hexdigest()
        for fn in ("model.safetensors", "tokenizer.json", "config.json")
    }
    prov_path = cand_dir / "candidate_provenance_manifest.json"
    prov_path.write_text(
        json.dumps(
            {
                "training_lineage": {"epochs": 3},
                "dataset_hashes": {"train.jsonl": "a" * 64},
                "base_model": {"init_weights_sha256": "b" * 64},
                "git_commit": git_commit,
                "artifact_hashes": hashes,
            }
        ),
        encoding="utf-8",
    )
    cal_path = cand_dir / "calibration_manifest.json"
    cal_path.write_text(
        json.dumps(
            {
                "schema_version": "selective_calibration.v1",
                "artifact_hashes": hashes,
                "calibration": {"temperature": 1.29, "min_temperature": 1.0, "calibrated": True},
                "label_space": {"num_labels": 46, "valid_46_label_bijection": True, "id2label": id2label},
                "selective_rejector": {
                    "enabled": rejector_enabled,
                    "type": "logistic_regression_v1",
                    "feature_spec": "logit_geometry_v1",
                    "feature_dim": 8,
                    "scaler_mean": [0.0] * 8,
                    "scaler_scale": [1.0] * 8,
                    "weights": [0.0] * 8,
                    "bias": 0.0,
                    "threshold": 0.0,
                    "reject_when": "below",
                },
            }
        ),
        encoding="utf-8",
    )
    return prov_path, cal_path


def _fake_eval(
    *,
    fa12_correct: int,
    fa12_denom: int = 12,
    sa34_correct: int = 21,
    noise_correct: int = 198,
    holdout: dict[str, Any] | None = None,
    rejector_active: bool = False,
) -> dict[str, Any]:
    return {
        "model_name": "m",
        "score_path": {"score_kind": "calibrated_probability", "temperature": 1.29, "calibrated": True, "experimental_rejector_active": rejector_active},
        "independent_holdout": holdout,
        "ml_oos_80": {"n_total": 80, "flagged_safe_count": 80, "false_draft_eligible_count": 0},
        "ml_noise_420": {
            "n_total": 420,
            "safe_routing_rate": 0.95,
            "selective_metrics": {"correct_intent_draft_eligible_count": noise_correct, "denominator": 420},
        },
        "known_acceptance_regression_not_unseen_holdout": {
            "system_acceptance_156": {
                "escalated_34_macro_f1": 0.70,
                "mandatory_63_real_unsafe_draft_leaks": [],
                "mandatory_63_strict_match": 55,
                "draft_expected_34_correct_intent_draft": sa34_correct,
            },
            "final_acceptance_24": {
                "unanswerable_active_kb_draft_leaks": [],
                "answerable_12_correct_intent_draft": fa12_correct,
                "answerable_12_wrong_intent_draft_cases": [],
                "answerable_12_selective_metrics": {"denominator": fa12_denom},
            },
        },
    }


def test_provenance_audit_rejects_symbolic_head_and_accepts_hex_sha(tmp_path: Path) -> None:
    prov_path, _ = _write_dummy_candidate(tmp_path, git_commit="HEAD")
    res_head = audit_candidate_provenance(tmp_path, prov_path)
    assert res_head["provenance_passed"] is False
    assert "invalid_provenance_git_commit" in res_head["failure_reasons"]

    prov_path, _ = _write_dummy_candidate(tmp_path, git_commit="deadbeef")
    res_ok = audit_candidate_provenance(tmp_path, prov_path)
    assert res_ok["provenance_passed"] is True


def test_calibration_audit_disabled_rejector_label_contract(tmp_path: Path) -> None:
    _, cal_path = _write_dummy_candidate(tmp_path, rejector_enabled=False)
    res = validate_calibration_manifest(tmp_path, cal_path)
    assert res["valid"] is True
    assert res["rejector"]["enabled"] is False
    rej = res["rejector"]
    assert bool(rej and rej.get("enabled", True) is not False) is False


@pytest.mark.parametrize(
    "cand_fa12, cand_sa34, cand_noise, expected_reason",
    [
        (2, 21, 198, "final_acceptance_answerable_coverage_regression"),
        (0, 0, 0, "system_acceptance_draft_coverage_regression"),
    ],
)
def test_gate_rejects_utility_regression_and_always_abstain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cand_fa12: int, cand_sa34: int, cand_noise: int, expected_reason: str
) -> None:
    cand_dir = tmp_path / "cand"
    cand_dir.mkdir()
    prov_path, cal_path = _write_dummy_candidate(cand_dir, git_commit="deadbeef")
    srv_eval = _fake_eval(fa12_correct=4, sa34_correct=17, noise_correct=177)
    cand_eval = _fake_eval(fa12_correct=cand_fa12, sa34_correct=cand_sa34, noise_correct=cand_noise)

    monkeypatch.setattr(gate_mod, "evaluate_model_on_suites", lambda name, *a, **kw: srv_eval if name == "distilbert-supportiq" else cand_eval)
    rep = run_classifier_acceptance_gate(
        repo_root=Path(__file__).resolve().parents[2],
        candidate_name="cand",
        candidate_dir=cand_dir,
        serving_dir=tmp_path / "srv",
        candidate_manifest_path=prov_path,
        calibration_manifest_path=cal_path,
        verify_parity=False,
    )
    assert rep["gate_decision"] == "REJECT"
    assert expected_reason in rep["failure_reasons"]
    assert "no_independent_holdout_split_provided" in rep["warnings"]


def test_gate_fails_closed_on_missing_utility_evidence_and_tiny_holdout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cand_dir = tmp_path / "cand"
    cand_dir.mkdir()
    prov_path, cal_path = _write_dummy_candidate(cand_dir, git_commit="deadbeef")
    eval_path = tmp_path / "eval.jsonl"
    eval_path.write_text(
        json.dumps({"id": "e1", "text": "Show my order history", "intent": "order_history", "group_id": "g1"}) + "\n",
        encoding="utf-8",
    )
    tiny_holdout = {
        "n_total": 2,
        "escalated_34": {"n": 2, "macro_f1": 1.0, "unsafe_draft_eligible_count": 0},
        "supported_12": {"n": 0, "correct_intent_draft_eligible_count": 0},
    }
    srv_eval = _fake_eval(fa12_correct=4, sa34_correct=17, noise_correct=177, holdout=tiny_holdout)
    cand_eval = _fake_eval(fa12_correct=4, sa34_correct=17, noise_correct=177, fa12_denom=0, holdout=tiny_holdout)

    monkeypatch.setattr(gate_mod, "evaluate_model_on_suites", lambda name, *a, **kw: srv_eval if name == "distilbert-supportiq" else cand_eval)
    rep = run_classifier_acceptance_gate(
        repo_root=Path(__file__).resolve().parents[2],
        candidate_name="cand",
        candidate_dir=cand_dir,
        serving_dir=tmp_path / "srv",
        candidate_manifest_path=prov_path,
        calibration_manifest_path=cal_path,
        eval_split_path=eval_path,
        verify_parity=False,
    )
    assert rep["gate_decision"] == "REJECT"
    assert "holdout_insufficient_supported_12_coverage" in rep["failure_reasons"]
    assert "missing_utility_evidence" in rep["failure_reasons"]


def test_gate_never_marks_missing_holdout_promotion_eligible(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cand_dir = tmp_path / 'cand'
    cand_dir.mkdir()
    prov_path, cal_path = _write_dummy_candidate(cand_dir, git_commit='deadbeef')
    srv_eval = _fake_eval(fa12_correct=4, sa34_correct=17, noise_correct=177)
    cand_eval = _fake_eval(fa12_correct=4, sa34_correct=17, noise_correct=177)
    monkeypatch.setattr(gate_mod, 'evaluate_model_on_suites', lambda name, *a, **kw: srv_eval if name == 'distilbert-supportiq' else cand_eval)
    rep = run_classifier_acceptance_gate(
        repo_root=Path(__file__).resolve().parents[2],
        candidate_name='cand', candidate_dir=cand_dir, serving_dir=tmp_path / 'srv',
        candidate_manifest_path=prov_path, calibration_manifest_path=cal_path, verify_parity=False,
    )
    assert rep['gate_decision'] == 'REJECT'
    assert 'missing_group_isolated_holdout' in rep['failure_reasons']
    assert rep['promotion_eligible'] is False
    assert rep['acceptance_scope'] == 'regression_only_not_promotion_eligible'
    rep_strict = run_classifier_acceptance_gate(
        repo_root=Path(__file__).resolve().parents[2],
        candidate_name='cand', candidate_dir=cand_dir, serving_dir=tmp_path / 'srv',
        candidate_manifest_path=prov_path, calibration_manifest_path=cal_path, verify_parity=False,
        require_independent_holdout=True,
    )
    assert rep_strict['gate_decision'] == 'REJECT'
    assert 'missing_independent_holdout_split' in rep_strict['failure_reasons']
    assert rep_strict['promotion_eligible'] is False
