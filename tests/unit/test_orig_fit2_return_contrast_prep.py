from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
import torch

from pipeline.evaluation.classifier_acceptance_gate import STANDARD_INTENTS_46
from pipeline.training.orig_fit2_return_contrast_data import (
    ORIG_FIT2_STAGE2_REL,
    build_orig_fit2_return_contrast_rows,
)
from pipeline.training.train_boundary_candidate import classify_row_kb_semantics
from scripts.run_boundary_contrast_fit import (
    EXPECTED_FIT2_SHA256,
    EXPECTED_SERVING_SHA256,
    _write_and_verify_sha_inventory,
    validate_zero_fit_prep_namespace,
)
from scripts.run_orig_fit2_return_contrast_fit import (
    OPTION_A_LOCKED,
    run_authorized_option_a_fit,
    validate_option_a_settings,
)
from scripts.run_orig_fit2_return_contrast_prep import (
    EXPECTED_FIT1_SHA256,
    RELEVANT_SOURCE_PATHS,
    UNCHANGED_ORIGINAL_RECIPE_PARAMETERS,
    _build_planned_option_a_plan,
    run_orig_fit2_preflight,
    verify_orig_relevant_source_provenance,
)


def test_verify_orig_relevant_source_provenance_blocks_uncommitted_diff(monkeypatch, tmp_path):
    calls = {"n": 0}

    def _fake_check_output(cmd, **kwargs):
        calls["n"] += 1
        return ("a" * 40) + "\n" if "rev-parse" in cmd else " M scripts/run_orig_fit2_return_contrast_fit.py\n"

    monkeypatch.setattr(subprocess, "check_output", _fake_check_output)
    with pytest.raises(RuntimeError, match="Uncommitted changes in relevant source files"):
        verify_orig_relevant_source_provenance(tmp_path)


def test_extension_balance_kb_semantics_and_no_refund_policy_leakage():
    rows = build_orig_fit2_return_contrast_rows()
    assert len(rows) == 18

    by_intent = {}
    for row in rows:
        assert row["intent"] in STANDARD_INTENTS_46
        assert row["split"] == "train"
        assert row["kb_version"] == "approved_kb.v2.json"
        assert row["selective_label"] == 1
        assert row["is_negative"] == 0
        if row["intent"] == "return_policy":
            low = row["text"].lower()
            assert "refund" not in low, f"Refund overlap in {row['sample_id']}: {row['text']}"
            assert "freight" not in low, f"Freight overlap in {row['sample_id']}: {row['text']}"
            assert "warehouse" not in low, f"Warehouse overlap in {row['sample_id']}: {row['text']}"
            assert "custom-made" not in low, f"Non-KB item in {row['sample_id']}: {row['text']}"
        sem = classify_row_kb_semantics(row)
        assert sem["status"] == "valid", f"{row['sample_id']} failed KB check: {sem}"
        by_intent[row["intent"]] = by_intent.get(row["intent"], 0) + 1

    assert by_intent == {"return_policy": 10, "return_product_in_store": 8}
    assert by_intent["return_policy"] * 4 == 40
    assert by_intent["return_product_in_store"] * 5 == 40


def test_zero_fit_preflight_reproduces_orig_baseline_and_blocks_optimizer_calibrator(monkeypatch, tmp_path):
    repo_root = Path(__file__).resolve().parents[2]
    stage2_ref = repo_root / ORIG_FIT2_STAGE2_REL
    if not stage2_ref.is_dir():
        pytest.skip("Archived faithful Fit2 stage2_inputs not present")

    def _forbid(*args, **kwargs):
        raise AssertionError("Zero-fit prep must never invoke optimizer or calibrator")

    class _StubTok:
        def encode(self, text, truncation=False, add_special_tokens=True):
            return [1] * len(text.split())

        def __call__(self, texts, truncation=False, max_length=64):
            return {"input_ids": [[1] * min(len(t.split()), max_length) for t in texts]}

    monkeypatch.setattr(torch.optim, "AdamW", _forbid)
    monkeypatch.setattr("pipeline.training.train_boundary_candidate.fit_temperature_on_calibration_logits", _forbid)
    monkeypatch.setattr("pipeline.training.train_boundary_candidate.run_fit_and_lock_candidate", _forbid)
    monkeypatch.setattr("pipeline.training.train_boundary_candidate.AutoTokenizer.from_pretrained", lambda *a, **kw: _StubTok())

    preflight = run_orig_fit2_preflight(repo_root, tmp_path / "dryrun")
    assert preflight["dry_run"] is True
    assert preflight["fits_executed"] == 0
    assert preflight["optimizer_invoked"] is False
    assert preflight["calibrator_invoked"] is False
    assert preflight["serving_weights_sha256"] == EXPECTED_SERVING_SHA256
    assert preflight["fit1_reference_weights_sha256"] == EXPECTED_FIT1_SHA256
    assert preflight["starting_checkpoint"]["weights_sha256"] == EXPECTED_FIT2_SHA256
    assert preflight["starting_checkpoint"]["temperature"] == 1.0
    assert preflight["starting_checkpoint"]["rejector_enabled"] is False
    assert preflight["starting_checkpoint"]["num_labels"] == 46

    diff = preflight["baseline_vs_new_diff"]
    assert set(diff["changed_files"].keys()) == {"boundary_pos_train.jsonl", "full_train_split.jsonl"}
    assert len(diff["unchanged_bit_identical_files"]) == 11
    assert diff["exposure_delta"] == {
        "raw_domain_return_policy_delta": 10,
        "raw_domain_return_product_in_store_delta": 8,
        "effective_domain_return_policy_delta": 40,
        "effective_domain_return_product_in_store_delta": 40,
        "effective_train_total_delta": 80,
    }
    assert preflight["counts"]["domain_pos_train"] == 199
    assert preflight["counts"]["domain_pos_cal"] == 86
    assert preflight["counts"]["domain_pos_eval"] == 122
    iso = preflight["isolation_audit"]
    assert iso["isolation_passed"] is True
    assert iso["pseudonymize_changed_extension_rows"] == []
    assert iso["max_jaccard_across_all_frozen_suites"] < 0.55
    assert iso["max_token_f1_across_all_frozen_suites"] < 0.65
    assert iso["post_privacy_max_jaccard_across_all_frozen_suites"] < 0.55
    assert iso["post_privacy_max_token_f1_across_all_frozen_suites"] < 0.65
    assert (
        preflight["historical_baseline_noisy_overlap_disclosure"]["historical_bitext_train_noisy_vs_eval_norm_overlap_count"]
        == 3
    )


def test_prep_namespace_collision_and_option_a_plan_contract(tmp_path):
    candidates_dir = tmp_path / "candidates"
    local_root = tmp_path / "local"
    candidates_dir.mkdir(parents=True)
    local_root.mkdir(parents=True)

    ns = validate_zero_fit_prep_namespace(
        prep_run_id="fit2-orig-ret-channel-v2",
        fit_run_id="fit2-orig-ret-channel-fit-v1",
        main_candidates_dir=candidates_dir,
        local_contrast_root=local_root,
    )
    assert ns["prep_records_dir"].name == "run-records-fit2-orig-ret-channel-v2-prep"

    ns["prep_records_dir"].mkdir()
    with pytest.raises(FileExistsError):
        validate_zero_fit_prep_namespace(
            prep_run_id="fit2-orig-ret-channel-v2",
            fit_run_id="fit2-orig-ret-channel-fit-v1",
            main_candidates_dir=candidates_dir,
            local_contrast_root=local_root,
        )

    plan = _build_planned_option_a_plan(
        prep_records_dir=ns["prep_records_dir"],
        planned_fit_run_id="fit2-orig-ret-channel-fit-v1",
        planned_future_paths={
            "archive_dir": str(ns["fit_archive_dir"]),
            "records_dir": str(ns["fit_records_dir"]),
            "local_dir": str(ns["fit_local_dir"]),
        },
    )
    assert plan["epochs"] == 3 and plan["lr"] == 2e-5
    assert plan["enable_selective_rejector"] is False
    assert plan["authorized_to_train_now"] is False
    assert "scripts.run_orig_fit2_return_contrast_fit" in " ".join(plan["planned_cli"])


def test_option_a_runner_guards_reject_wrong_settings_and_dirty_or_tampered_inputs(monkeypatch, tmp_path):
    with pytest.raises(ValueError, match="epochs=3"):
        validate_option_a_settings(
            epochs=2, lr=2e-5, batch_size=32, seed=42, fit_mode="fit2_supcon_energy", enable_selective_rejector=False
        )
    with pytest.raises(ValueError, match="lr=2e-5"):
        validate_option_a_settings(
            epochs=3, lr=1e-5, batch_size=32, seed=42, fit_mode="fit2_supcon_energy", enable_selective_rejector=False
        )
    with pytest.raises(ValueError, match="rejector OFF"):
        validate_option_a_settings(
            epochs=3, lr=2e-5, batch_size=32, seed=42, fit_mode="fit2_supcon_energy", enable_selective_rejector=True
        )
    assert OPTION_A_LOCKED["epochs"] == 3 and OPTION_A_LOCKED["lr"] == 2e-5

    # Build a synthetic clean repo + locked v2-prep bundle to test fail-closed guards with zero fits.
    repo_root = tmp_path / "repo"
    for rel in RELEVANT_SOURCE_PATHS:
        fp = repo_root / rel
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(f"# {rel}\n", encoding="utf-8")

    prep_dir = tmp_path / "run-records-fit2-orig-ret-channel-v2-prep"
    ds_dir = prep_dir / "datasets"
    ds_dir.mkdir(parents=True)
    split_manifest = ds_dir / "split_manifest.json"
    full_train = ds_dir / "full_train_split.jsonl"
    split_manifest.write_text('{"ok": true}\n', encoding="utf-8")
    full_train.write_text('{"sample_id": "x"}\n', encoding="utf-8")

    import hashlib

    def _sha(p: Path) -> str:
        return hashlib.sha256(p.read_bytes()).hexdigest().lower()

    source_hashes = {rel: _sha(repo_root / rel) for rel in RELEVANT_SOURCE_PATHS}
    git_sha = "a" * 40
    ds_hashes = {"boundary_split_manifest": _sha(split_manifest), "full_train_split": _sha(full_train)}
    new_hashes = {"split_manifest.json": _sha(split_manifest), "full_train_split.jsonl": _sha(full_train)}

    (prep_dir / "status.json").write_text(
        json.dumps({"status": "complete", "fits_executed": 0, "prep_archive": True}), encoding="utf-8"
    )
    (prep_dir / "prep_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "orig_fit2_return_contrast_prep.v2",
                "git_commit": git_sha,
                "source_hashes": source_hashes,
                "unchanged_original_recipe_parameters": UNCHANGED_ORIGINAL_RECIPE_PARAMETERS,
                "option_a_execution_plan": {"epochs": 3, "lr": 2e-5, "enable_selective_rejector": False},
                "preflight": {
                    "extension_version": "orig_fit2_return_channel_contrast_v2",
                    "counts": {"extension_pos_train_added": 18},
                    "dataset_hashes": ds_hashes,
                    "new_input_file_hashes": new_hashes,
                    "serving_weights_sha256": EXPECTED_SERVING_SHA256,
                    "fit1_reference_weights_sha256": EXPECTED_FIT1_SHA256,
                    "starting_checkpoint": {"weights_sha256": EXPECTED_FIT2_SHA256},
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    _write_and_verify_sha_inventory(prep_dir, "sidecar_sha_inventory.json")

    candidates_dir = tmp_path / "candidates"
    local_base = tmp_path / "local"
    init_dir = tmp_path / "init_f695"
    serving_dir = tmp_path / "serving"
    init_dir.mkdir()
    serving_dir.mkdir()
    (serving_dir / "model.safetensors").write_bytes(b"serving")

    monkeypatch.setattr(
        "scripts.run_orig_fit2_return_contrast_fit._sha256_lower",
        lambda p: EXPECTED_SERVING_SHA256 if p == serving_dir / "model.safetensors" else _sha(p),
    )
    monkeypatch.setattr(
        "scripts.run_orig_fit2_return_contrast_fit.verify_fit2_starting_checkpoint",
        lambda p: {"weights_sha256": EXPECTED_FIT2_SHA256, "temperature": 1.0, "rejector_enabled": False, "num_labels": 46},
    )
    monkeypatch.setattr(
        "scripts.run_orig_fit2_return_contrast_fit.verify_orig_relevant_source_provenance",
        lambda root: {"git_commit": git_sha, "source_hashes": {rel: _sha(root / rel) for rel in RELEVANT_SOURCE_PATHS}},
    )

    # 1) Validate-only passes cleanly with zero fits.
    val_res = run_authorized_option_a_fit(
        repo_root=repo_root,
        prep_dir=prep_dir,
        run_id="fit2-orig-ret-channel-fit-v1",
        execute_fit=False,
        main_candidates_dir=candidates_dir,
        local_root_base=local_base,
        init_model_dir=init_dir,
        serving_dir=serving_dir,
    )
    assert val_res["validated_only"] is True and val_res["fits_executed"] == 0

    # 2) Mocked Option A execution archives complete outputs, manifests, logs, and inventories cleanly.
    def _fake_fit(**kwargs):
        assert (kwargs["epochs"], kwargs["lr"], kwargs["batch_size"], kwargs["seed"]) == (3, 2e-5, 32, 42)
        assert kwargs["fit_mode"] == "fit2_supcon_energy" and kwargs["enable_selective_rejector"] is False
        cand_dir = kwargs["artifact_root"] / kwargs["output_subdir"]
        cand_dir.mkdir(parents=True)
        for fname in ("model.safetensors", "tokenizer.json", "tokenizer_config.json", "config.json"):
            (cand_dir / fname).write_bytes(fname.encode("utf-8"))
        (cand_dir / "calibration_manifest.json").write_text('{"valid": true, "temperature": 1.0}', encoding="utf-8")
        (cand_dir / "candidate_provenance_manifest.json").write_text('{"provenance_status": "verified"}', encoding="utf-8")
        return {"fit_mode": "fit2_supcon_energy", "temperature": 1.0}

    monkeypatch.setattr("scripts.run_orig_fit2_return_contrast_fit.run_fit_and_lock_candidate", _fake_fit)
    monkeypatch.setattr(
        "scripts.run_orig_fit2_return_contrast_fit.validate_calibration_manifest",
        lambda d, p: {"valid": True, "temperature": 1.0, "rejector": {"enabled": False}},
    )
    monkeypatch.setattr(
        "scripts.run_orig_fit2_return_contrast_fit.audit_candidate_provenance",
        lambda d, p: {"provenance_passed": True, "num_labels": 46},
    )
    monkeypatch.setattr(
        "scripts.run_orig_fit2_return_contrast_fit.verify_reload_from_archive",
        lambda d: {"reload_verified": True, "archive_dir": str(d), "num_labels": 46},
    )

    fit_out = run_authorized_option_a_fit(
        repo_root=repo_root,
        prep_dir=prep_dir,
        run_id="fit2-orig-ret-channel-fit-v1",
        execute_fit=True,
        main_candidates_dir=candidates_dir,
        local_root_base=local_base,
        init_model_dir=init_dir,
        serving_dir=serving_dir,
    )
    assert fit_out["fits_executed"] == 1
    arch = Path(fit_out["archive_dir"])
    recs = Path(fit_out["records_dir"])
    assert (arch / "archive_sha_inventory.json").is_file()
    assert (recs / "sidecar_sha_inventory.json").is_file()
    assert (recs / "inputs" / "inputs_sha256_inventory.json").is_file()
    assert (recs / "run.log").is_file()
    assert json.loads((recs / "status.json").read_text(encoding="utf-8"))["status"] == "complete"
    assert json.loads((recs / "run_config.json").read_text(encoding="utf-8"))["epochs"] == 3

    # 3) Output collision guard fails closed.
    with pytest.raises(FileExistsError, match="Output path already exists"):
        run_authorized_option_a_fit(
            repo_root=repo_root,
            prep_dir=prep_dir,
            run_id="fit2-orig-ret-channel-fit-v1",
            execute_fit=False,
            main_candidates_dir=candidates_dir,
            local_root_base=local_base,
            init_model_dir=init_dir,
            serving_dir=serving_dir,
        )

    # 4) Wrong Serving SHA guard fails closed on an unused run_id.
    monkeypatch.setattr("scripts.run_orig_fit2_return_contrast_fit._sha256_lower", _sha)
    with pytest.raises(ValueError, match="Serving weights SHA mismatch"):
        run_authorized_option_a_fit(
            repo_root=repo_root,
            prep_dir=prep_dir,
            run_id="fit2-orig-ret-channel-fit-v2",
            execute_fit=False,
            main_candidates_dir=candidates_dir,
            local_root_base=local_base,
            init_model_dir=init_dir,
            serving_dir=serving_dir,
        )
    monkeypatch.setattr(
        "scripts.run_orig_fit2_return_contrast_fit._sha256_lower",
        lambda p: EXPECTED_SERVING_SHA256 if p == serving_dir / "model.safetensors" else _sha(p),
    )

    # 5) Relevant source edit after prep fails closed.
    (repo_root / RELEVANT_SOURCE_PATHS[0]).write_text("# modified after prep\n", encoding="utf-8")
    with pytest.raises(ValueError, match="source file hashes differ"):
        run_authorized_option_a_fit(
            repo_root=repo_root,
            prep_dir=prep_dir,
            run_id="fit2-orig-ret-channel-fit-v2",
            execute_fit=False,
            main_candidates_dir=candidates_dir,
            local_root_base=local_base,
            init_model_dir=init_dir,
            serving_dir=serving_dir,
        )
    (repo_root / RELEVANT_SOURCE_PATHS[0]).write_text(f"# {RELEVANT_SOURCE_PATHS[0]}\n", encoding="utf-8")

    # 6) Tampered prep dataset input fails closed via sidecar inventory / input SHA check.
    full_train.write_text('{"sample_id": "tampered"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="SHA mismatch"):
        run_authorized_option_a_fit(
            repo_root=repo_root,
            prep_dir=prep_dir,
            run_id="fit2-orig-ret-channel-fit-v2",
            execute_fit=False,
            main_candidates_dir=candidates_dir,
            local_root_base=local_base,
            init_model_dir=init_dir,
            serving_dir=serving_dir,
        )
