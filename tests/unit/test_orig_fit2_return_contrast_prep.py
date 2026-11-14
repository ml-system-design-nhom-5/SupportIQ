from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
import torch

from pipeline.evaluation.classifier_acceptance_gate import STANDARD_INTENTS_46
from pipeline.training.orig_fit2_return_contrast_data import (
    EXPECTED_ORIG_STAGE2_LOCKED_FILES,
    ORIG_FIT2_STAGE2_REL,
    build_orig_fit2_return_contrast_rows,
    prepare_and_lock_orig_fit2_zero_delta_control_splits,
)
from pipeline.training.train_boundary_candidate import (
    build_teacher_anchor_mask,
    classify_row_kb_semantics,
    compute_masked_teacher_kl_loss,
)
from scripts.run_boundary_contrast_fit import (
    EXPECTED_FIT2_SHA256,
    EXPECTED_SERVING_SHA256,
    FIT2_BASELINE_DIR,
    MAIN_CANDIDATES_DIR,
    _write_and_verify_sha_inventory,
    validate_zero_fit_prep_namespace,
)
from scripts.run_orig_fit2_return_contrast_fit import (
    OPTION_A_LOCKED,
    main as fit_cli_main,
    run_authorized_fit,
    run_authorized_option_a_fit,
    validate_option_a_settings,
    validate_profile_settings,
)
from scripts.run_orig_fit2_return_contrast_prep import (
    AUTHORIZED_FIT_PROFILES,
    CAL_GUARD_DENOMINATORS,
    CAL_GUARD_FLOAT_TOLERANCE,
    DEFAULT_PREP_RUN_ID,
    EXPECTED_FIT1_SHA256,
    RELEVANT_SOURCE_PATHS,
    UNCHANGED_ORIGINAL_RECIPE_PARAMETERS,
    _build_planned_execution_plan,
    _build_planned_option_a_plan,
    compute_cal_guard_metrics_from_logits,
    evaluate_cal_guard_metrics_for_model,
    evaluate_cal_guard_report,
    run_orig_fit2_preflight,
    verify_git_commit_ancestor,
    verify_orig_relevant_source_provenance,
)


def test_verify_orig_relevant_source_provenance_blocks_uncommitted_diff(monkeypatch, tmp_path):
    seen_cmds = []

    def _fake_check_output(cmd, **kwargs):
        seen_cmds.append(list(cmd))
        return ("a" * 40) + "\n" if "rev-parse" in cmd else " M scripts/run_orig_fit2_return_contrast_fit.py\n"

    monkeypatch.setattr(subprocess, "check_output", _fake_check_output)
    with pytest.raises(RuntimeError, match="Uncommitted changes in relevant source files"):
        verify_orig_relevant_source_provenance(tmp_path)
    assert "--untracked-files=all" in seen_cmds[1]
    assert "apps/backend/tickets/privacy.py" in RELEVANT_SOURCE_PATHS
    assert "pipeline/training/train_domain_candidate.py" in RELEVANT_SOURCE_PATHS
    assert "pipeline/preparation/utils.py" in RELEVANT_SOURCE_PATHS


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
    for rel in RELEVANT_SOURCE_PATHS:
        snap_fp = prep_dir / "source_snapshot" / rel
        snap_fp.parent.mkdir(parents=True, exist_ok=True)
        snap_fp.write_text(f"# {rel}\n", encoding="utf-8")

    git_sha = "a" * 40
    head_sha = "b" * 40
    ds_hashes = {"boundary_split_manifest": _sha(split_manifest), "full_train_split": _sha(full_train)}
    new_hashes = {"split_manifest.json": _sha(split_manifest), "full_train_split.jsonl": _sha(full_train)}

    (prep_dir / "status.json").write_text(
        json.dumps({"status": "complete", "fits_executed": 0, "prep_archive": True}), encoding="utf-8"
    )
    (prep_dir / "prep_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "orig_fit2_return_contrast_prep.v3",
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
        lambda root: {"git_commit": head_sha, "source_hashes": {rel: _sha(root / rel) for rel in RELEVANT_SOURCE_PATHS}},
    )
    monkeypatch.setattr(
        "scripts.run_orig_fit2_return_contrast_fit.verify_git_commit_ancestor",
        lambda root, anc, desc="HEAD": head_sha,
    )

    # 1) Validate-only passes cleanly with zero fits (including descendant HEAD != prep git_sha).
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
    assert val_res["prep_git_commit"] == git_sha and val_res["head_git_commit"] == head_sha

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


def test_real_git_ancestor_source_hash_and_incomplete_exception_path(monkeypatch, tmp_path):
    """Verify real git ancestor + source-hash checks and execute_fit=True incomplete status handling."""
    import hashlib
    import shutil

    def _sha(p: Path) -> str:
        return hashlib.sha256(p.read_bytes()).hexdigest().lower()

    def _git(cwd: Path, *args: str) -> str:
        return subprocess.check_output(["git", *args], cwd=str(cwd), text=True).strip()

    repo_root = tmp_path / "git_repo"
    repo_root.mkdir()
    _git(repo_root, "init")
    _git(repo_root, "config", "user.name", "Test")
    _git(repo_root, "config", "user.email", "test@example.com")

    for rel in RELEVANT_SOURCE_PATHS:
        fp = repo_root / rel
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(f"# {rel}\n", encoding="utf-8")
    _git(repo_root, "add", ".")
    _git(repo_root, "commit", "-m", "prep baseline")
    prep_commit = _git(repo_root, "rev-parse", "HEAD")

    # Side-branch non-ancestor commit with identical RELEVANT_SOURCE_PATHS content.
    _git(repo_root, "checkout", "-b", "other")
    (repo_root / "docs/unrelated.md").parent.mkdir(parents=True, exist_ok=True)
    (repo_root / "docs/unrelated.md").write_text("side branch\n", encoding="utf-8")
    _git(repo_root, "add", "docs/unrelated.md")
    _git(repo_root, "commit", "-m", "side branch")
    non_ancestor_commit = _git(repo_root, "rev-parse", "HEAD")

    _git(repo_root, "checkout", "-")
    (repo_root / "docs/audits/review.md").parent.mkdir(parents=True, exist_ok=True)
    (repo_root / "docs/audits/review.md").write_text("review doc\n", encoding="utf-8")
    _git(repo_root, "add", "docs/audits/review.md")
    _git(repo_root, "commit", "-m", "descendant review doc")
    doc_descendant_commit = _git(repo_root, "rev-parse", "HEAD")
    assert doc_descendant_commit != prep_commit

    prep_dir = tmp_path / f"run-records-{DEFAULT_PREP_RUN_ID}-prep"
    ds_dir = prep_dir / "datasets"
    ds_dir.mkdir(parents=True)
    split_manifest = ds_dir / "split_manifest.json"
    full_train = ds_dir / "full_train_split.jsonl"
    split_manifest.write_text('{"ok": true}\n', encoding="utf-8")
    full_train.write_text('{"sample_id": "x"}\n', encoding="utf-8")
    source_hashes = {rel: _sha(repo_root / rel) for rel in RELEVANT_SOURCE_PATHS}
    for rel in RELEVANT_SOURCE_PATHS:
        dst = prep_dir / "source_snapshot" / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(repo_root / rel, dst)

    def _write_prep_manifest(commit_sha: str) -> None:
        (prep_dir / "status.json").write_text(
            json.dumps({"status": "complete", "fits_executed": 0, "prep_archive": True}), encoding="utf-8"
        )
        (prep_dir / "prep_manifest.json").write_text(
            json.dumps(
                {
                    "schema_version": "orig_fit2_return_contrast_prep.v3",
                    "git_commit": commit_sha,
                    "source_hashes": source_hashes,
                    "unchanged_original_recipe_parameters": UNCHANGED_ORIGINAL_RECIPE_PARAMETERS,
                    "option_a_execution_plan": {"epochs": 3, "lr": 2e-5, "enable_selective_rejector": False},
                    "preflight": {
                        "extension_version": "orig_fit2_return_channel_contrast_v2",
                        "counts": {"extension_pos_train_added": 18},
                        "dataset_hashes": {
                            "boundary_split_manifest": _sha(split_manifest),
                            "full_train_split": _sha(full_train),
                        },
                        "new_input_file_hashes": {
                            "split_manifest.json": _sha(split_manifest),
                            "full_train_split.jsonl": _sha(full_train),
                        },
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

    # 1) Non-ancestor commit rejected even when RELEVANT_SOURCE_PATHS hashes match.
    _write_prep_manifest(non_ancestor_commit)
    with pytest.raises(ValueError, match="not an ancestor"):
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

    # 2) Valid doc-only descendant HEAD != prep_commit is accepted.
    _write_prep_manifest(prep_commit)
    assert verify_git_commit_ancestor(repo_root, prep_commit, doc_descendant_commit) == doc_descendant_commit
    res = run_authorized_option_a_fit(
        repo_root=repo_root,
        prep_dir=prep_dir,
        run_id="fit2-orig-ret-channel-fit-v1",
        execute_fit=False,
        main_candidates_dir=candidates_dir,
        local_root_base=local_base,
        init_model_dir=init_dir,
        serving_dir=serving_dir,
    )
    assert res["prep_git_commit"] == prep_commit
    assert res["head_git_commit"] == doc_descendant_commit
    assert res["fits_executed"] == 0

    # 3) execute_fit=True exception path records status == "incomplete" and fits_completed == 0.
    def _boom(**kwargs):
        raise RuntimeError("simulated training failure")

    monkeypatch.setattr("scripts.run_orig_fit2_return_contrast_fit.run_fit_and_lock_candidate", _boom)
    with pytest.raises(RuntimeError, match="simulated training failure"):
        run_authorized_option_a_fit(
            repo_root=repo_root,
            prep_dir=prep_dir,
            run_id="fit2-orig-ret-channel-fit-v1",
            execute_fit=True,
            main_candidates_dir=candidates_dir,
            local_root_base=local_base,
            init_model_dir=init_dir,
            serving_dir=serving_dir,
        )
    status_json = json.loads((candidates_dir / "run-records-fit2-orig-ret-channel-fit-v1" / "status.json").read_text(encoding="utf-8"))
    assert status_json["status"] == "incomplete"
    assert status_json["fits_completed"] == 0
    assert status_json["prep_git_commit"] == prep_commit
    assert status_json["head_git_commit"] == doc_descendant_commit

    # 4) Committed descendant modifying a relevant dependency-closure file fails closed.
    (repo_root / "apps/backend/tickets/privacy.py").write_text("# changed dependency\n", encoding="utf-8")
    _git(repo_root, "add", "apps/backend/tickets/privacy.py")
    _git(repo_root, "commit", "-m", "modify relevant dependency")
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


def _make_synthetic_cal_surfaces():
    from apps.core_backend.intent.routing import ESCALATED_34_INTENTS, SUPPORTED_12_INTENTS

    pos_sup12 = [{"sample_id": f"sup_{i}", "intent": SUPPORTED_12_INTENTS[i % 12], "text": f"s {i}"} for i in range(48)]
    pos_esc34 = [{"sample_id": f"esc_{i}", "intent": ESCALATED_34_INTENTS[i % 34], "text": f"e {i}"} for i in range(38)]
    pos_cal = pos_sup12 + pos_esc34
    bitext_cal = [{"sample_id": f"bit_{i}", "intent": STANDARD_INTENTS_46[i % 46], "text": f"b {i}"} for i in range(690)]
    neg_cal = [{"sample_id": f"neg_{i}", "intent": "out_of_scope", "text": f"n {i}"} for i in range(48)]
    added_18 = [
        {
            "sample_id": f"orig_ret_ch_{i}",
            "intent": "return_policy" if i < 10 else "return_product_in_store",
            "text": f"a {i}",
        }
        for i in range(18)
    ]
    return {
        "boundary_pos_cal": pos_cal,
        "bitext_cal": bitext_cal,
        "boundary_neg_cal": neg_cal,
        "pos_train_added_18": added_18,
    }


def _uniform_row_with_target(target_idx: int, target_prob: float):
    import math
    import numpy as np

    assert 0.0 < target_prob < 1.0
    other_prob = (1.0 - target_prob) / 45.0
    logits = np.full(46, math.log(other_prob), dtype=np.float64)
    logits[target_idx] = math.log(target_prob)
    return logits


def test_cal_guard_integer_gates_anti_all_abstain_and_float_tolerance():
    import numpy as np
    from apps.core_backend.intent.routing import ESCALATED_34_INTENTS, SUPPORTED_12_INTENTS

    idx_by_label = {label: i for i, label in enumerate(STANDARD_INTENTS_46)}
    sup0 = idx_by_label[SUPPORTED_12_INTENTS[0]]
    esc0 = idx_by_label[ESCALATED_34_INTENTS[0]]
    surfaces = _make_synthetic_cal_surfaces()

    def _build_logits(
        *,
        sup12_correct: int = 38,
        sup12_ge70_target: int = 28,
        sup12_ge80_target: int = 24,
        esc34_correct: int = 30,
        esc34_conf: float = 0.70,
        esc34_row0_sup12_prob: float | None = None,
        bitext_correct: int = 689,
        added_correct: int = 16,
        neg_pred_sup12: int = 9,
        neg_row0_sup12_prob: float = 0.55,
    ):
        sup12_probs = [0.85] * sup12_ge80_target + [0.75] * (sup12_ge70_target - sup12_ge80_target) + [0.60] * (
            48 - sup12_ge70_target
        )
        pos_logits = []
        for i in range(48):
            true_idx = idx_by_label[surfaces["boundary_pos_cal"][i]["intent"]]
            wrong_idx = (true_idx + 1) % 46
            chosen = true_idx if i < sup12_correct else wrong_idx
            pos_logits.append(_uniform_row_with_target(chosen, sup12_probs[i]))
        for j in range(38):
            row = surfaces["boundary_pos_cal"][48 + j]
            true_idx = idx_by_label[row["intent"]]
            wrong_idx = [idx_by_label[x] for x in ESCALATED_34_INTENTS if x != row["intent"]][0]
            if j == 0 and esc34_row0_sup12_prob is not None:
                rem = (1.0 - esc34_row0_sup12_prob) / 45.0
                z = np.full(46, np.log(rem), dtype=np.float64)
                z[sup0] = np.log(esc34_row0_sup12_prob)
                pos_logits.append(z)
            else:
                chosen = true_idx if j < esc34_correct else wrong_idx
                pos_logits.append(_uniform_row_with_target(chosen, esc34_conf))

        bit_logits = []
        for i, row in enumerate(surfaces["bitext_cal"]):
            true_idx = idx_by_label[row["intent"]]
            wrong_idx = (true_idx + 1) % 46
            bit_logits.append(_uniform_row_with_target(true_idx if i < bitext_correct else wrong_idx, 0.90))

        add_logits = []
        for i, row in enumerate(surfaces["pos_train_added_18"]):
            true_idx = idx_by_label[row["intent"]]
            wrong_idx = (true_idx + 1) % 46
            add_logits.append(_uniform_row_with_target(true_idx if i < added_correct else wrong_idx, 0.90))

        neg_logits = []
        for i in range(48):
            if i == 0:
                neg_logits.append(_uniform_row_with_target(sup0, neg_row0_sup12_prob))
            elif i < neg_pred_sup12:
                neg_logits.append(_uniform_row_with_target(sup0, 0.40))
            else:
                neg_logits.append(_uniform_row_with_target(esc0, 0.60))

        return {
            "boundary_pos_cal": np.vstack(pos_logits),
            "bitext_cal": np.vstack(bit_logits),
            "boundary_neg_cal": np.vstack(neg_logits),
            "pos_train_added_18": np.vstack(add_logits),
        }

    base_metrics = compute_cal_guard_metrics_from_logits(
        _build_logits(sup12_correct=38, esc34_correct=30, esc34_conf=0.65, added_correct=8, neg_row0_sup12_prob=0.55),
        surfaces,
    )
    cand_pass = compute_cal_guard_metrics_from_logits(
        _build_logits(sup12_correct=38, esc34_correct=30, esc34_conf=0.66, added_correct=15, neg_row0_sup12_prob=0.55),
        surfaces,
    )
    rep_pass = evaluate_cal_guard_report(cand_pass, base_metrics)
    assert rep_pass["passed"] is True
    assert rep_pass["recommended_status"] == "CAL_GUARD_PASS_READY_FOR_C_EVAL"

    # Integer gates: 1-row shortage on any exact threshold must fail.
    for fail_name, kwargs in (
        ("boundary_pos_cal_correct_count", dict(sup12_correct=38, esc34_correct=29)),
        ("boundary_pos_cal_sup12_correct_count", dict(sup12_correct=37, esc34_correct=31)),
        ("bitext_cal_correct_count", dict(bitext_correct=686)),
        ("pos_train_added_18_correct_count", dict(added_correct=14)),
        ("boundary_pos_cal_sup12_conf_ge_070_count", dict(sup12_ge70_target=25, sup12_ge80_target=24)),
        ("boundary_pos_cal_sup12_conf_ge_080_count", dict(sup12_ge70_target=26, sup12_ge80_target=23)),
        ("boundary_neg_cal_pred_sup12_count", dict(neg_pred_sup12=10)),
    ):
        cand = compute_cal_guard_metrics_from_logits(_build_logits(**kwargs), surfaces)
        rep = evaluate_cal_guard_report(cand, base_metrics)
        assert rep["passed"] is False
        assert fail_name in rep["failed_checks"]

    # Esc34 max_sup12_mass <= 0.55 + tol and neg_cal float bounds + 3e-6 rounding tolerance.
    import copy

    cand_tol_ok = copy.deepcopy(cand_pass)
    cand_tol_ok["boundary_pos_cal"]["mean_max_prob"] = base_metrics["boundary_pos_cal"]["mean_max_prob"] + 0.015 + 2e-6
    cand_tol_ok["boundary_pos_cal_esc34"]["mean_max_prob"] = (
        base_metrics["boundary_pos_cal_esc34"]["mean_max_prob"] + 0.015 + 2e-6
    )
    cand_tol_ok["boundary_pos_cal_esc34"]["max_sup12_mass"] = 0.55 + 2e-6
    cand_tol_ok["boundary_neg_cal"]["max_sup12_mass"] = base_metrics["boundary_neg_cal"]["max_sup12_mass"] + 2e-6
    cand_tol_ok["boundary_neg_cal"]["max_single_sup12_prob"] = (
        base_metrics["boundary_neg_cal"]["max_single_sup12_prob"] + 2e-6
    )
    assert evaluate_cal_guard_report(cand_tol_ok, base_metrics)["passed"] is True

    for float_fail_field, mutator in (
        (
            "boundary_pos_cal_delta_mean_max_prob",
            lambda c: c["boundary_pos_cal"].__setitem__(
                "mean_max_prob", base_metrics["boundary_pos_cal"]["mean_max_prob"] + 0.015 + 5e-6
            ),
        ),
        (
            "boundary_pos_cal_esc34_delta_mean_max_prob",
            lambda c: c["boundary_pos_cal_esc34"].__setitem__(
                "mean_max_prob", base_metrics["boundary_pos_cal_esc34"]["mean_max_prob"] + 0.015 + 5e-6
            ),
        ),
        (
            "boundary_pos_cal_esc34_max_sup12_mass",
            lambda c: c["boundary_pos_cal_esc34"].__setitem__("max_sup12_mass", 0.55 + 5e-6),
        ),
        (
            "boundary_neg_cal_max_sup12_mass",
            lambda c: c["boundary_neg_cal"].__setitem__(
                "max_sup12_mass", base_metrics["boundary_neg_cal"]["max_sup12_mass"] + 5e-6
            ),
        ),
        (
            "boundary_neg_cal_max_single_sup12_prob",
            lambda c: c["boundary_neg_cal"].__setitem__(
                "max_single_sup12_prob", base_metrics["boundary_neg_cal"]["max_single_sup12_prob"] + 5e-6
            ),
        ),
    ):
        cand_bad = copy.deepcopy(cand_pass)
        mutator(cand_bad)
        rep_bad = evaluate_cal_guard_report(cand_bad, base_metrics)
        assert rep_bad["passed"] is False
        assert float_fail_field in rep_bad["failed_checks"]

    # Bounded drift scale-up formula for pos_cal correct > 68 (70/86 allows +0.025 cap).
    cand_70 = copy.deepcopy(cand_pass)
    cand_70["boundary_pos_cal"]["correct_count"] = 70
    cand_70["boundary_pos_cal"]["mean_max_prob"] = base_metrics["boundary_pos_cal"]["mean_max_prob"] + 0.022
    rep_70 = evaluate_cal_guard_report(cand_70, base_metrics)
    assert "boundary_pos_cal_delta_mean_max_prob" not in rep_70["failed_checks"]
    assert abs(rep_70["deltas"]["boundary_pos_cal_allowed_delta_mean_max_prob"] - 0.025) < 1e-12
    assert CAL_GUARD_FLOAT_TOLERANCE == 3e-6


def test_lr5e6_profile_contract_cli_and_post_fit_cal_guard_archive(monkeypatch, tmp_path):
    import hashlib
    import sys

    def _sha(p: Path) -> str:
        return hashlib.sha256(p.read_bytes()).hexdigest().lower()

    assert AUTHORIZED_FIT_PROFILES["lr5e6"]["lr"] == 5e-6
    plan_lr = _build_planned_execution_plan(
        profile_name="lr5e6",
        prep_records_dir=tmp_path / "run-records-fit2-orig-ret-channel-v4-prep",
        planned_fit_run_id="fit2-orig-ret-channel-lr5e6-v1",
        planned_future_paths={"archive_dir": "a", "records_dir": "r", "local_dir": "l"},
    )
    cli_str = " ".join(plan_lr["planned_cli"])
    assert "--profile lr5e6" in cli_str and "--lr 5e-6" in cli_str and "--run-authorized-fit" in cli_str
    assert "--run-option-a-fit" not in cli_str

    with pytest.raises(ValueError, match="lr=5e-6"):
        validate_profile_settings(
            profile="lr5e6", epochs=3, lr=2e-5, batch_size=32, seed=42, fit_mode="fit2_supcon_energy", enable_selective_rejector=False
        )

    repo_root = tmp_path / "repo"
    for rel in RELEVANT_SOURCE_PATHS:
        fp = repo_root / rel
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(f"# {rel}\n", encoding="utf-8")

    prep_dir = tmp_path / "run-records-fit2-orig-ret-channel-v4-prep"
    ds_dir = prep_dir / "datasets"
    ds_dir.mkdir(parents=True)
    split_manifest = ds_dir / "split_manifest.json"
    full_train = ds_dir / "full_train_split.jsonl"
    split_manifest.write_text('{"ok": true}\n', encoding="utf-8")
    full_train.write_text('{"sample_id": "x"}\n', encoding="utf-8")
    import shutil

    source_hashes = {rel: _sha(repo_root / rel) for rel in RELEVANT_SOURCE_PATHS}
    for rel in RELEVANT_SOURCE_PATHS:
        snap = prep_dir / "source_snapshot" / rel
        snap.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(repo_root / rel, snap)

    ds_hashes = {"boundary_split_manifest": _sha(split_manifest), "full_train_split": _sha(full_train)}
    new_hashes = {"split_manifest.json": _sha(split_manifest), "full_train_split.jsonl": _sha(full_train)}
    dummy_base_cal = {
        "boundary_pos_cal": {"count": 86, "correct_count": 68, "mean_max_prob": 0.68},
        "boundary_pos_cal_sup12": {"count": 48, "correct_count": 38, "conf_ge_070_count": 28, "conf_ge_080_count": 28},
        "boundary_pos_cal_esc34": {"count": 38, "correct_count": 30, "mean_max_prob": 0.67, "max_sup12_mass": 0.46},
        "bitext_cal": {"count": 690, "correct_count": 689},
        "boundary_neg_cal": {"count": 48, "pred_sup12_count": 9, "max_sup12_mass": 0.71, "max_single_sup12_prob": 0.55},
        "pos_train_added_18": {"count": 18, "correct_count": 8},
    }
    (prep_dir / "status.json").write_text(
        json.dumps({"status": "complete", "fits_executed": 0, "prep_archive": True}), encoding="utf-8"
    )
    (prep_dir / "prep_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "orig_fit2_return_contrast_prep.v4",
                "git_commit": "a" * 40,
                "source_hashes": source_hashes,
                "unchanged_original_recipe_parameters": UNCHANGED_ORIGINAL_RECIPE_PARAMETERS,
                "authorized_fit_profile": AUTHORIZED_FIT_PROFILES["lr5e6"],
                "execution_plan": AUTHORIZED_FIT_PROFILES["lr5e6"],
                "baseline_cal_reference": {
                    "baseline_weights_sha256": EXPECTED_FIT2_SHA256,
                    "baseline_calibration_manifest_sha256": "c" * 64,
                    "dataset_hashes": ds_hashes,
                    "metrics": dummy_base_cal,
                },
                "preflight": {
                    "extension_version": "orig_fit2_return_channel_contrast_v2",
                    "counts": {"extension_pos_train_added": 18},
                    "dataset_hashes": ds_hashes,
                    "new_input_file_hashes": new_hashes,
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
        lambda root: {"git_commit": "b" * 40, "source_hashes": source_hashes},
    )
    monkeypatch.setattr(
        "scripts.run_orig_fit2_return_contrast_fit.verify_git_commit_ancestor",
        lambda root, anc, desc="HEAD": "b" * 40,
    )

    # Profile mismatch against v4-prep (option_a requested vs lr5e6 prep) must fail closed.
    with pytest.raises(ValueError, match="mismatches locked prep authorized_fit_profile"):
        run_authorized_fit(
            repo_root=repo_root,
            prep_dir=prep_dir,
            run_id="fit2-orig-ret-channel-lr5e6-v1",
            profile="option_a",
            epochs=3,
            lr=2e-5,
            execute_fit=False,
            main_candidates_dir=candidates_dir,
            local_root_base=local_base,
            init_model_dir=init_dir,
            serving_dir=serving_dir,
        )

    # Validate-only succeeds for matching lr5e6 profile.
    val_out = run_authorized_fit(
        repo_root=repo_root,
        prep_dir=prep_dir,
        run_id="fit2-orig-ret-channel-lr5e6-v1",
        profile="lr5e6",
        epochs=3,
        lr=5e-6,
        execute_fit=False,
        main_candidates_dir=candidates_dir,
        local_root_base=local_base,
        init_model_dir=init_dir,
        serving_dir=serving_dir,
    )
    assert val_out["validated_only"] is True and val_out["authorized_fit_profile"] == "lr5e6"

    # CLI blocks missing --profile / --lr or --run-option-a-fit with lr5e6.
    monkeypatch.setattr(sys, "argv", ["prog", "--validate-only", "--lr", "5e-6"])
    with pytest.raises(SystemExit):
        fit_cli_main()
    monkeypatch.setattr(sys, "argv", ["prog", "--profile", "lr5e6", "--lr", "5e-6", "--run-option-a-fit"])
    with pytest.raises(ValueError, match="--run-option-a-fit requires --profile option_a"):
        fit_cli_main()

    # Mocked lr5e6 fit forwards lr=5e-6 and durably archives CAL_GUARD_REJECT without auto-retrain.
    seen_lrs = []

    def _fake_fit(**kwargs):
        seen_lrs.append(kwargs["lr"])
        cand_dir = kwargs["artifact_root"] / kwargs["output_subdir"]
        cand_dir.mkdir(parents=True)
        for fname in ("model.safetensors", "tokenizer.json", "tokenizer_config.json", "config.json"):
            (cand_dir / fname).write_bytes(fname.encode("utf-8"))
        (cand_dir / "calibration_manifest.json").write_text('{"valid": true}', encoding="utf-8")
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
    bad_cand_cal = dict(dummy_base_cal)
    bad_cand_cal["pos_train_added_18"] = {"count": 18, "correct_count": 16}
    bad_cand_cal["boundary_neg_cal"] = {"count": 48, "pred_sup12_count": 10, "max_sup12_mass": 0.75, "max_single_sup12_prob": 0.59}
    monkeypatch.setattr(
        "scripts.run_orig_fit2_return_contrast_fit.evaluate_cal_guard_metrics_for_model",
        lambda archive_dir, inputs_dir: bad_cand_cal,
    )

    fit_out = run_authorized_fit(
        repo_root=repo_root,
        prep_dir=prep_dir,
        run_id="fit2-orig-ret-channel-lr5e6-v1",
        profile="lr5e6",
        epochs=3,
        lr=5e-6,
        execute_fit=True,
        main_candidates_dir=candidates_dir,
        local_root_base=local_base,
        init_model_dir=init_dir,
        serving_dir=serving_dir,
    )
    assert seen_lrs == [5e-6]
    assert fit_out["fits_executed"] == 1
    assert fit_out["cal_guard_passed"] is False
    assert fit_out["cal_guard_status"] == "CAL_GUARD_REJECT_DO_NOT_PROMOTE"
    recs = Path(fit_out["records_dir"])
    assert (recs / "cal_guard_report.json").is_file()
    status_obj = json.loads((recs / "status.json").read_text(encoding="utf-8"))
    assert status_obj["status"] == "complete"
    assert status_obj["cal_guard_passed"] is False
    assert status_obj["cal_guard_status"] == "CAL_GUARD_REJECT_DO_NOT_PROMOTE"


@pytest.mark.real_model
def test_live_readonly_cal_guard_against_baseline_and_rejected_fit_v1():
    repo_root = Path(__file__).resolve().parents[2]
    ds_dir = repo_root / "artifacts/models/candidates/run-records-fit2-orig-ret-channel-v3-prep/datasets"
    fit_v1_dir = repo_root / "artifacts/models/candidates/fit2-orig-ret-channel-fit-v1"
    if not (FIT2_BASELINE_DIR.is_dir() and fit_v1_dir.is_dir() and ds_dir.is_dir()):
        pytest.skip("Archived Original Fit2 / fit-v1 / v3-prep datasets not present")

    base_metrics = evaluate_cal_guard_metrics_for_model(FIT2_BASELINE_DIR, ds_dir)
    base_self = evaluate_cal_guard_report(base_metrics, base_metrics)
    assert base_self["failed_checks"] == ["pos_train_added_18_correct_count"]
    assert base_metrics["boundary_pos_cal"]["correct_count"] == 68
    assert base_metrics["boundary_pos_cal_sup12"]["correct_count"] == 38
    assert base_metrics["boundary_pos_cal_sup12"]["conf_ge_070_count"] >= 26
    assert base_metrics["boundary_pos_cal_sup12"]["conf_ge_080_count"] >= 24
    assert base_metrics["boundary_neg_cal"]["pred_sup12_count"] == 9
    assert base_metrics["pos_train_added_18"]["correct_count"] == 8

    fit_v1_metrics = evaluate_cal_guard_metrics_for_model(fit_v1_dir, ds_dir)
    fit_v1_report = evaluate_cal_guard_report(fit_v1_metrics, base_metrics)
    assert fit_v1_report["passed"] is False
    assert fit_v1_report["recommended_status"] == "CAL_GUARD_REJECT_DO_NOT_PROMOTE"
    assert set(fit_v1_report["failed_checks"]) == {
        "boundary_pos_cal_delta_mean_max_prob",
        "boundary_pos_cal_esc34_delta_mean_max_prob",
        "boundary_pos_cal_esc34_max_sup12_mass",
        "boundary_neg_cal_pred_sup12_count",
        "boundary_neg_cal_max_sup12_mass",
        "boundary_neg_cal_max_single_sup12_prob",
    }


def test_zero_delta_control_splits_bit_identical_to_orig_stage2_and_blocks_optimizer(monkeypatch, tmp_path):
    repo_root = Path(__file__).resolve().parents[2]
    orig_stage2 = repo_root / ORIG_FIT2_STAGE2_REL
    if not orig_stage2.is_dir():
        pytest.skip("Archived faithful Fit2 stage2_inputs not present")

    class _StubTok:
        def encode(self, text, truncation=False, add_special_tokens=True):
            return [1] * len(text.split())

        def __call__(self, texts, truncation=False, max_length=64):
            return {"input_ids": [[1] * min(len(t.split()), max_length) for t in texts]}

    monkeypatch.setattr(
        "torch.optim.AdamW",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("Optimizer forbidden in zero-delta prep")),
    )
    monkeypatch.setattr(
        "pipeline.training.train_boundary_candidate.fit_temperature_on_calibration_logits",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("Calibrator forbidden in zero-delta prep")),
    )
    monkeypatch.setattr(
        "pipeline.training.train_boundary_candidate.run_fit_and_lock_candidate",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("Training forbidden in zero-delta prep")),
    )
    monkeypatch.setattr(
        "pipeline.training.train_boundary_candidate.AutoTokenizer.from_pretrained",
        lambda *a, **kw: _StubTok(),
    )

    dryrun_root = tmp_path / "control_dryrun"
    lock = prepare_and_lock_orig_fit2_zero_delta_control_splits(
        worktree_root=repo_root,
        data_repo_root=repo_root,
        init_model_dir=FIT2_BASELINE_DIR if FIT2_BASELINE_DIR.is_dir() else repo_root,
        artifact_root=dryrun_root,
    )
    assert lock["schema_version"] == "orig_fit2_zero_delta_control_lock.v1"
    assert lock["extension_version"] == "orig_fit2_zero_delta_control_v1"
    assert lock["delta_absent"] is True
    assert lock["counts"]["domain_pos_train"] == 181
    assert lock["counts"]["extension_pos_train_added"] == 0
    assert lock["counts"]["full_train_split_rows"] == 11320
    assert lock["counts"]["effective_train_total"] == 13000
    assert lock["token_truncation_audit_max_length_64"]["train_all"]["count"] == 11320

    ds_dir = dryrun_root / "datasets"
    assert not (ds_dir / "orig_fit2_return_contrast_extension.jsonl").exists()
    assert lock["new_input_file_hashes"] == lock["orig_fit2_stage2_reference_hashes"]
    assert set(lock["new_input_file_hashes"].keys()) == set(EXPECTED_ORIG_STAGE2_LOCKED_FILES)
    assert lock["baseline_vs_new_diff"]["changed_files"] == {}
    assert lock["baseline_vs_new_diff"]["exposure_delta"]["effective_train_total_delta"] == 0

    for fname in ("boundary_pos_train.jsonl", "full_train_split.jsonl"):
        rows = [json.loads(line) for line in (ds_dir / fname).read_text(encoding="utf-8").splitlines() if line.strip()]
        assert not any(str(r.get("sample_id", "")).startswith("orig_ret_ch_") for r in rows)

    preflight = run_orig_fit2_preflight(repo_root, tmp_path / "preflight_ctl", zero_delta_control=True)
    assert preflight["fits_executed"] == 0
    assert preflight["optimizer_invoked"] is False
    assert preflight["zero_delta_control"] is True
    assert preflight["delta_absent"] is True
    assert preflight["counts"]["extension_pos_train_added"] == 0


def test_cal_guard_control_mode_omits_only_learning_floor_and_freezes_attribution_breakdown():
    from pipeline.evaluation.classifier_acceptance_gate import ESCALATED_34_INTENTS

    n_pos_cal, n_sup, n_esc = 86, 48, 38
    assert n_sup + n_esc == n_pos_cal
    bx_intent = next(x for x in STANDARD_INTENTS_46 if x not in ("return_policy", "return_product_in_store"))
    other_esc_intent = next(
        x for x in sorted(ESCALATED_34_INTENTS) if x not in ("return_product_in_store", bx_intent)
    )

    surfaces = {
        "boundary_pos_cal": (
            [{"sample_id": f"sup_{i}", "intent": "return_policy"} for i in range(n_sup)]
            + [{"sample_id": f"esc_{i}", "intent": "return_product_in_store"} for i in range(n_esc)]
        ),
        "bitext_cal": [{"sample_id": f"bx_{i}", "intent": bx_intent} for i in range(690)],
        "boundary_neg_cal": [{"sample_id": f"neg_{i}", "intent": "unsupported_x"} for i in range(48)],
    }

    sup_idx = STANDARD_INTENTS_46.index("return_policy")
    esc_idx = STANDARD_INTENTS_46.index("return_product_in_store")
    bx_idx = STANDARD_INTENTS_46.index(bx_intent)
    other_esc_idx = STANDARD_INTENTS_46.index(other_esc_intent)
    assert other_esc_idx != esc_idx and sup_idx != esc_idx

    def _make_logits(esc_wrong_high_sup_conf: bool) -> dict[str, torch.Tensor]:
        pos_logits = torch.full((n_pos_cal, len(STANDARD_INTENTS_46)), -8.0, dtype=torch.float32)
        for i in range(n_sup):
            target = sup_idx if i < 38 else other_esc_idx
            pos_logits[i, target] = 1.1 if i < 38 else 0.5
        for i in range(n_esc):
            row = n_sup + i
            if i < 30:
                pos_logits[row, esc_idx] = 0.8
            elif esc_wrong_high_sup_conf:
                # Wrong ESC row predicting sup with inflated confidence -> spikes incorrect_mean_max_prob
                pos_logits[row, sup_idx] = 2.5
            else:
                pos_logits[row, other_esc_idx] = 0.1
                pos_logits[row, bx_idx] = 0.0
        bx_logits = torch.full((690, len(STANDARD_INTENTS_46)), -8.0, dtype=torch.float32)
        bx_logits[:, bx_idx] = 3.0
        neg_logits = torch.full((48, len(STANDARD_INTENTS_46)), -8.0, dtype=torch.float32)
        for i in range(9):
            neg_logits[i, sup_idx] = 0.2
        for i in range(9, 48):
            neg_logits[i, other_esc_idx] = 1.0
        return {
            "boundary_pos_cal": pos_logits,
            "bitext_cal": bx_logits,
            "boundary_neg_cal": neg_logits,
        }

    base_metrics = compute_cal_guard_metrics_from_logits(
        _make_logits(esc_wrong_high_sup_conf=False), surfaces, temperature=1.0, include_added_18=False
    )
    assert "pos_train_added_18" not in base_metrics
    assert {
        "schema_version",
        "surface_note",
        "boundary_pos_cal",
        "boundary_pos_cal_sup12",
        "boundary_pos_cal_esc34",
        "bitext_cal",
    }.issubset(base_metrics["attribution_breakdown"].keys())

    # Identical logits pass all 11 control checks without pos_train_added_18
    self_report = evaluate_cal_guard_report(base_metrics, base_metrics, cal_guard_mode="control")
    assert self_report["cal_guard_mode"] == "matched_zero_delta_control_11_checks"
    assert self_report["is_promotion_candidate"] is False
    assert self_report["passed"] is True
    assert self_report["recommended_status"] == "CONTROL_CAL_NO_REGRESSION_SCIENTIFIC_ONLY"
    assert "pos_train_added_18_correct_count" not in {c["name"] for c in self_report["checks"]}
    assert len(self_report["checks"]) == 11

    # Inflated confidence on WRONG ESC rows raises incorrect_mean_max_prob and overall mean_max_prob even at same 30/38 accuracy
    drift_metrics = compute_cal_guard_metrics_from_logits(
        _make_logits(esc_wrong_high_sup_conf=True), surfaces, temperature=1.0, include_added_18=False
    )
    esc_base_attr = base_metrics["attribution_breakdown"]["boundary_pos_cal_esc34"]
    esc_drift_attr = drift_metrics["attribution_breakdown"]["boundary_pos_cal_esc34"]
    assert esc_base_attr["correct_count"] == esc_drift_attr["correct_count"] == 30
    assert esc_base_attr["all_mean_max_prob"] == pytest.approx(
        base_metrics["boundary_pos_cal_esc34"]["mean_max_prob"],
        abs=1e-9,
    )
    assert esc_drift_attr["all_mean_max_prob"] == pytest.approx(
        drift_metrics["boundary_pos_cal_esc34"]["mean_max_prob"], abs=1e-9
    )
    assert esc_drift_attr["incorrect_mean_max_prob"] > esc_base_attr["incorrect_mean_max_prob"] + 0.3

    drift_report = evaluate_cal_guard_report(drift_metrics, base_metrics, cal_guard_mode="control")
    assert drift_report["passed"] is False
    assert drift_report["recommended_status"] == "CONTROL_CAL_DRIFT_OR_REGRESSION_DETECTED"
    assert "boundary_pos_cal_esc34_delta_mean_max_prob" in drift_report["failed_checks"]
    assert "boundary_pos_cal_esc34_max_sup12_mass" in drift_report["failed_checks"]
    assert drift_report["attribution_deltas"]["boundary_pos_cal_esc34"]["delta_incorrect_mean_max_prob"] > 0.3


def test_zero_delta_control_prep_and_fit_guards_reject_extension_and_wrong_profile(monkeypatch, tmp_path):
    import hashlib
    import sys

    def _sha(p: Path) -> str:
        return hashlib.sha256(p.read_bytes()).hexdigest().lower()

    ctl_plan = _build_planned_execution_plan(
        profile_name="option_a",
        prep_records_dir=tmp_path / "run-records-fit2-orig-zero-delta-control-v1-prep",
        planned_fit_run_id="fit2-orig-zero-delta-control-v1",
        planned_future_paths={"archive_dir": "a", "records_dir": "r", "local_dir": "l"},
        experiment_mode="zero_delta_control",
    )
    assert ctl_plan["experiment_mode"] == "matched_zero_delta_control"
    assert ctl_plan["is_promotion_candidate"] is False
    assert "--run-authorized-fit" in ctl_plan["planned_cli"]
    assert "--profile" in ctl_plan["planned_cli"]

    with pytest.raises(ValueError, match="requires profile_name='option_a'"):
        _build_planned_execution_plan(
            profile_name="lr5e6",
            prep_records_dir=tmp_path / "x",
            planned_fit_run_id="y",
            planned_future_paths={"archive_dir": "a", "records_dir": "r", "local_dir": "l"},
            experiment_mode="zero_delta_control",
        )

    repo_root = tmp_path / "repo"
    for rel in RELEVANT_SOURCE_PATHS:
        fp = repo_root / rel
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(f"# {rel}\n", encoding="utf-8")

    prep_dir = tmp_path / "run-records-fit2-orig-zero-delta-control-v1-prep"
    ds_dir = prep_dir / "datasets"
    ds_dir.mkdir(parents=True)
    ds_hashes = {}
    new_hashes = {}
    for fname in EXPECTED_ORIG_STAGE2_LOCKED_FILES:
        fp = ds_dir / fname
        fp.write_text('{"ok": true}\n' if fname.endswith(".json") else '{"sample_id": "x"}\n', encoding="utf-8")
        digest = _sha(fp)
        key = "boundary_split_manifest" if fname == "split_manifest.json" else fname[: -len(".jsonl")]
        ds_hashes[key] = digest
        new_hashes[fname] = digest
    assert not (ds_dir / "orig_fit2_return_contrast_extension.jsonl").exists()

    import shutil

    source_hashes = {rel: _sha(repo_root / rel) for rel in RELEVANT_SOURCE_PATHS}
    for rel in RELEVANT_SOURCE_PATHS:
        snap = prep_dir / "source_snapshot" / rel
        snap.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(repo_root / rel, snap)

    base_metrics = {
        "boundary_pos_cal": {"count": 86, "correct_count": 68, "mean_max_prob": 0.686},
        "boundary_pos_cal_sup12": {"count": 48, "correct_count": 38, "conf_ge_070_count": 28, "conf_ge_080_count": 26},
        "boundary_pos_cal_esc34": {"count": 38, "correct_count": 30, "mean_max_prob": 0.671, "max_sup12_mass": 0.48},
        "bitext_cal": {"count": 690, "correct_count": 689},
        "boundary_neg_cal": {"count": 48, "pred_sup12_count": 9, "max_sup12_mass": 0.72, "max_single_sup12_prob": 0.56},
        "attribution_breakdown": {},
    }
    (prep_dir / "status.json").write_text(
        json.dumps({"status": "complete", "fits_executed": 0, "prep_archive": True}), encoding="utf-8"
    )
    (prep_dir / "prep_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "orig_fit2_zero_delta_control_prep.v1",
                "experiment_mode": "matched_zero_delta_control",
                "is_promotion_candidate": False,
                "git_commit": "a" * 40,
                "source_hashes": source_hashes,
                "unchanged_original_recipe_parameters": UNCHANGED_ORIGINAL_RECIPE_PARAMETERS,
                "authorized_fit_profile": AUTHORIZED_FIT_PROFILES["option_a"],
                "execution_plan": ctl_plan,
                "baseline_cal_reference": {
                    "baseline_weights_sha256": EXPECTED_FIT2_SHA256,
                    "baseline_calibration_manifest_sha256": "c" * 64,
                    "dataset_hashes": ds_hashes,
                    "metrics": base_metrics,
                },
                "preflight": {
                    "extension_version": "orig_fit2_zero_delta_control_v1",
                    "delta_absent": True,
                    "counts": {
                        "domain_pos_train": 181,
                        "extension_pos_train_added": 0,
                        "full_train_split_rows": 11320,
                        "effective_train_total": 13000,
                    },
                    "dataset_hashes": ds_hashes,
                    "orig_fit2_stage2_reference_hashes": dict(new_hashes),
                    "new_input_file_hashes": dict(new_hashes),
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
        lambda root: {"git_commit": "b" * 40, "source_hashes": source_hashes},
    )
    monkeypatch.setattr(
        "scripts.run_orig_fit2_return_contrast_fit.verify_git_commit_ancestor",
        lambda root, anc, desc="HEAD": "b" * 40,
    )

    with pytest.raises(ValueError, match="mismatches locked prep authorized_fit_profile"):
        run_authorized_fit(
            repo_root=repo_root,
            prep_dir=prep_dir,
            run_id="fit2-orig-zero-delta-control-v1",
            profile="lr5e6",
            epochs=3,
            lr=5e-6,
            execute_fit=False,
            main_candidates_dir=candidates_dir,
            local_root_base=local_base,
            init_model_dir=init_dir,
            serving_dir=serving_dir,
        )

    val_out = run_authorized_fit(
        repo_root=repo_root,
        prep_dir=prep_dir,
        run_id="fit2-orig-zero-delta-control-v1",
        profile="option_a",
        epochs=3,
        lr=2e-5,
        execute_fit=False,
        main_candidates_dir=candidates_dir,
        local_root_base=local_base,
        init_model_dir=init_dir,
        serving_dir=serving_dir,
    )
    assert val_out["validated_only"] is True
    assert val_out["prep_schema_version"] == "orig_fit2_zero_delta_control_prep.v1"

    def _fake_fit(**kwargs):
        cand_dir = kwargs["artifact_root"] / kwargs["output_subdir"]
        cand_dir.mkdir(parents=True)
        for fname in ("model.safetensors", "tokenizer.json", "tokenizer_config.json", "config.json"):
            (cand_dir / fname).write_bytes(fname.encode("utf-8"))
        (cand_dir / "calibration_manifest.json").write_text('{"valid": true}', encoding="utf-8")
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
    seen_include_added = []

    def _fake_eval(model_dir, inputs_dir, *, include_added_18=True):
        seen_include_added.append(include_added_18)
        return dict(base_metrics)

    monkeypatch.setattr("scripts.run_orig_fit2_return_contrast_fit.evaluate_cal_guard_metrics_for_model", _fake_eval)

    fit_out = run_authorized_fit(
        repo_root=repo_root,
        prep_dir=prep_dir,
        run_id="fit2-orig-zero-delta-control-v1",
        profile="option_a",
        epochs=3,
        lr=2e-5,
        execute_fit=True,
        main_candidates_dir=candidates_dir,
        local_root_base=local_base,
        init_model_dir=init_dir,
        serving_dir=serving_dir,
    )
    assert seen_include_added == [False]
    assert fit_out["fits_executed"] == 1
    assert fit_out["cal_guard_passed"] is True
    assert fit_out["cal_guard_status"] == "CONTROL_CAL_NO_REGRESSION_SCIENTIFIC_ONLY"
    report = json.loads((Path(fit_out["records_dir"]) / "cal_guard_report.json").read_text(encoding="utf-8"))
    assert report["cal_guard_mode"] == "matched_zero_delta_control_11_checks"
    assert "pos_train_added_18_correct_count" not in {c["name"] for c in report["checks"]}

    # Leaked extension file in datasets/ fails closed against sidecar inventory + control guard
    (ds_dir / "orig_fit2_return_contrast_extension.jsonl").write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Prep bundle file set mismatch"):
        run_authorized_fit(
            repo_root=repo_root,
            prep_dir=prep_dir,
            run_id="fit2-orig-zero-delta-control-v1-bad",
            profile="option_a",
            epochs=3,
            lr=2e-5,
            execute_fit=False,
            main_candidates_dir=candidates_dir,
            local_root_base=local_base,
            init_model_dir=init_dir,
            serving_dir=serving_dir,
        )


def test_teacher_kl_identity_student_equals_teacher_and_zero_mask_safe():
    torch.manual_seed(7)
    student = torch.nn.Sequential(torch.nn.Embedding(32, 8), torch.nn.Linear(8, len(STANDARD_INTENTS_46)))
    teacher = torch.nn.Sequential(torch.nn.Embedding(32, 8), torch.nn.Linear(8, len(STANDARD_INTENTS_46)))
    teacher.load_state_dict(student.state_dict())
    student.eval()
    teacher.eval()
    for p in teacher.parameters():
        p.requires_grad_(False)

    tokens = torch.randint(0, 32, (6,))
    with torch.no_grad():
        t_logits = teacher(tokens)
    s_logits = student(tokens)

    loss_all, cnt_all = compute_masked_teacher_kl_loss(
        s_logits, t_logits, torch.ones(6, dtype=torch.long), teacher_temperature=1.0
    )
    assert cnt_all == 6
    assert float(loss_all.item()) < 1e-7

    loss_zero, cnt_zero = compute_masked_teacher_kl_loss(
        s_logits, t_logits, torch.zeros(6, dtype=torch.long), teacher_temperature=1.0
    )
    assert cnt_zero == 0
    assert torch.isfinite(loss_zero)
    assert float(loss_zero.item()) == 0.0


def test_teacher_kl_teacher_immutability_and_student_gradient_update(tmp_path: Path):
    import copy
    import hashlib
    from pipeline.training.train_boundary_candidate import _load_and_verify_frozen_teacher

    torch.manual_seed(11)
    student = torch.nn.Linear(8, len(STANDARD_INTENTS_46))
    teacher = copy.deepcopy(student)
    teacher.eval()
    for p in teacher.parameters():
        p.requires_grad_(False)
    with torch.no_grad():
        student.weight[0].add_(0.5)

    teacher_snap = {k: v.detach().clone() for k, v in teacher.state_dict().items()}
    student_snap = {k: v.detach().clone() for k, v in student.state_dict().items()}
    opt = torch.optim.AdamW(student.parameters(), lr=1e-2)

    x = torch.randn(4, 8)
    mask = torch.tensor([1, 1, 0, 1], dtype=torch.long)
    opt.zero_grad()
    with torch.no_grad():
        t_logits = teacher(x)
    s_logits = student(x)
    l_tkl, active = compute_masked_teacher_kl_loss(s_logits, t_logits, mask, teacher_temperature=1.0)
    assert active == 3 and float(l_tkl.item()) > 1e-4
    l_tkl.backward()
    opt.step()

    assert teacher.training is False
    for p in teacher.parameters():
        assert p.grad is None
        assert p.requires_grad is False
    for k, orig_t in teacher_snap.items():
        assert torch.equal(teacher.state_dict()[k], orig_t)
    assert not torch.equal(student.weight, student_snap["weight"])

    t_dir = tmp_path / "teacher"
    s_dir = tmp_path / "student"
    t_dir.mkdir()
    s_dir.mkdir()
    (t_dir / "model.safetensors").write_bytes(b"fake-weights")
    (s_dir / "tokenizer.json").write_text('{"tok": 1}\n', encoding="utf-8")
    (t_dir / "tokenizer.json").write_text('{"tok": 2}\n', encoding="utf-8")
    (t_dir / "config.json").write_text(
        json.dumps({"id2label": {str(i): lbl for i, lbl in enumerate(STANDARD_INTENTS_46)}}), encoding="utf-8"
    )
    wrong_sha = hashlib.sha256(b"other").hexdigest()
    with pytest.raises(ValueError, match="Teacher weights SHA-256 mismatch"):
        _load_and_verify_frozen_teacher(
            teacher_dir=t_dir, init_model_dir=s_dir, expected_teacher_weights_sha256=wrong_sha, device=torch.device("cpu")
        )
    actual_sha = hashlib.sha256(b"fake-weights").hexdigest()
    with pytest.raises(ValueError, match="tokenizer.json SHA-256 differs"):
        _load_and_verify_frozen_teacher(
            teacher_dir=t_dir, init_model_dir=s_dir, expected_teacher_weights_sha256=actual_sha, device=torch.device("cpu")
        )


def test_teacher_kl_provenance_mask_exact_13000_anchor_and_80_excluded():
    from apps.core_backend.intent.routing import ESCALATED_34_INTENTS, SUPPORTED_12_INTENTS

    sup_lbl = sorted(SUPPORTED_12_INTENTS)[0]
    esc_lbl = sorted(ESCALATED_34_INTENTS)[0]
    pos_canon = [{"sample_id": f"canon_s_{i}", "intent": sup_lbl} for i in range(133)] + [
        {"sample_id": f"canon_e_{i}", "intent": esc_lbl} for i in range(48)
    ]
    ext_rows = [{"sample_id": f"orig_ret_ch_s_{i}", "intent": sup_lbl} for i in range(10)] + [
        {"sample_id": f"orig_ret_ch_e_{i}", "intent": esc_lbl} for i in range(8)
    ]
    pos_train = pos_canon + ext_rows
    bitext_rows = [{"sample_id": f"bx_{i}", "intent": sup_lbl} for i in range(11040)]
    neg_train = [{"sample_id": f"neg_{i}", "intent": "unsupported_x"} for i in range(99)]
    neg_repeats = [12] * len(neg_train)

    mask, summary = build_teacher_anchor_mask(
        pos_train=pos_train,
        bitext_rows=bitext_rows,
        neg_train=neg_train,
        neg_repeat_counts=neg_repeats,
        extension_rows=ext_rows,
    )
    assert len(mask) == 13080
    assert sum(mask) == 13000
    assert len(mask) - sum(mask) == 80
    assert summary["anchor_effective_total"] == 13000
    assert summary["excluded_effective_total"] == 80
    assert summary["extension_raw_count"] == 18

    with pytest.raises(ValueError, match="empty"):
        build_teacher_anchor_mask(
            pos_train=pos_train, bitext_rows=bitext_rows, neg_train=neg_train, neg_repeat_counts=neg_repeats, extension_rows=[]
        )
    with pytest.raises(ValueError, match="leaked into bitext"):
        build_teacher_anchor_mask(
            pos_train=pos_train,
            bitext_rows=bitext_rows + [ext_rows[0]],
            neg_train=neg_train,
            neg_repeat_counts=neg_repeats,
            extension_rows=ext_rows,
        )
    with pytest.raises(ValueError, match="missing from pos_train"):
        build_teacher_anchor_mask(
            pos_train=pos_canon,
            bitext_rows=bitext_rows,
            neg_train=neg_train,
            neg_repeat_counts=neg_repeats,
            extension_rows=ext_rows,
        )


def test_teacher_kl_profile_isolation_and_fail_closed_cli_guards(monkeypatch):
    from scripts.run_orig_fit2_return_contrast_prep import DEFAULT_PREP_PROFILE

    assert DEFAULT_PREP_PROFILE == "lr5e6"
    assert "teacher_kl_weight" not in AUTHORIZED_FIT_PROFILES["option_a"]
    assert "teacher_kl_weight" not in AUTHORIZED_FIT_PROFILES["lr5e6"]

    tkl = AUTHORIZED_FIT_PROFILES["option_a_teacher_kl"]
    assert tkl["lr"] == 2e-5
    assert tkl["epochs"] == 3
    assert tkl["batch_size"] == 32
    assert tkl["seed"] == 42
    assert tkl["fit_mode"] == "fit2_supcon_energy"
    assert tkl["min_temperature"] == 1.0
    assert tkl["enable_selective_rejector"] is False
    assert tkl["init_weights_sha256"] == EXPECTED_FIT2_SHA256
    assert tkl["teacher_weights_sha256"] == EXPECTED_FIT2_SHA256
    assert tkl["teacher_kl_weight"] == 1.0
    assert tkl["teacher_temperature"] == 1.0

    for bad_kwargs in (
        {"teacher_kl_weight": None, "teacher_temperature": 1.0, "teacher_weights_sha256": EXPECTED_FIT2_SHA256},
        {"teacher_kl_weight": 0.5, "teacher_temperature": 1.0, "teacher_weights_sha256": EXPECTED_FIT2_SHA256},
        {"teacher_kl_weight": 1.0, "teacher_temperature": 2.0, "teacher_weights_sha256": EXPECTED_FIT2_SHA256},
        {"teacher_kl_weight": 1.0, "teacher_temperature": 1.0, "teacher_weights_sha256": "0" * 64},
    ):
        with pytest.raises(ValueError, match="option_a_teacher_kl requires"):
            validate_profile_settings(
                profile="option_a_teacher_kl",
                epochs=3,
                lr=2e-5,
                batch_size=32,
                seed=42,
                fit_mode="fit2_supcon_energy",
                enable_selective_rejector=False,
                **bad_kwargs,
            )

    with pytest.raises(ValueError, match="option_a forbids"):
        validate_profile_settings(
            profile="option_a",
            epochs=3,
            lr=2e-5,
            batch_size=32,
            seed=42,
            fit_mode="fit2_supcon_energy",
            enable_selective_rejector=False,
            teacher_kl_weight=1.0,
        )
    with pytest.raises(ValueError, match="lr5e6 forbids"):
        validate_profile_settings(
            profile="lr5e6",
            epochs=3,
            lr=5e-6,
            batch_size=32,
            seed=42,
            fit_mode="fit2_supcon_energy",
            enable_selective_rejector=False,
            teacher_weights_sha256=EXPECTED_FIT2_SHA256,
        )

    monkeypatch.setattr(
        "sys.argv",
        [
            "run_orig_fit2_return_contrast_fit.py",
            "--profile",
            "option_a_teacher_kl",
            "--lr",
            "2e-5",
            "--validate-only",
        ],
    )
    with pytest.raises(ValueError, match="option_a_teacher_kl requires"):
        fit_cli_main()


def test_teacher_kl_prep_plan_and_runner_forwarding_closure(tmp_path: Path, monkeypatch):
    import hashlib

    def _sha(p: Path) -> str:
        return hashlib.sha256(p.read_bytes()).hexdigest().lower()

    repo_root = Path(__file__).resolve().parents[2]
    prep_dir = tmp_path / "run-records-fit2-orig-teacher-kl-v1-prep"
    ds_dir = prep_dir / "datasets"
    ds_dir.mkdir(parents=True)

    plan = _build_planned_execution_plan(
        profile_name="option_a_teacher_kl",
        prep_records_dir=prep_dir,
        planned_fit_run_id="fit2-orig-teacher-kl-v1",
        planned_future_paths={"archive_dir": str(tmp_path / "arch")},
        experiment_mode="return_contrast",
    )
    assert plan["is_promotion_candidate"] is True
    assert "--teacher-kl-weight" in plan["planned_cli"]
    assert "--teacher-weights-sha256" in plan["planned_cli"]
    assert EXPECTED_FIT2_SHA256 in plan["planned_cli"]
    assert plan["planned_cli"][-1] == "--run-authorized-fit"

    ds_hashes: dict[str, str] = {}
    new_hashes: dict[str, str] = {}
    for fname in (*EXPECTED_ORIG_STAGE2_LOCKED_FILES, "orig_fit2_return_contrast_extension.jsonl"):
        fp = ds_dir / fname
        fp.write_text('{"ok": true}\n' if fname.endswith(".json") else '{"sample_id": "x"}\n', encoding="utf-8")
        digest = _sha(fp)
        if fname == "split_manifest.json":
            ds_hashes["boundary_split_manifest"] = digest
        elif fname == "orig_fit2_return_contrast_extension.jsonl":
            ds_hashes["orig_fit2_return_contrast_extension"] = digest
        else:
            ds_hashes[fname[: -len(".jsonl")]] = digest
        new_hashes[fname] = digest

    import shutil

    source_hashes = {rel: _sha(repo_root / rel) for rel in RELEVANT_SOURCE_PATHS}
    for rel in RELEVANT_SOURCE_PATHS:
        snap = prep_dir / "source_snapshot" / rel
        snap.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(repo_root / rel, snap)

    base_metrics = {
        "boundary_pos_cal": {"count": 86, "correct_count": 68, "mean_max_prob": 0.686},
        "boundary_pos_cal_sup12": {"count": 48, "correct_count": 38, "conf_ge_070_count": 28, "conf_ge_080_count": 26},
        "boundary_pos_cal_esc34": {"count": 38, "correct_count": 30, "mean_max_prob": 0.671, "max_sup12_mass": 0.48},
        "bitext_cal": {"count": 690, "correct_count": 689},
        "boundary_neg_cal": {"count": 48, "pred_sup12_count": 9, "max_sup12_mass": 0.72, "max_single_sup12_prob": 0.56},
        "pos_train_added_18": {"count": 18, "correct_count": 18},
        "attribution_breakdown": {},
    }
    tkl_anchor_cfg = {
        "enabled": True,
        "teacher_weights_sha256": EXPECTED_FIT2_SHA256,
        "teacher_kl_weight": 1.0,
        "teacher_temperature": 1.0,
        "anchor_effective_count": 13000,
        "excluded_effective_count": 80,
    }
    (prep_dir / "status.json").write_text(
        json.dumps({"status": "complete", "fits_executed": 0, "prep_archive": True}), encoding="utf-8"
    )
    (prep_dir / "prep_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "orig_fit2_return_contrast_prep.v4",
                "experiment_mode": "return_contrast",
                "is_promotion_candidate": True,
                "git_commit": "a" * 40,
                "source_hashes": source_hashes,
                "unchanged_original_recipe_parameters": UNCHANGED_ORIGINAL_RECIPE_PARAMETERS,
                "authorized_fit_profile": AUTHORIZED_FIT_PROFILES["option_a_teacher_kl"],
                "execution_plan": plan,
                "teacher_anchor_config": tkl_anchor_cfg,
                "baseline_cal_reference": {
                    "baseline_weights_sha256": EXPECTED_FIT2_SHA256,
                    "baseline_calibration_manifest_sha256": "c" * 64,
                    "dataset_hashes": ds_hashes,
                    "metrics": base_metrics,
                },
                "preflight": {
                    "extension_version": "orig_fit2_return_channel_contrast_v2",
                    "counts": {"extension_pos_train_added": 18},
                    "dataset_hashes": ds_hashes,
                    "new_input_file_hashes": new_hashes,
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
    (init_dir / "model.safetensors").write_bytes(b"fit2")
    (serving_dir / "model.safetensors").write_bytes(b"serving")

    monkeypatch.setattr(
        "scripts.run_orig_fit2_return_contrast_fit._sha256_lower",
        lambda p: (
            EXPECTED_SERVING_SHA256
            if p == serving_dir / "model.safetensors"
            else (EXPECTED_FIT2_SHA256 if p == init_dir / "model.safetensors" else _sha(p))
        ),
    )
    monkeypatch.setattr(
        "scripts.run_orig_fit2_return_contrast_fit.verify_fit2_starting_checkpoint",
        lambda p: {"weights_sha256": EXPECTED_FIT2_SHA256, "temperature": 1.0, "rejector_enabled": False, "num_labels": 46},
    )
    monkeypatch.setattr(
        "scripts.run_orig_fit2_return_contrast_fit.verify_orig_relevant_source_provenance",
        lambda root: {"git_commit": "b" * 40, "source_hashes": source_hashes},
    )
    monkeypatch.setattr(
        "scripts.run_orig_fit2_return_contrast_fit.verify_git_commit_ancestor",
        lambda root, anc, desc="HEAD": "b" * 40,
    )

    val_res = run_authorized_fit(
        repo_root=repo_root,
        prep_dir=prep_dir,
        run_id="fit2-orig-teacher-kl-v1",
        profile="option_a_teacher_kl",
        epochs=3,
        lr=2e-5,
        teacher_kl_weight=1.0,
        teacher_temperature=1.0,
        teacher_weights_sha256=EXPECTED_FIT2_SHA256,
        execute_fit=False,
        main_candidates_dir=candidates_dir,
        local_root_base=local_base,
        init_model_dir=init_dir,
        serving_dir=serving_dir,
    )
    assert val_res["validated_only"] is True
    assert val_res["fits_executed"] == 0
    assert val_res["teacher_anchor_config"]["teacher_kl_weight"] == 1.0

    captured_trainer_kwargs: dict[str, object] = {}

    def _fake_tkl_fit(**kwargs):
        captured_trainer_kwargs.update(kwargs)
        cand_dir = kwargs["artifact_root"] / kwargs["output_subdir"]
        cand_dir.mkdir(parents=True)
        for fname in ("model.safetensors", "tokenizer.json", "tokenizer_config.json", "config.json"):
            (cand_dir / fname).write_bytes(fname.encode("utf-8"))
        (cand_dir / "calibration_manifest.json").write_text('{"valid": true}', encoding="utf-8")
        (cand_dir / "candidate_provenance_manifest.json").write_text(
            json.dumps(
                {
                    "provenance_status": "verified",
                    "training_lineage": {
                        "teacher_kl_enabled": True,
                        "teacher_weights_sha256": kwargs["expected_teacher_weights_sha256"],
                        "teacher_kl_weight": kwargs["teacher_kl_weight"],
                        "teacher_temperature": kwargs["teacher_temperature"],
                    },
                }
            ),
            encoding="utf-8",
        )
        return {"fit_mode": "fit2_supcon_energy", "temperature": 1.0}

    monkeypatch.setattr("scripts.run_orig_fit2_return_contrast_fit.run_fit_and_lock_candidate", _fake_tkl_fit)
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
    monkeypatch.setattr(
        "scripts.run_orig_fit2_return_contrast_fit.evaluate_cal_guard_metrics_for_model",
        lambda d, inp: dict(base_metrics),
    )

    fit_res = run_authorized_fit(
        repo_root=repo_root,
        prep_dir=prep_dir,
        run_id="fit2-orig-teacher-kl-v1",
        profile="option_a_teacher_kl",
        epochs=3,
        lr=2e-5,
        teacher_kl_weight=1.0,
        teacher_temperature=1.0,
        teacher_weights_sha256=EXPECTED_FIT2_SHA256,
        execute_fit=True,
        main_candidates_dir=candidates_dir,
        local_root_base=local_base,
        init_model_dir=init_dir,
        serving_dir=serving_dir,
    )
    assert fit_res["fits_executed"] == 1
    assert captured_trainer_kwargs["teacher_kl_weight"] == 1.0
    assert captured_trainer_kwargs["teacher_temperature"] == 1.0
    assert captured_trainer_kwargs["expected_teacher_weights_sha256"] == EXPECTED_FIT2_SHA256
    assert captured_trainer_kwargs["teacher_model_dir"] == init_dir
    run_cfg = json.loads((Path(fit_res["records_dir"]) / "run_config.json").read_text(encoding="utf-8"))
    assert run_cfg["teacher_anchor_config"]["teacher_kl_weight"] == 1.0
    cal_report = json.loads((Path(fit_res["records_dir"]) / "cal_guard_report.json").read_text(encoding="utf-8"))
    assert cal_report["cal_guard_mode"] == "candidate_12_checks"
    assert fit_res["cal_guard_passed"] is True


def _make_synthetic_dropout_classifier(seed: int = 13):
    from types import SimpleNamespace

    class _ToyClassifier(torch.nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.emb = torch.nn.Embedding(32, 16)
            self.drop_outer = torch.nn.Dropout(0.35)
            self.proj = torch.nn.Sequential(torch.nn.Linear(16, 16), torch.nn.Dropout(0.35), torch.nn.GELU())
            self.head = torch.nn.Linear(16, len(STANDARD_INTENTS_46))

        def forward(self, input_ids, attention_mask=None, output_hidden_states: bool = False):
            h = self.drop_outer(self.emb(input_ids).mean(dim=1))
            h = self.proj(h)
            logits = self.head(h)
            if output_hidden_states:
                return SimpleNamespace(logits=logits, hidden_states=(h.unsqueeze(1),))
            return SimpleNamespace(logits=logits)

    torch.manual_seed(seed)
    return _ToyClassifier()


def test_deterministic_kl_init_identity_zero_and_zero_anchor_grad_vs_stochastic_dropout():
    import copy
    from pipeline.training.train_boundary_candidate import _forward_student_logits_eval_mode

    student = _make_synthetic_dropout_classifier(seed=17)
    teacher = copy.deepcopy(student)
    student.train()
    teacher.eval()
    for p in teacher.parameters():
        p.requires_grad_(False)

    input_ids = torch.randint(0, 32, (8, 5))
    attn = torch.ones_like(input_ids)
    mask = torch.ones(8, dtype=torch.long)
    with torch.no_grad():
        t_logits = teacher(input_ids=input_ids, attention_mask=attn).logits

    # Deterministic eval-mode student forward with autograd enabled: KL ~ 0 and grad ~ 0
    student.zero_grad()
    det_logits = _forward_student_logits_eval_mode(student, input_ids, attn)
    det_loss, det_cnt = compute_masked_teacher_kl_loss(det_logits, t_logits, mask, teacher_temperature=1.0)
    assert det_cnt == 8
    assert float(det_loss.item()) < 1e-7
    det_loss.backward()
    det_grad_norm = torch.sqrt(
        sum((p.grad.detach().pow(2).sum() for p in student.parameters() if p.grad is not None), torch.tensor(0.0))
    )
    assert float(det_grad_norm.item()) < 1e-6

    # Stochastic train-mode counterexample: dropout noise induces artificial non-zero KL & gradient
    torch.manual_seed(99)
    student.zero_grad()
    stoch_logits = student(input_ids=input_ids, attention_mask=attn).logits
    stoch_loss, _ = compute_masked_teacher_kl_loss(stoch_logits, t_logits, mask, teacher_temperature=1.0)
    assert float(stoch_loss.item()) > 1e-4
    stoch_loss.backward()
    stoch_grad_norm = torch.sqrt(
        sum((p.grad.detach().pow(2).sum() for p in student.parameters() if p.grad is not None), torch.tensor(0.0))
    )
    assert float(stoch_grad_norm.item()) > 1e-4


def test_deterministic_kl_perturbed_student_positive_and_gradient_toward_teacher():
    import copy
    from pipeline.training.train_boundary_candidate import _forward_student_logits_eval_mode

    teacher = _make_synthetic_dropout_classifier(seed=23)
    student = copy.deepcopy(teacher)
    teacher.eval()
    for p in teacher.parameters():
        p.requires_grad_(False)
    student.train()
    with torch.no_grad():
        student.head.weight[0].add_(0.4)
        student.head.weight[1].sub_(0.3)

    input_ids = torch.randint(0, 32, (6, 5))
    attn = torch.ones_like(input_ids)
    mask = torch.tensor([1, 1, 0, 1, 1, 0], dtype=torch.long)
    with torch.no_grad():
        t_logits = teacher(input_ids=input_ids, attention_mask=attn).logits

    det_1 = _forward_student_logits_eval_mode(student, input_ids, attn)
    loss_1, cnt_1 = compute_masked_teacher_kl_loss(det_1, t_logits, mask, teacher_temperature=1.0)
    det_2 = _forward_student_logits_eval_mode(student, input_ids, attn)
    loss_2, _ = compute_masked_teacher_kl_loss(det_2, t_logits, mask, teacher_temperature=1.0)
    assert cnt_1 == 4
    assert float(loss_1.item()) > 1e-4
    assert float((loss_1.detach() - loss_2.detach()).abs().item()) == 0.0

    student.zero_grad()
    loss_1.backward()
    # Autograd gradient points away from teacher ((theta_s - theta_t) . grad > 0) without optimizer updates
    directional_alignment = sum(
        float(((p.detach() - pt.detach()) * p.grad.detach()).sum().item())
        for p, pt in zip(student.parameters(), teacher.parameters())
        if p.grad is not None
    )
    assert directional_alignment > 0.0


def test_deterministic_kl_mask_all_added_empty_zero_and_canonical_exclusion():
    import copy
    from apps.core_backend.intent.routing import ESCALATED_34_INTENTS, SUPPORTED_12_INTENTS
    from pipeline.training.train_boundary_candidate import _forward_student_logits_eval_mode

    teacher = _make_synthetic_dropout_classifier(seed=31)
    student = copy.deepcopy(teacher)
    teacher.eval()
    student.train()

    input_ids = torch.randint(0, 32, (4, 5))
    attn = torch.ones_like(input_ids)
    empty_mask = torch.zeros(4, dtype=torch.long)
    with torch.no_grad():
        t_logits = teacher(input_ids=input_ids, attention_mask=attn).logits

    det_logits = _forward_student_logits_eval_mode(student, input_ids, attn)
    loss_empty, cnt_empty = compute_masked_teacher_kl_loss(det_logits, t_logits, empty_mask, teacher_temperature=1.0)
    assert cnt_empty == 0
    assert torch.isfinite(loss_empty)
    assert float(loss_empty.item()) == 0.0
    assert loss_empty.requires_grad is False

    sup_lbl = sorted(SUPPORTED_12_INTENTS)[0]
    esc_lbl = sorted(ESCALATED_34_INTENTS)[0]
    pos_canon = [{"sample_id": f"c_s_{i}", "intent": sup_lbl} for i in range(133)] + [
        {"sample_id": f"c_e_{i}", "intent": esc_lbl} for i in range(48)
    ]
    ext_rows = [{"sample_id": f"orig_ret_ch_s_{i}", "intent": sup_lbl} for i in range(10)] + [
        {"sample_id": f"orig_ret_ch_e_{i}", "intent": esc_lbl} for i in range(8)
    ]
    mask, summary = build_teacher_anchor_mask(
        pos_train=pos_canon + ext_rows,
        bitext_rows=[{"sample_id": f"bx_{i}", "intent": sup_lbl} for i in range(11040)],
        neg_train=[{"sample_id": f"neg_{i}", "intent": "unsupported_x"} for i in range(99)],
        neg_repeat_counts=[12] * 99,
        extension_rows=ext_rows,
    )
    assert summary["anchor_effective_total"] == 13000 and sum(mask) == 13000
    assert summary["excluded_effective_total"] == 80 and (len(mask) - sum(mask)) == 80


def test_deterministic_kl_base_forward_rng_modes_unchanged_and_exception_restore():
    import copy
    import random as py_random
    import numpy as np
    from pipeline.training.train_boundary_candidate import _forward_student_logits_eval_mode

    teacher = _make_synthetic_dropout_classifier(seed=41)
    student = copy.deepcopy(teacher)
    teacher.eval()
    for p in teacher.parameters():
        p.requires_grad_(False)

    # Set non-uniform nested module .training flags and confirm exact restore on normal call AND exception
    student.train()
    student.drop_outer.eval()
    student.proj[1].train()
    expected_flags = {name: mod.training for name, mod in student.named_modules()}

    input_ids = torch.randint(0, 32, (4, 5))
    attn = torch.ones_like(input_ids)
    _ = _forward_student_logits_eval_mode(student, input_ids, attn)
    assert {name: mod.training for name, mod in student.named_modules()} == expected_flags

    orig_head_forward = student.head.forward

    def _boom(*args, **kwargs):
        raise RuntimeError("injected forward failure")

    student.head.forward = _boom  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="injected forward failure"):
        _ = _forward_student_logits_eval_mode(student, input_ids, attn)
    student.head.forward = orig_head_forward  # type: ignore[method-assign]
    assert {name: mod.training for name, mod in student.named_modules()} == expected_flags

    # RNG preservation & base stochastic forward identity
    student.train()
    with torch.no_grad():
        student.head.weight[0].add_(0.2)
    mask = torch.ones(4, dtype=torch.long)

    torch.manual_seed(1234)
    ref_out_1 = student(input_ids=input_ids, attention_mask=attn, output_hidden_states=True).logits
    ref_out_2 = student(input_ids=input_ids, attention_mask=attn, output_hidden_states=True).logits

    torch.manual_seed(1234)
    np.random.seed(1234)
    py_random.seed(1234)
    base_out_1 = student(input_ids=input_ids, attention_mask=attn, output_hidden_states=True).logits
    cpu_rng_before = torch.get_rng_state()
    cuda_rng_before = torch.cuda.get_rng_state() if torch.cuda.is_available() else None
    np_rng_before = repr(np.random.get_state())
    py_rng_before = py_random.getstate()

    with torch.no_grad():
        t_logits = teacher(input_ids=input_ids, attention_mask=attn).logits
    det_logits = _forward_student_logits_eval_mode(student, input_ids, attn)
    l_tkl, _ = compute_masked_teacher_kl_loss(det_logits, t_logits, mask, teacher_temperature=1.0)
    l_tkl.backward()

    assert torch.equal(torch.get_rng_state(), cpu_rng_before)
    if cuda_rng_before is not None:
        assert torch.equal(torch.cuda.get_rng_state(), cuda_rng_before)
    assert repr(np.random.get_state()) == np_rng_before
    assert py_random.getstate() == py_rng_before

    base_out_2 = student(input_ids=input_ids, attention_mask=attn, output_hidden_states=True).logits
    assert torch.equal(base_out_1.detach(), ref_out_1.detach())
    assert torch.equal(base_out_2.detach(), ref_out_2.detach())


def test_deterministic_kl_no_grad_only_teacher_and_profile_archive_forward_flags(tmp_path: Path, monkeypatch):
    import copy
    import hashlib
    import shutil
    from pipeline.training.train_boundary_candidate import _forward_student_logits_eval_mode

    # Part A: autograd active ONLY on det_student_logits, never on teacher
    teacher = _make_synthetic_dropout_classifier(seed=53)
    student = copy.deepcopy(teacher)
    teacher.eval()
    for p in teacher.parameters():
        p.requires_grad_(False)
    student.train()
    with torch.no_grad():
        student.head.weight[2].add_(0.35)
    t_snap = {k: v.detach().clone() for k, v in teacher.state_dict().items()}

    input_ids = torch.randint(0, 32, (4, 5))
    attn = torch.ones_like(input_ids)
    with torch.no_grad():
        t_logits = teacher(input_ids=input_ids, attention_mask=attn).logits
    assert t_logits.requires_grad is False and t_logits.grad_fn is None

    det_logits = _forward_student_logits_eval_mode(student, input_ids, attn)
    assert det_logits.requires_grad is True and det_logits.grad_fn is not None
    l_tkl, _ = compute_masked_teacher_kl_loss(det_logits, t_logits, torch.ones(4, dtype=torch.long))
    assert l_tkl.requires_grad is True
    l_tkl.backward()
    for p in teacher.parameters():
        assert p.grad is None and p.requires_grad is False
    for k, orig_t in t_snap.items():
        assert torch.equal(teacher.state_dict()[k], orig_t)

    # Part B: profile isolation, fail-closed anchor-mode guards, prep plan & runner forwarding
    assert "teacher_student_anchor_mode" not in AUTHORIZED_FIT_PROFILES["option_a_teacher_kl"]
    det_cfg = AUTHORIZED_FIT_PROFILES["option_a_teacher_kl_deterministic"]
    assert det_cfg["teacher_kl_weight"] == 1.0
    assert det_cfg["teacher_temperature"] == 1.0
    assert det_cfg["teacher_student_anchor_mode"] == "eval_no_dropout_autograd_enabled"

    with pytest.raises(ValueError, match="option_a_teacher_kl_deterministic requires explicit teacher_student_anchor_mode"):
        validate_profile_settings(
            profile="option_a_teacher_kl_deterministic",
            epochs=3,
            lr=2e-5,
            batch_size=32,
            seed=42,
            fit_mode="fit2_supcon_energy",
            enable_selective_rejector=False,
            teacher_kl_weight=1.0,
            teacher_temperature=1.0,
            teacher_weights_sha256=EXPECTED_FIT2_SHA256,
            teacher_student_anchor_mode="train_stochastic",
        )
    with pytest.raises(ValueError, match="option_a_teacher_kl forbids non-stochastic"):
        validate_profile_settings(
            profile="option_a_teacher_kl",
            epochs=3,
            lr=2e-5,
            batch_size=32,
            seed=42,
            fit_mode="fit2_supcon_energy",
            enable_selective_rejector=False,
            teacher_kl_weight=1.0,
            teacher_temperature=1.0,
            teacher_weights_sha256=EXPECTED_FIT2_SHA256,
            teacher_student_anchor_mode="eval_no_dropout_autograd_enabled",
        )

    def _sha(p: Path) -> str:
        return hashlib.sha256(p.read_bytes()).hexdigest().lower()

    repo_root = Path(__file__).resolve().parents[2]
    prep_dir = tmp_path / "run-records-fit2-orig-deterministic-kl-v1-prep"
    ds_dir = prep_dir / "datasets"
    ds_dir.mkdir(parents=True)
    plan = _build_planned_execution_plan(
        profile_name="option_a_teacher_kl_deterministic",
        prep_records_dir=prep_dir,
        planned_fit_run_id="fit2-orig-deterministic-kl-v1",
        planned_future_paths={"archive_dir": str(tmp_path / "arch")},
        experiment_mode="return_contrast",
    )
    assert "--teacher-student-anchor-mode" in plan["planned_cli"]
    assert "eval_no_dropout_autograd_enabled" in plan["planned_cli"]
    assert plan["teacher_student_anchor_mode"] == "eval_no_dropout_autograd_enabled"

    ds_hashes: dict[str, str] = {}
    new_hashes: dict[str, str] = {}
    for fname in (*EXPECTED_ORIG_STAGE2_LOCKED_FILES, "orig_fit2_return_contrast_extension.jsonl"):
        fp = ds_dir / fname
        fp.write_text('{"ok": true}\n' if fname.endswith(".json") else '{"sample_id": "x"}\n', encoding="utf-8")
        digest = _sha(fp)
        key = (
            "boundary_split_manifest"
            if fname == "split_manifest.json"
            else ("orig_fit2_return_contrast_extension" if fname == "orig_fit2_return_contrast_extension.jsonl" else fname[:-len(".jsonl")])
        )
        ds_hashes[key] = digest
        new_hashes[fname] = digest
    source_hashes = {rel: _sha(repo_root / rel) for rel in RELEVANT_SOURCE_PATHS}
    for rel in RELEVANT_SOURCE_PATHS:
        snap = prep_dir / "source_snapshot" / rel
        snap.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(repo_root / rel, snap)
    base_metrics = {
        "boundary_pos_cal": {"count": 86, "correct_count": 68, "mean_max_prob": 0.686},
        "boundary_pos_cal_sup12": {"count": 48, "correct_count": 38, "conf_ge_070_count": 28, "conf_ge_080_count": 26},
        "boundary_pos_cal_esc34": {"count": 38, "correct_count": 30, "mean_max_prob": 0.671, "max_sup12_mass": 0.48},
        "bitext_cal": {"count": 690, "correct_count": 689},
        "boundary_neg_cal": {"count": 48, "pred_sup12_count": 9, "max_sup12_mass": 0.72, "max_single_sup12_prob": 0.56},
        "pos_train_added_18": {"count": 18, "correct_count": 18},
        "attribution_breakdown": {},
    }
    (prep_dir / "status.json").write_text(
        json.dumps({"status": "complete", "fits_executed": 0, "prep_archive": True}), encoding="utf-8"
    )
    (prep_dir / "prep_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "orig_fit2_return_contrast_prep.v4",
                "experiment_mode": "return_contrast",
                "is_promotion_candidate": True,
                "git_commit": "a" * 40,
                "source_hashes": source_hashes,
                "unchanged_original_recipe_parameters": UNCHANGED_ORIGINAL_RECIPE_PARAMETERS,
                "authorized_fit_profile": det_cfg,
                "execution_plan": plan,
                "teacher_anchor_config": {
                    "enabled": True,
                    "teacher_weights_sha256": EXPECTED_FIT2_SHA256,
                    "teacher_kl_weight": 1.0,
                    "teacher_temperature": 1.0,
                    "teacher_student_anchor_mode": "eval_no_dropout_autograd_enabled",
                    "anchor_effective_count": 13000,
                    "excluded_effective_count": 80,
                },
                "baseline_cal_reference": {
                    "baseline_weights_sha256": EXPECTED_FIT2_SHA256,
                    "baseline_calibration_manifest_sha256": "c" * 64,
                    "dataset_hashes": ds_hashes,
                    "metrics": base_metrics,
                },
                "preflight": {
                    "extension_version": "orig_fit2_return_channel_contrast_v2",
                    "counts": {"extension_pos_train_added": 18},
                    "dataset_hashes": ds_hashes,
                    "new_input_file_hashes": new_hashes,
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
    (init_dir / "model.safetensors").write_bytes(b"fit2")
    (serving_dir / "model.safetensors").write_bytes(b"serving")
    monkeypatch.setattr(
        "scripts.run_orig_fit2_return_contrast_fit._sha256_lower",
        lambda p: (
            EXPECTED_SERVING_SHA256
            if p == serving_dir / "model.safetensors"
            else (EXPECTED_FIT2_SHA256 if p == init_dir / "model.safetensors" else _sha(p))
        ),
    )
    monkeypatch.setattr(
        "scripts.run_orig_fit2_return_contrast_fit.verify_fit2_starting_checkpoint",
        lambda p: {"weights_sha256": EXPECTED_FIT2_SHA256, "temperature": 1.0, "rejector_enabled": False, "num_labels": 46},
    )
    monkeypatch.setattr(
        "scripts.run_orig_fit2_return_contrast_fit.verify_orig_relevant_source_provenance",
        lambda root: {"git_commit": "b" * 40, "source_hashes": source_hashes},
    )
    monkeypatch.setattr(
        "scripts.run_orig_fit2_return_contrast_fit.verify_git_commit_ancestor",
        lambda root, anc, desc="HEAD": "b" * 40,
    )

    captured_kwargs: dict[str, object] = {}

    def _fake_det_fit(**kwargs):
        captured_kwargs.update(kwargs)
        cand_dir = kwargs["artifact_root"] / kwargs["output_subdir"]
        cand_dir.mkdir(parents=True)
        for fname in ("model.safetensors", "tokenizer.json", "tokenizer_config.json", "config.json"):
            (cand_dir / fname).write_bytes(fname.encode("utf-8"))
        (cand_dir / "calibration_manifest.json").write_text('{"valid": true}', encoding="utf-8")
        (cand_dir / "candidate_provenance_manifest.json").write_text(
            json.dumps(
                {
                    "provenance_status": "verified",
                    "training_lineage": {
                        "teacher_kl_enabled": True,
                        "teacher_weights_sha256": kwargs["expected_teacher_weights_sha256"],
                        "teacher_kl_weight": kwargs["teacher_kl_weight"],
                        "teacher_temperature": kwargs["teacher_temperature"],
                        "teacher_student_anchor_mode": kwargs["teacher_student_anchor_mode"],
                    },
                }
            ),
            encoding="utf-8",
        )
        return {"fit_mode": "fit2_supcon_energy", "temperature": 1.0}

    monkeypatch.setattr("scripts.run_orig_fit2_return_contrast_fit.run_fit_and_lock_candidate", _fake_det_fit)
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
    monkeypatch.setattr(
        "scripts.run_orig_fit2_return_contrast_fit.evaluate_cal_guard_metrics_for_model",
        lambda d, inp: dict(base_metrics),
    )

    fit_res = run_authorized_fit(
        repo_root=repo_root,
        prep_dir=prep_dir,
        run_id="fit2-orig-deterministic-kl-v1",
        profile="option_a_teacher_kl_deterministic",
        epochs=3,
        lr=2e-5,
        teacher_kl_weight=1.0,
        teacher_temperature=1.0,
        teacher_weights_sha256=EXPECTED_FIT2_SHA256,
        teacher_student_anchor_mode="eval_no_dropout_autograd_enabled",
        execute_fit=True,
        main_candidates_dir=candidates_dir,
        local_root_base=local_base,
        init_model_dir=init_dir,
        serving_dir=serving_dir,
    )
    assert captured_kwargs["teacher_student_anchor_mode"] == "eval_no_dropout_autograd_enabled"
    run_cfg = json.loads((Path(fit_res["records_dir"]) / "run_config.json").read_text(encoding="utf-8"))
    assert run_cfg["teacher_anchor_config"]["teacher_student_anchor_mode"] == "eval_no_dropout_autograd_enabled"


def test_head_only_freeze_component_hashes_nograd_and_optimizer_exact_param_list():
    from transformers import DistilBertConfig, DistilBertForSequenceClassification
    from pipeline.evaluation.classifier_acceptance_gate import SUPPORTED_12_INTENTS
    from pipeline.training.train_boundary_candidate import (
        _configure_trainable_scope,
        _set_epoch_module_modes,
        _snapshot_frozen_component_hashes,
    )

    torch.manual_seed(42)
    full_cfg = DistilBertConfig(num_labels=len(STANDARD_INTENTS_46))
    model = DistilBertForSequenceClassification(full_cfg)
    scope_info = _configure_trainable_scope(
        model,
        "classifier_head_only",
        expected_trainable_param_count=35374,
        expected_frozen_param_count=66953472,
    )
    assert scope_info["trainable_param_count"] == 35374
    assert scope_info["frozen_param_count"] == 66953472
    assert scope_info["trainable_param_names"] == ["classifier.weight", "classifier.bias"]
    assert sum(p.numel() for p in model.parameters()) == 66988846

    pre_snap = _snapshot_frozen_component_hashes(model)
    expected_components = {
        "distilbert.embeddings",
        *[f"distilbert.transformer.layer.{i}" for i in range(6)],
        "pre_classifier",
        "buffers",
    }
    assert expected_components.issubset(set(pre_snap["component_hashes"].keys()))

    trainable_params = [p for p in model.parameters() if p.requires_grad]
    optimizer = torch.optim.AdamW(trainable_params, lr=1e-4, weight_decay=0.01)
    assert len(optimizer.param_groups) == 1
    opt_ids = [id(p) for p in optimizer.param_groups[0]["params"]]
    assert opt_ids == [id(model.classifier.weight), id(model.classifier.bias)]
    assert sum(p.numel() for p in optimizer.param_groups[0]["params"]) == 35374
    assert optimizer.param_groups[0]["lr"] == 1e-4
    assert optimizer.param_groups[0]["weight_decay"] == 0.01

    _set_epoch_module_modes(model, trainable_scope="classifier_head_only", feature_dropout_eval_mode=True)
    input_ids = torch.randint(0, full_cfg.vocab_size, (4, 12))
    attention_mask = torch.ones((4, 12), dtype=torch.long)
    logits = model(input_ids=input_ids, attention_mask=attention_mask, output_hidden_states=False).logits
    sup12_idx = torch.tensor([STANDARD_INTENTS_46.index(x) for x in SUPPORTED_12_INTENTS], dtype=torch.long)
    uniform_target = torch.full((2, len(STANDARD_INTENTS_46)), 1.0 / len(STANDARD_INTENTS_46))

    l_pos = torch.nn.functional.cross_entropy(logits[:2], torch.tensor([0, 31], dtype=torch.long), label_smoothing=0.03)
    neg_logits = logits[2:]
    l_kl = torch.nn.functional.kl_div(torch.nn.functional.log_softmax(neg_logits, dim=-1), uniform_target, reduction="batchmean")
    sup12_mass = torch.softmax(neg_logits, dim=-1)[:, sup12_idx].sum(dim=-1)
    l_ceil = torch.relu(sup12_mass - 0.18).pow(2).mean()
    pos_eng = (-torch.logsumexp(logits[:2], dim=-1)).mean().detach()
    neg_eng = -torch.logsumexp(neg_logits, dim=-1)
    l_eng = 0.25 * torch.relu((pos_eng + 2.0) - neg_eng).pow(2).mean()
    loss = l_pos + (0.80 * l_kl + 3.0 * l_ceil + l_eng)
    optimizer.zero_grad()
    loss.backward()

    assert model.classifier.weight.grad is not None and float(model.classifier.weight.grad.abs().max().item()) > 0.0
    assert model.classifier.bias.grad is not None and float(model.classifier.bias.grad.abs().max().item()) > 0.0
    assert all(p.grad is None for _, p in model.named_parameters() if not p.requires_grad)

    # Do NOT step optimizer; verify frozen parameter + buffer hashes remain bit-identical.
    post_snap = _snapshot_frozen_component_hashes(model)
    assert post_snap["all_frozen_tensors_sha256"] == pre_snap["all_frozen_tensors_sha256"]
    assert post_snap["component_hashes"] == pre_snap["component_hashes"]


def test_head_only_eval_dropout_deterministic_rng_zero_and_mode_guards():
    import numpy as np
    import random
    from transformers import DistilBertConfig, DistilBertForSequenceClassification
    from pipeline.training.train_boundary_candidate import (
        _configure_trainable_scope,
        _set_epoch_module_modes,
    )

    cfg = DistilBertConfig(
        num_labels=len(STANDARD_INTENTS_46),
        vocab_size=256,
        dim=64,
        hidden_dim=128,
        n_layers=2,
        n_heads=4,
    )
    model = DistilBertForSequenceClassification(cfg)
    _configure_trainable_scope(model, "classifier_head_only")

    # Even if recursive model.train() ran earlier, per-epoch _set_epoch_module_modes disables frozen dropout.
    model.train()
    _set_epoch_module_modes(model, trainable_scope="classifier_head_only", feature_dropout_eval_mode=True)
    assert model.distilbert.training is False
    assert model.pre_classifier.training is False
    assert model.dropout.training is False
    assert model.classifier.training is True
    for mod in model.modules():
        if mod is model.classifier:
            assert mod.training is True
        else:
            assert mod.training is False

    x = torch.randint(0, 256, (4, 10))
    mask = torch.ones((4, 10), dtype=torch.long)
    torch_rng0 = torch.get_rng_state().clone()
    np_rng0 = np.random.get_state()
    py_rng0 = random.getstate()

    out1 = model(input_ids=x, attention_mask=mask).logits
    out1.sum().backward()
    model.zero_grad(set_to_none=True)
    out2 = model(input_ids=x, attention_mask=mask).logits.detach()

    assert float((out1.detach() - out2).abs().max().item()) == 0.0
    assert torch.equal(torch.get_rng_state(), torch_rng0)
    np_rng1 = np.random.get_state()
    assert np_rng0[0] == np_rng1[0] and np.array_equal(np_rng0[1], np_rng1[1]) and np_rng0[2:] == np_rng1[2:]
    assert random.getstate() == py_rng0

    with pytest.raises(ValueError, match="requires explicit feature_dropout_eval_mode=True"):
        _set_epoch_module_modes(model, trainable_scope="classifier_head_only", feature_dropout_eval_mode=False)
    with pytest.raises(ValueError, match="only allowed with trainable_scope='classifier_head_only'"):
        _set_epoch_module_modes(model, trainable_scope="all", feature_dropout_eval_mode=True)


def test_head_only_inactive_supcon_equivalent_head_grad():
    from transformers import DistilBertConfig, DistilBertForSequenceClassification
    from pipeline.training.train_boundary_candidate import (
        _configure_trainable_scope,
        _set_epoch_module_modes,
        _supcon_loss,
    )

    torch.manual_seed(7)
    cfg = DistilBertConfig(
        num_labels=len(STANDARD_INTENTS_46),
        vocab_size=256,
        dim=64,
        hidden_dim=128,
        n_layers=2,
        n_heads=4,
    )
    model = DistilBertForSequenceClassification(cfg)
    _configure_trainable_scope(model, "classifier_head_only")
    _set_epoch_module_modes(model, trainable_scope="classifier_head_only", feature_dropout_eval_mode=True)

    x = torch.randint(0, 256, (6, 8))
    mask = torch.ones((6, 8), dtype=torch.long)
    y = torch.tensor([0, 0, 5, 5, 0, 0], dtype=torch.long)
    neg_mask = torch.tensor([False, False, False, False, True, True])

    out = model(input_ids=x, attention_mask=mask, output_hidden_states=True)
    l_base = torch.nn.functional.cross_entropy(out.logits[~neg_mask], y[~neg_mask], label_smoothing=0.03)
    model.zero_grad(set_to_none=True)
    l_base.backward(retain_graph=True)
    w_grad_base = model.classifier.weight.grad.detach().clone()
    b_grad_base = model.classifier.bias.grad.detach().clone()

    cls_norm = torch.nn.functional.normalize(out.hidden_states[-1][:, 0, :], dim=-1)
    sc_targets = torch.where(neg_mask, torch.full_like(y, -1), y)
    l_sc = 0.25 * _supcon_loss(cls_norm, sc_targets, temperature=0.12)
    assert l_sc.requires_grad is False

    model.zero_grad(set_to_none=True)
    (l_base + l_sc).backward()
    assert float((model.classifier.weight.grad - w_grad_base).abs().max().item()) == 0.0
    assert float((model.classifier.bias.grad - b_grad_base).abs().max().item()) == 0.0
    assert all(p.grad is None for _, p in model.named_parameters() if not p.requires_grad)


def test_head_only_profile_validation_defaults_and_negative_guards():
    from transformers import DistilBertConfig, DistilBertForSequenceClassification
    from pipeline.training.train_boundary_candidate import _configure_trainable_scope
    from scripts.run_orig_fit2_return_contrast_prep import DEFAULT_PREP_PROFILE

    assert DEFAULT_PREP_PROFILE == "lr5e6"
    assert "option_a_classifier_head_only_v1" in AUTHORIZED_FIT_PROFILES
    head_cfg = AUTHORIZED_FIT_PROFILES["option_a_classifier_head_only_v1"]
    assert head_cfg["lr"] == 1e-4
    assert head_cfg["epochs"] == 2
    assert head_cfg["batch_size"] == 32
    assert head_cfg["seed"] == 42
    assert head_cfg["weight_decay"] == 0.01
    assert head_cfg["fit_mode"] == "fit2_supcon_energy"
    assert head_cfg["min_temperature"] == 1.0
    assert head_cfg["enable_selective_rejector"] is False
    assert head_cfg["trainable_scope"] == "classifier_head_only"
    assert head_cfg["feature_dropout_eval_mode"] is True
    assert head_cfg["expected_trainable_param_count"] == 35374
    assert head_cfg["expected_frozen_param_count"] == 66953472

    ok = validate_profile_settings(
        profile="option_a_classifier_head_only_v1",
        epochs=2,
        lr=1e-4,
        batch_size=32,
        seed=42,
        fit_mode="fit2_supcon_energy",
        enable_selective_rejector=False,
        weight_decay=0.01,
        trainable_scope="classifier_head_only",
        feature_dropout_eval_mode=True,
    )
    assert ok["selected_recipe"] == "option_a_classifier_head_only_adamw_1e4_2ep"

    # Existing default profiles stay isolated and reject head-only flags.
    for p_name, p_epochs, p_lr, extra in (
        ("option_a", 3, 2e-5, {}),
        ("lr5e6", 3, 5e-6, {}),
        (
            "option_a_teacher_kl",
            3,
            2e-5,
            {"teacher_kl_weight": 1.0, "teacher_temperature": 1.0, "teacher_weights_sha256": EXPECTED_FIT2_SHA256},
        ),
    ):
        with pytest.raises(ValueError, match="forbids non-all trainable_scope"):
            validate_profile_settings(
                profile=p_name,
                epochs=p_epochs,
                lr=p_lr,
                batch_size=32,
                seed=42,
                fit_mode="fit2_supcon_energy",
                enable_selective_rejector=False,
                trainable_scope="classifier_head_only",
                **extra,
            )
        with pytest.raises(ValueError, match="forbids feature_dropout_eval_mode=True"):
            validate_profile_settings(
                profile=p_name,
                epochs=p_epochs,
                lr=p_lr,
                batch_size=32,
                seed=42,
                fit_mode="fit2_supcon_energy",
                enable_selective_rejector=False,
                feature_dropout_eval_mode=True,
                **extra,
            )

    # Head-only rejects wrong lr, epochs, weight_decay, trainable_scope, missing eval mode, or teacher_kl.
    for bad_kwargs, match in (
        ({"lr": 2e-5}, "enforces lr="),
        ({"epochs": 3}, "enforces epochs=2"),
        ({"weight_decay": 0.0}, "requires explicit weight_decay=0.01"),
        ({"weight_decay": None}, "requires explicit weight_decay=0.01"),
        ({"trainable_scope": "all"}, "requires explicit trainable_scope='classifier_head_only'"),
        ({"trainable_scope": None}, "requires explicit trainable_scope='classifier_head_only'"),
        ({"feature_dropout_eval_mode": False}, "requires explicit feature_dropout_eval_mode=True"),
        ({"enable_selective_rejector": True}, "selective rejector OFF"),
        ({"teacher_kl_weight": 1.0}, "forbids non-zero teacher_kl_weight"),
    ):
        kw = dict(
            profile="option_a_classifier_head_only_v1",
            epochs=2,
            lr=1e-4,
            batch_size=32,
            seed=42,
            fit_mode="fit2_supcon_energy",
            enable_selective_rejector=False,
            weight_decay=0.01,
            trainable_scope="classifier_head_only",
            feature_dropout_eval_mode=True,
        )
        kw.update(bad_kwargs)
        with pytest.raises(ValueError, match=match):
            validate_profile_settings(**kw)

    tiny = DistilBertForSequenceClassification(
        DistilBertConfig(num_labels=46, vocab_size=128, dim=32, hidden_dim=64, n_layers=1, n_heads=2)
    )
    with pytest.raises(ValueError, match="Trainable parameter count mismatch"):
        _configure_trainable_scope(tiny, "classifier_head_only", expected_trainable_param_count=35374)


def test_head_only_prep_archival_kwargs_forwarding_and_validate_only_zero_fits(monkeypatch, tmp_path):
    import hashlib
    import shutil
    from scripts.run_orig_fit2_return_contrast_prep import _build_planned_execution_plan

    def _sha(p: Path) -> str:
        return hashlib.sha256(p.read_bytes()).hexdigest().lower()

    repo_root = Path(__file__).resolve().parents[2]
    prep_dir = tmp_path / "run-records-fit2-orig-classifier-head-only-v1-prep"
    ds_dir = prep_dir / "datasets"
    ds_dir.mkdir(parents=True)
    head_cfg = AUTHORIZED_FIT_PROFILES["option_a_classifier_head_only_v1"]
    plan = _build_planned_execution_plan(
        profile_name="option_a_classifier_head_only_v1",
        prep_records_dir=prep_dir,
        planned_fit_run_id="fit2-orig-classifier-head-only-v1",
        planned_future_paths={"archive_dir": "arc", "records_dir": "rec", "local_dir": "loc"},
    )
    assert "--trainable-scope" in plan["planned_cli"]
    assert "classifier_head_only" in plan["planned_cli"]
    assert "--feature-dropout-eval-mode" in plan["planned_cli"]
    assert "--weight-decay" in plan["planned_cli"]
    assert "--teacher-kl-weight" not in plan["planned_cli"]
    assert plan["authorized_to_train_now"] is False

    ds_hashes: dict[str, str] = {}
    new_hashes: dict[str, str] = {}
    for fname in (*EXPECTED_ORIG_STAGE2_LOCKED_FILES, "orig_fit2_return_contrast_extension.jsonl"):
        fp = ds_dir / fname
        fp.write_text('{"ok": true}\n' if fname.endswith(".json") else '{"sample_id": "x"}\n', encoding="utf-8")
        digest = _sha(fp)
        key = (
            "boundary_split_manifest"
            if fname == "split_manifest.json"
            else ("orig_fit2_return_contrast_extension" if fname == "orig_fit2_return_contrast_extension.jsonl" else fname[:-len(".jsonl")])
        )
        ds_hashes[key] = digest
        new_hashes[fname] = digest
    source_hashes = {rel: _sha(repo_root / rel) for rel in RELEVANT_SOURCE_PATHS}
    for rel in RELEVANT_SOURCE_PATHS:
        snap = prep_dir / "source_snapshot" / rel
        snap.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(repo_root / rel, snap)
    base_metrics = {
        "boundary_pos_cal": {"count": 86, "correct_count": 68, "mean_max_prob": 0.686},
        "boundary_pos_cal_sup12": {"count": 48, "correct_count": 38, "conf_ge_070_count": 28, "conf_ge_080_count": 26},
        "boundary_pos_cal_esc34": {"count": 38, "correct_count": 30, "mean_max_prob": 0.671, "max_sup12_mass": 0.48},
        "bitext_cal": {"count": 690, "correct_count": 689},
        "boundary_neg_cal": {"count": 48, "pred_sup12_count": 9, "max_sup12_mass": 0.72, "max_single_sup12_prob": 0.56},
        "pos_train_added_18": {"count": 18, "correct_count": 18},
        "attribution_breakdown": {},
    }
    init_freeze_sha = "d" * 64
    (prep_dir / "status.json").write_text(
        json.dumps({"status": "complete", "fits_executed": 0, "prep_archive": True}), encoding="utf-8"
    )
    (prep_dir / "prep_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "orig_fit2_return_contrast_prep.v4",
                "experiment_mode": "return_contrast",
                "is_promotion_candidate": True,
                "git_commit": "a" * 40,
                "source_hashes": source_hashes,
                "unchanged_original_recipe_parameters": UNCHANGED_ORIGINAL_RECIPE_PARAMETERS,
                "authorized_fit_profile": head_cfg,
                "execution_plan": plan,
                "classifier_head_only_config": {
                    "enabled": True,
                    "trainable_scope": "classifier_head_only",
                    "feature_dropout_eval_mode": True,
                    "weight_decay": 0.01,
                    "teacher_used": False,
                    "trainable_param_count": 35374,
                    "frozen_param_count": 66953472,
                    "initial_frozen_tensors_sha256": init_freeze_sha,
                    "initial_freeze_component_hashes": {"distilbert.embeddings": "e" * 64},
                },
                "baseline_cal_reference": {
                    "baseline_weights_sha256": EXPECTED_FIT2_SHA256,
                    "baseline_calibration_manifest_sha256": "c" * 64,
                    "dataset_hashes": ds_hashes,
                    "metrics": base_metrics,
                },
                "preflight": {
                    "extension_version": "orig_fit2_return_channel_contrast_v2",
                    "counts": {"extension_pos_train_added": 18},
                    "dataset_hashes": ds_hashes,
                    "new_input_file_hashes": new_hashes,
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
    (init_dir / "model.safetensors").write_bytes(b"fit2")
    (serving_dir / "model.safetensors").write_bytes(b"serving")
    monkeypatch.setattr(
        "scripts.run_orig_fit2_return_contrast_fit._sha256_lower",
        lambda p: (
            EXPECTED_SERVING_SHA256
            if p == serving_dir / "model.safetensors"
            else (EXPECTED_FIT2_SHA256 if p == init_dir / "model.safetensors" else _sha(p))
        ),
    )
    monkeypatch.setattr(
        "scripts.run_orig_fit2_return_contrast_fit.verify_fit2_starting_checkpoint",
        lambda p: {"weights_sha256": EXPECTED_FIT2_SHA256, "temperature": 1.0, "rejector_enabled": False, "num_labels": 46},
    )
    monkeypatch.setattr(
        "scripts.run_orig_fit2_return_contrast_fit.verify_orig_relevant_source_provenance",
        lambda root: {"git_commit": "b" * 40, "source_hashes": source_hashes},
    )
    monkeypatch.setattr(
        "scripts.run_orig_fit2_return_contrast_fit.verify_git_commit_ancestor",
        lambda root, anc, desc="HEAD": "b" * 40,
    )

    val_out = run_authorized_fit(
        repo_root=repo_root,
        prep_dir=prep_dir,
        run_id="fit2-orig-classifier-head-only-v1",
        profile="option_a_classifier_head_only_v1",
        epochs=2,
        lr=1e-4,
        weight_decay=0.01,
        trainable_scope="classifier_head_only",
        feature_dropout_eval_mode=True,
        execute_fit=False,
        main_candidates_dir=candidates_dir,
        local_root_base=local_base,
        init_model_dir=init_dir,
        serving_dir=serving_dir,
    )
    assert val_out["validated_only"] is True
    assert val_out["fits_executed"] == 0

    captured_kwargs: dict[str, object] = {}

    def _fake_head_fit(**kwargs):
        captured_kwargs.update(kwargs)
        cand_dir = kwargs["artifact_root"] / kwargs["output_subdir"]
        cand_dir.mkdir(parents=True)
        for fname in ("model.safetensors", "tokenizer.json", "tokenizer_config.json", "config.json"):
            (cand_dir / fname).write_bytes(fname.encode("utf-8"))
        (cand_dir / "calibration_manifest.json").write_text('{"valid": true}', encoding="utf-8")
        (cand_dir / "candidate_provenance_manifest.json").write_text(
            json.dumps(
                {
                    "provenance_status": "verified",
                    "training_lineage": {
                        "trainable_scope": kwargs["trainable_scope"],
                        "feature_dropout_eval_mode": kwargs["feature_dropout_eval_mode"],
                        "weight_decay": kwargs["weight_decay"],
                        "trainable_param_count": kwargs["expected_trainable_param_count"],
                        "frozen_param_count": kwargs["expected_frozen_param_count"],
                        "post_fit_freeze_verified": True,
                        "post_fit_frozen_tensors_sha256": init_freeze_sha,
                        "teacher_kl_enabled": False,
                    },
                }
            ),
            encoding="utf-8",
        )
        return {"fit_mode": "fit2_supcon_energy", "temperature": 1.0}

    monkeypatch.setattr("scripts.run_orig_fit2_return_contrast_fit.run_fit_and_lock_candidate", _fake_head_fit)
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
    monkeypatch.setattr(
        "scripts.run_orig_fit2_return_contrast_fit.evaluate_cal_guard_metrics_for_model",
        lambda d, inp: dict(base_metrics),
    )

    fit_res = run_authorized_fit(
        repo_root=repo_root,
        prep_dir=prep_dir,
        run_id="fit2-orig-classifier-head-only-v1",
        profile="option_a_classifier_head_only_v1",
        epochs=2,
        lr=1e-4,
        weight_decay=0.01,
        trainable_scope="classifier_head_only",
        feature_dropout_eval_mode=True,
        execute_fit=True,
        main_candidates_dir=candidates_dir,
        local_root_base=local_base,
        init_model_dir=init_dir,
        serving_dir=serving_dir,
    )
    assert captured_kwargs["trainable_scope"] == "classifier_head_only"
    assert captured_kwargs["feature_dropout_eval_mode"] is True
    assert captured_kwargs["weight_decay"] == 0.01
    assert captured_kwargs["expected_trainable_param_count"] == 35374
    assert captured_kwargs["expected_frozen_param_count"] == 66953472
    assert "teacher_kl_weight" not in captured_kwargs
    run_cfg = json.loads((Path(fit_res["records_dir"]) / "run_config.json").read_text(encoding="utf-8"))
    assert run_cfg["classifier_head_only_config"]["trainable_scope"] == "classifier_head_only"
    assert run_cfg["classifier_head_only_config"]["teacher_used"] is False
    cal_rep = json.loads((Path(fit_res["records_dir"]) / "cal_guard_report.json").read_text(encoding="utf-8"))
    assert len(cal_rep["checks"]) == 12
