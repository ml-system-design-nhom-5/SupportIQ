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
    source_hashes = {rel: _sha(repo_root / rel) for rel in RELEVANT_SOURCE_PATHS}
    for rel in RELEVANT_SOURCE_PATHS:
        snap = prep_dir / "source_snapshot" / rel
        snap.parent.mkdir(parents=True, exist_ok=True)
        snap.write_text(f"# {rel}\n", encoding="utf-8")

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
