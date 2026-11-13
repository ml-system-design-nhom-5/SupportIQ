# A/B/C Integration & Scoped Cleanup Manifest (Fit2 v4.1 Freeze)

- **Branch:** `minh` (pre-evaluation freeze prior to Worker C independent `fit2-boundary-contrast-v4p1` evaluation)
- **Active Fit Provenance Commit:** `42c6980f84824fc481bad47f97837e10f5ad285f`
- **No live training, calibration edits, provider calls, push, or old workspace/branch deletions performed.**

---

## 1. Historical Source Integration Mapping

### A. Already Integrated Prior to This Pass (`e4adafd`, `f5913ad`, `9ff541b`, `42c6980`)
- Active training, data, runner, gate, and review artifacts on `minh`:
  `pipeline/evaluation/classifier_acceptance_gate.py`, `pipeline/training/{boundary_contrast_data.py,boundary_curriculum_data.py,closure_domain_data.py,domain_templates.py,selective_domain_data.py,train_boundary_candidate.py,train_domain_candidate.py,train_selective_candidate.py}`, `scripts/run_boundary_contrast_fit.py`, `tests/unit/{test_boundary_contrast_fit.py,test_gate_contract_b.py}`, `docs/superpowers/plans/2026-11-14-fit2-v4-taxonomy-calibration-plan.md`, `docs/audits/{2026-11-14-fit2-v4-prep-review-b.md,2026-11-14-fit2-v4p1-prep-rereview-b.md}`.

### B. Newly Integrated Files (From Shared Git Objects & Preserved MAIN File)
| Source Worker / Commit | Integrated Path(s) | Notes |
|---|---|---|
| Worker A `428d91831fb66c9162a498a9eabf299fd2b76169` / `4939970b27ca93bff68196021119a038828cbc23` / `c6cae7a5bb777777a60d8fc72c1dc7fea83a7452` | `scripts/run_faithful_fit2_restore.py`, `pipeline/training/train_closure_candidate.py`, `tests/unit/test_faithful_fit2_entrypoint.py` | Preserves original Stage-1 `c6cae7a` closure recipe + Stage-2 faithful Fit2 restoration entrypoint. Minimal 1-line import repair in `scripts/run_faithful_fit2_restore.py`: imports `verify_reload_from_archive` from `pipeline.training.train_boundary_candidate` instead of excluded superseded `train_fit2_improve`. |
| MAIN untracked (Worker B, coordinator-preserved) | `docs/audits/2026-11-13-fit2-boundary-contrast-v1-audit-b.md` | Exact original `v1` (`494fe730`, `REJECT`) audit report committed unchanged. |
| Worker B `e5aebae81a547d29a25cd48cb2e874b4ecde1953` (`3ebff38`, `fe34dc7`, `f677f38`) | `docs/audits/{2026-11-13-boundary-diagnosis-b.md,2026-11-13-faithful-fit2-plan-review-b.md,2026-11-13-fit2-boundary-contrast-v2-diagnosis-b.md,2026-11-13-fit2-improve-audit-b.md}`, `tests/unit/test_supported_unsupported_boundary_b.py` | Preserves historical labels, hashes, and boundary diagnosis tests verbatim (`3ebff38` gate patch already integrated & extended in `9ff541b`). |
| Worker B `2e3ff4d4d1ba0bf8d35ad253fe951f3e166b7fac` | `scripts/run_classifier_vs_serving_live_eval.py`, `artifacts/evaluation/classifier_vs_serving_live_20261113/{COMPARISON_REPORT.md,comparison_report.json,preflight_and_budget.json,raw_records.json}` | Online comparison reproducibility script & recorded evidence. Legacy `DEFAULT_FIT2_DIR` points to removed `supportiq-final-routing` worktree; pass `--fit2-dir` when re-running. |
| Worker C `dc28e52` (`a84c9ca`, `efb6868`, `2dd5b79`, `e228f47`) | `docs/audits/{2026-11-13-faithful-fit2-restoration-audit.md,2026-11-13-fit2-independent-gate.md,2026-11-14-fit2-v3-targeted-audit.md}`, `artifacts/evaluation/fit2_v3_targeted_audit_20261114/{probe_v3.py,probes.json}`, `artifacts/evaluation/fit2_independent_gate_20261113/{cases.jsonl,evaluate.py,gate.py,manifest.json,results/*}`, `tests/unit/test_fit2_independent_gate.py` | Preserves sealed 36-case gate (`cases.jsonl` untouched) and targeted `v3` audit probes. Minimal LF-normalization fallback in `tests/unit/test_fit2_independent_gate.py::test_manifest_hash_lock` for `data/knowledge/approved_kb.v2.json` so Windows `core.autocrlf` CRLF checkout matches Git blob SHA `aaa924c4...` without altering `manifest.json` or KB data. |

### C. Excluded Superseded / Non-Source Artifacts
- **Worker A (`428d918`, `c6cae7a`, `d7ddaf2`):** `pipeline/training/{fit2_improve_data.py,train_fit2_improve.py}`, `scripts/eval_fit2_improve.py`, `tests/unit/test_fit2_improve.py` (superseded `0f2da927` sibling-boundary experiment `REJECT`ed by B & C; code & eval reports already archived in `artifacts/models/candidates/run-records-20261113-0f2da927/`), historical `docs/superpowers/plans/2026-11-13-*.md` and intermediate `artifacts/evaluation/{boundary_contrast_20261113,fit2_improve_20261113,original_fit2_dryrun_20261113}` manifests (superseded by `2026-11-14-fit2-v4-taxonomy-calibration-plan.md` & archived in `run-records-*`), `tests/unit/test_task_a_closure_candidate.py` (hardcodes missing `artifacts/evaluation/task_a_closure_20261113`), `tests/unit/test_task_a_boundary_candidate.py` (covered by active boundary tests).
- **Worker C (`dc28e52`):** `artifacts/evaluation/fit2_independent_gate_20261113/__pycache__/gate.cpython-312.pyc` (compiled Python bytecode).

---

## 2. Active `fit2-boundary-contrast-v4p1` Recorded State & Baselines

*(Recorded CAL-only training telemetry from `artifacts/evaluation/boundary_contrast_20261114/fit2-boundary-contrast-v4p1-run.log` and archive manifests; **NOT** evaluation acceptance or promotion.)*

- **Serving Baseline (`artifacts/models/trained/distilbert-supportiq`):** `model.safetensors` `dc7af8cffb19fe7711ed5a5d0137ffff3d7d1a1f43bad5a35edff8c8de4c1302` (unchanged).
- **Original Fit2 Init (`artifacts/models/candidates/reconstructed-fit2-supcon-20261113`):** `model.safetensors` `f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa` (unchanged).
- **Frozen Candidate (`artifacts/models/candidates/fit2-boundary-contrast-v4p1`):**
  - `model.safetensors`: `e1039f9207a6aef5bfd2fcb5b8f14eb84a86d735da2a7386ed9721fb89ccb76f`
  - `tokenizer.json`: `41b9d12a4c559e4098f30173bc0f76d092c43d7b1f873e7027da45a256f30f87`
  - `config.json`: `6fa1fa9cc6a94063a977b0adaf2c9c3b296cf296d4ad9dcc6f2c52ca3bac9cb2`
  - `archive_sha_inventory.json`: `6/6` match (`0` mismatches); `run-records-fit2-boundary-contrast-v4p1/sidecar_sha_inventory.json`: `30/30` match (`0` mismatches).
  - Source commit recorded in `status.json` / `run_config.json` / `candidate_provenance_manifest.json`: `42c6980f84824fc481bad47f97837e10f5ad285f` (`fits_completed=1`, `T=1.0`, `rejector.enabled=true`, `rejector_c=0.75`, `threshold=0.72`, `feasible_candidates=101/180`).
  - CAL-only selection counts: `cal_dom_correct_draft=29/53`, `cal_bitext_correct_draft=150/165`, `cal_esc34_unsafe_draft=0/588`, `cal_human_agent_unsafe_draft=0/19`, `cal_neg_false_draft=0/60`, `cal_neg_false_accept_any=4/60`.

---

## 3. Old Workspaces Retention & Preservation Gaps (No Deletion Performed)

- **`C:/Users/PC/orca/workspaces/SupportIQ/fit2-boundary-b` (`MINHDZVODICH/fit2-boundary-b` at `e5aebae`):** Only `.pytest-cleanup.lock`, `.pytest_cache/`, `__pycache__/`, `tmp/` untracked/ignored. Zero unique untracked evidence. (`2e3ff4d` came from `MINHDZVODICH/supportiq-final-accounting`, now integrated into `minh`).
- **`C:/Users/PC/orca/workspaces/SupportIQ/fit2-gate-c` (`MINHDZVODICH/fit2-gate-c` at `dc28e52`):** Only `.pytest-cleanup.lock`, `__pycache__/` untracked/ignored. All committed artifacts/audits integrated into `minh`; coordinator plans to assign `v4p1` evaluation to Worker C.
- **`C:/Users/PC/orca/workspaces/SupportIQ/fit2-improve-a` (`MINHDZVODICH/fit2-improve-a` at `428d918`):** All 7 checkpoints (`v1`, `v2`, `v3`, `fit1/fit2 sibling`, `reconstructed fit1/fit2`), all 6 sidecar files per `v1..v3`/reconstructed checkpoint, `v1..v3` logs, `dryrun_manifest{,_v2,_v4}.json`, and `fit2_improve_20261113` datasets/eval reports verified byte-for-byte in `MAIN/artifacts/models/candidates/`.
  - **Preservation gaps / hold reasons:** (1) `fit2-improve-a` has dirty `dataset_lock_manifest.json` (`locked_at=15:54:35Z` vs archived `15:31:16Z`) and `stage1_datasets/closure_dataset_manifest.json` (`generated_at=15:54:04Z` vs `15:50:52Z`) from a later dryrun timestamp; (2) branch `MINHDZVODICH/fit2-improve-a` retains the excluded `0f2da927` sibling-boundary files and `2026-11-13` historical plans. Do not delete old branches/worktrees until coordinator confirms excluded historical refs are no longer needed and C's `v4p1` evaluation workspace plan is settled.

---

## 4. Scoped Cleanup Inventory & Verification

- **Executed Disposable Cache Cleanup:** `powershell -ExecutionPolicy Bypass -File scripts/clean_test_cache.ps1 -Apply` -> **`Removed 238 cache directories`** (`.pytest_cache`: 1, `tmp/pytest/*`: 209, source `__pycache__`: 28 across `apps`, `pipeline`, `tests`, `scripts`), all verified non-reparse paths inside `MAIN` with `0` tracked files.
- **Tracked Deletions:** `0` (`None` safely disposable without losing authoritative docs, recorded eval evidence, or regression tests; no separate tracked cleanup commit needed).
- **Explicitly Skipped / Preserved:** `artifacts/models/` (including `D artifacts/models/.gitkeep` and all rejected/failed checkpoints), `artifacts/evaluation/` (including `boundary_contrast_20261114/` `v4p1` run log/model), `data/`, user `.pptx` files (`report.pptx`, `docs/report.pptx`, `docs/report.template.pptx`), `.env`, `ai-for-production.zip`, `.pytest-cleanup.lock`, and uncertain gitignored `tmp/` items (`tmp/acceptance-preflight`, `tmp/ci-integration-eval`, `tmp/report-work`, `tmp/tmpudxh8xh2`, `tmp/*.png`, `tmp/*.sqlite3`, `tmp/*.log`, `tmp/udp-guard-snippet.txt`).
- **Post-Cleanup Verification:**
  - CLI/compile checks (`run_faithful_fit2_restore --help`, `run_classifier_vs_serving_live_eval --help`, `fit2_independent_gate_20261113/evaluate.py --help`, `py_compile`): exit `0`.
  - `verify_relevant_source_provenance` (`12` active source files), `fit2-boundary-contrast-v4p1` (`6/6`), `run-records-fit2-boundary-contrast-v4p1` (`30/30`): `0` mismatches.
  - `.venv/Scripts/python.exe -B -m pytest tests/unit/test_faithful_fit2_entrypoint.py tests/unit/test_fit2_independent_gate.py tests/unit/test_supported_unsupported_boundary_b.py tests/unit/test_boundary_contrast_fit.py -p no:cacheprovider -q` -> **`43 passed, 1 xfailed in 105.97s`**.
