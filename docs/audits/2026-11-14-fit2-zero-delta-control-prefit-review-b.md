# Worker B Pre-Fit Audit: `fit2-orig-zero-delta-control-v1` (Matched Zero-Delta Control)

**Date:** 2026-11-14  
**Reviewer:** Worker B (Zero-Fit Audit)  
**Branch:** `minh`  
**Reviewed Commits:** `118196095ee040d3606fc6960a2fa94ae8d89957` (`prep(fit2-control): add zero-fit matched zero-delta control mode and cal attribution breakdown`), `2c4ca1755b72a5b94fcc6a3d83fc9cb6ff8cc937` (`docs(audit): record zero-fit fit2 matched zero-delta control prep and CAL attribution`)  
**Frozen Prep Bundle:** [`artifacts/models/candidates/run-records-fit2-orig-zero-delta-control-v1-prep`](file:///F:/Năm%203/SD/project/SupportIQ/artifacts/models/candidates/run-records-fit2-orig-zero-delta-control-v1-prep)  
**Verdict:** `PASS` *(scientific one-fit-ready preflight ONLY — `is_promotion_candidate=false`; does NOT authorize starting training without explicit Coordinator release)*  
**Fits Executed:** `0` (`--validate-only` and read-only checks only; optimizer, calibrator, paid LLMs, and full holdouts not invoked)

---

## 1. Control Design, Data Parity & Stochastic Limits

- **Starting Checkpoint & Hyperparameters:** Starts strictly from Original Fit2 (`reconstructed-fit2-supcon-20261113`, `model.safetensors` SHA-256 `f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa`, `T=1.0`, `selective_rejector=False`, `46` labels) under locked `option_a` (`epochs=3, lr=2e-5, batch_size=32, seed=42, fit_mode="fit2_supcon_energy", min_temperature=1.0, enable_selective_rejector=False`), matching `fit2-orig-ret-channel-fit-v1` (`lr=2e-5`).
- **Strictly Additive Data Code (`orig_fit2_return_contrast_data.py`):** Diff in `11819609` appends `prepare_and_lock_orig_fit2_zero_delta_control_splits` (`+140` lines, `0` deletions), leaving `+18` return-contrast extension content and prior semantics completely unmodified.
- **Bit-Identical Stage-2 Inputs (`13/13`):** Independently verified `0` SHA-256 diffs across all 13 locked files between `run-records-fit2-orig-zero-delta-control-v1-prep/datasets` and `run-records-faithful-fit2-20261113/stage2_inputs`, `orig_fit2_return_contrast_extension.jsonl` absent (`False` in both `datasets/` and prep root), `0` `orig_ret_ch_*` IDs in `boundary_pos_train.jsonl` / `full_train_split.jsonl`, `domain_pos_train=181`, `full_train_split_rows=11,320`, and recomputed `effective_train_total=13,000` (`pos=11,812`, `neg=1,188`).
- **Fresh Token Audit & Unchanged Overlaps:** Recomputed `token_truncation_audit_max_length_64.train_all` on the 11,320 train rows -> `count=11320, truncated_count=0, max_tokens=30` (matches `prep_manifest.json`). Inherited `3` normalized `bitext_train_noisy` vs `bitext_test_6690` overlaps remain unmodified (`exclude_noisy_test_overlap=false`, `0` in clean/CAL); sealed `fit-v1` / `lr5e6-v1` archives and their static metadata are untouched.
- **Unavoidable Batching / Trajectory Limit (Not an Exact Stochastic Counterfactual):** `train_boundary_candidate.py` uses `DataLoader(ds, batch_size=32, shuffle=True, generator=...)` (`drop_last=False`). Removing the `+18` rows (`+80` effective rows) shifts `len(loader)` from `409` batches/epoch (`1,227` steps) on `13,080` rows to `407` batches/epoch (`1,221` steps) on `13,000` rows, altering `randperm` shuffling, in-batch SupCon pairings, and linear LR decay slope after step `122`. This yields a clean **matched continuation control**, not a bitwise stochastic counterfactual, and carries `is_promotion_candidate=false`.

---

## 2. Hashes, Guard Isolation & Closure Verification

- **Frozen Bundle Hashes:**
  - `prep_manifest.json` SHA-256: `5ad2f3eb888979e6cd913850aa423c77cae1cc60b345b3326ee17fa0c7aa3b92`
  - `sidecar_sha_inventory.json` SHA-256: `0200ab011fd5afdf280c0c1c1dac5e46d85a81fe381e5ef9bc39d599b7c3952c` (`37/37` files verified, `0` missing/extra/mismatches)
  - `source_snapshot/`: `19/19` tracked files match workspace `HEAD` (`0` mismatches)
- **Untouched Archives & Unused Control Outputs:** Original Fit2 (`f695b1fe...`), Fit1 (`95a940b6...`), Serving (`dc7af8cffb19fe7711ed5a5d0137ffff3d7d1a1f43bad5a35edff8c8de4c1302`), `v1/v2/v3/v4-prep` (`v3` `24094bc7...`, `v4` `55e53cf0...`), `fit-v1` (`dc3e88e713c71fe0e521a1dc5bec5831d9a0a91a83d4c3d1b413d3b1cd68e44d`), and `lr5e6-v1` (`b7a285479b853b5bed9ad1c67caaeed1b45107bd78bf8e53e23f6ec4f332feb2`) remain unmodified; `fit2-orig-zero-delta-control-v1` candidate, records, eval, and `%LOCALAPPDATA%\SupportIQ\fit_runs\...` directories do not exist yet.
- **No Generic Bypass & Control CAL Guard Isolation:**
  - `run_orig_fit2_return_contrast_fit.py` exposes no `--cal-guard-mode` CLI flag; `cal_guard_mode="control"` (`matched_zero_delta_control_11_checks`) activates **only** when `prep_schema_version == "orig_fit2_zero_delta_control_prep.v1"`, which requires `authorized_fit_profile == "option_a"` (`lr=2e-5`), `experiment_mode == "matched_zero_delta_control"`, `is_promotion_candidate is False`, `delta_absent is True`, `extension_pos_train_added == 0`, exact `13` Stage-2 file hashes, absent `orig_fit2_return_contrast_extension.jsonl`, and ancestor source closure.
  - Candidate profiles (`option_a` return contrast and `lr5e6`) continue requiring all `12` CAL checks including `pos_train_added_18_correct_count >= 15` (`baseline_cal_reference` omitting `pos_train_added_18` in `v4-prep` fails closed), and Control mode skips **only** `pos_train_added_18_correct_count` while keeping the exact same 11 integer/float+`3e-6` gates and baseline references.

---

## 3. Reproducible CAL Attribution Breakdown & Scientific Reading

Independently recomputed post-`T` `float64` CAL metrics (`include_added_18=False`, `cal_guard_mode="control"`) match [2026-11-14-fit2-zero-delta-control-prep-a.md](file:///F:/Năm%203/SD/project/SupportIQ/docs/audits/2026-11-14-fit2-zero-delta-control-prep-a.md):
- **`orig_fit2` (`f695b1fe`):** `pos_cal` `68/86` (`all_mmp=0.686344`, `corr=0.732839`, `incorr=0.510698`), `esc34` `30/38` (`all=0.670962`, `corr=0.724323`, `incorr=0.470862`), `neg pred_sup12=9/48`.
- **`prior_2e5` (`dc3e88e7`):** `pos_cal` `68/86` (`all=0.722439`, `corr=0.753907`, `incorr=0.603560`), `esc34` `30/38` (`all=0.707041` `+0.036078`, `corr=0.730540` `+0.006218`, `incorr=0.618916` `+0.148055`), `neg pred_sup12=10/48` — **FAIL `6/11`**.
- **`cand_lr5e6` (`b7a28547`):** `pos_cal` `66/86` (`sup12` `36/48`, `all=0.724639`, `corr=0.771944`, `incorr=0.568534`), `esc34` `30/38` (`all=0.708544` `+0.037581`, `corr=0.736837` `+0.012515`, `incorr=0.602444` `+0.131582`), `neg pred_sup12=11/48` — **FAIL `7/11`**.

`_summarize_attribution_slice` correctly computes unmasked `all`, `correct`, and `incorrect` group averages; both `2e-5` and `5e-6` `+18`-row continuations inflated wrong-prediction `esc34` confidence (`+0.148` / `+0.132`) and negative `sup12` intrusion (`9 -> 10` / `11`), so running this zero-delta `2e-5` control cleanly separates extra-epoch continuation drift from `+18`-row data interaction without holdout-driven tuning. Worker C's full EVAL/OOD/safety/promotion protocol remains untouched.

---

## 4. Verification Runs (Zero Fits)

1. **Regression & provenance suites:** `.venv/Scripts/python.exe -m pytest tests/unit/test_orig_fit2_return_contrast_prep.py tests/unit/test_boundary_contrast_fit.py tests/unit/test_faithful_fit2_entrypoint.py tests/unit/test_gate_contract_b.py tests/unit/test_task_c_evaluation_gates.py tests/unit/test_model_provenance.py -v` -> **`59 passed, 2 deselected in 268.80s`**.
2. **Real-model CAL guard check:** `.venv/Scripts/python.exe -m pytest -m real_model tests/unit/test_orig_fit2_return_contrast_prep.py -v` -> **`1 passed, 11 deselected in 10.73s`**.
3. **Independent live guard probes:** Verified fail-closed rejection on accidental `lr=5e-6`, mismatched `profile="lr5e6"`, CLI `--cal-guard-mode control`, existing `run_id` collision, `is_promotion_candidate=True` tamper, omitted `pos_train_added_18` in `v4-prep`, dirty/untracked `RELEVANT_SOURCE_PATHS`, and non-ancestor `git_commit` (`9/9` passed).
4. **Pre-commit & post-commit `--validate-only`:**  
   `.venv/Scripts/python.exe -m scripts.run_orig_fit2_return_contrast_fit --prep-dir artifacts/models/candidates/run-records-fit2-orig-zero-delta-control-v1-prep --run-id fit2-orig-zero-delta-control-v1 --profile option_a --epochs 3 --lr 2e-5 --batch-size 32 --seed 42 --fit-mode fit2_supcon_energy --validate-only` (`fits_executed: 0`, `lr: 2e-05`, `prep_git_commit: 118196095ee040d3606fc6960a2fa94ae8d89957`, clean descendant `HEAD`).

---

## 5. Frozen Future Single-Fit Command (Upon Coordinator Release Only)

```powershell
.venv/Scripts/python.exe -m scripts.run_orig_fit2_return_contrast_fit --prep-dir artifacts/models/candidates/run-records-fit2-orig-zero-delta-control-v1-prep --run-id fit2-orig-zero-delta-control-v1 --profile option_a --epochs 3 --lr 2e-5 --batch-size 32 --seed 42 --fit-mode fit2_supcon_energy --run-authorized-fit
```
