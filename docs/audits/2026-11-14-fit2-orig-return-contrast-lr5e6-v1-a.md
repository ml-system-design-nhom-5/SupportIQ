# Fit Audit Report: `fit2-orig-ret-channel-lr5e6-v1` (Worker A)

- **Role / Branch / Workspace:** Worker A (`minh`, `F:/Năm 3/SD/project/SupportIQ`)
- **Coordinator Release:** Released after Worker B v4 PASS (`5c06889ce4f9016c0693f4c9763af1f68df10306`), preflight `--validate-only` PASS.
- **Fit Count:** `1` (`fit2-orig-ret-channel-lr5e6-v1`; single authorized run, no retry/retrain/tuning/holdout evaluation/runtime promotion/paid LLM/embedding call).
- **Hardware & Duration:** `NVIDIA GeForce RTX 5060` (CUDA); optimizer `train_seconds = 111.74` (wall timestamps `2026-11-14T12:53:01.582969+00:00` -> `2026-11-14T12:55:13.794403+00:00`).

---

## 1. Provenance, Archive Paths & Exact SHA-256 Checksums

- **Git HEAD at fit execution:** `5c06889ce4f9016c0693f4c9763af1f68df10306`
- **Locked `v4-prep` git commit (`ancestor` verified):** `98d5de8fddca100520c86b38fd344db80675ae0c`
- **Locked `v4-prep` bundle:** `artifacts/models/candidates/run-records-fit2-orig-ret-channel-v4-prep`
  - `prep_manifest.json` SHA-256: `55e53cf0e1067216a25462b5d03ffc63eef406854b063b9c601ab1de9eaa9a45`
  - `sidecar_sha_inventory.json` SHA-256: `f8262ffd73816bafc164a608521b7205ffefd1d46a4ecae6f7d267de5026090c`
- **Candidate Model Archive:** `artifacts/models/candidates/fit2-orig-ret-channel-lr5e6-v1`
  - `model.safetensors`: `b7a285479b853b5bed9ad1c67caaeed1b45107bd78bf8e53e23f6ec4f332feb2`
  - `calibration_manifest.json`: `a62c3a138cb6340c14c6e2ba20e97c81ee54a9dd7488249382546d07d75482da` (`valid=true`, `temperature=1.0`, `selective_rejector.enabled=false`)
  - `candidate_provenance_manifest.json`: `9fee3f6e8d49d6e82c6a668358b86275ae5c25bf025acab0da3d06bd9b36615b` (`provenance_passed=true`, `num_labels=46`)
  - `tokenizer.json`: `41b9d12a4c559e4098f30173bc0f76d092c43d7b1f873e7027da45a256f30f87`
  - `config.json`: `6fa1fa9cc6a94063a977b0adaf2c9c3b296cf296d4ad9dcc6f2c52ca3bac9cb2`
  - `archive_sha_inventory.json`: `4d1f9204b8d8cd4a3f55543baec1d74b29f75c2253810591b1600013d9e49855` (`6/6` files verified)
- **Run Records & Local Root:**
  - `artifacts/models/candidates/run-records-fit2-orig-ret-channel-lr5e6-v1`
  - `sidecar_sha_inventory.json`: `4b5f53e479115bb182cc9e9557c7ddea4b7f1b2bbd801f4cd96089b48a7c69b5` (`41/41` files verified)
  - `inputs/inputs_sha256_inventory.json`: `15/15` files verified
  - `cal_guard_report.json`: `01d4b9956c563fba64512aa92ff3f1daf12cd732b8fb9d630e993f69a44613a4`
  - Local working dir: `artifacts/evaluation/fit2_orig_ret_channel_20261114/fit2-orig-ret-channel-lr5e6-v1`
- **Reload & Untouched Baseline/Serving Checks:**
  - `verify_reload_from_archive`: `reload_verified=true`, `num_labels=46`
  - Original Fit2 (`reconstructed-fit2-supcon-20261113/model.safetensors`): `f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa` (unchanged init)
  - Serving (`SERVING_DIR/model.safetensors`): `dc7af8cffb19fe7711ed5a5d0137ffff3d7d1a1f43bad5a35edff8c8de4c1302` (unchanged active serving)

---

## 2. Locked Hyperparameters & Optimizer Summary

- **Profile:** `lr5e6` (`lr=5e-6`, `epochs=3`, `batch_size=32`, `seed=42`, `fit_mode="fit2_supcon_energy"`, `min_temperature=1.0`, `enable_selective_rejector=False`)
- **Calibration:** `T = 1.0` (`temperature_scaling_nll`, `min_temperature=1.0`, `selective_rejector_enabled=False`)
- **Epoch Stats:**
  - Epoch 1: `mean_loss=0.36887`, `pos_loss_sum=0.26245`, `neg_loss_sum=0.0088`, `supcon_loss_sum=0.09762`
  - Epoch 2: `mean_loss=0.35164`, `pos_loss_sum=0.25348`, `neg_loss_sum=0.00871`, `supcon_loss_sum=0.08945`
  - Epoch 3: `mean_loss=0.34962`, `pos_loss_sum=0.25247`, `neg_loss_sum=0.0087`, `supcon_loss_sum=0.08845`

---

## 3. Read-Only Post-Fit CAL Guard (`cal_guard_report.json`)

- **Overall Verdict:** `passed = False`, `recommended_status = "CAL_GUARD_REJECT_DO_NOT_PROMOTE"` (`5/12` passed, `7/12` failed; archived cleanly without retrain or threshold changes).
- **All 12 Check Counts & Values (raw unpseudonymized text, post-`T=1.0` float64 softmax, `tol=3e-6` on floats):**

| Check | Kind | Candidate Actual | Rule / Baseline Limit | Passed |
| --- | --- | --- | --- | --- |
| `boundary_pos_cal_correct_count` | integer | `66` / 86 (`mean_max_prob=0.7246390920091725`) | `>= 68` (baseline `68/86`) | `False` |
| `boundary_pos_cal_sup12_correct_count` | integer | `36` / 48 (`mean_max_prob=0.7373812424742581`) | `>= 38` (baseline `38/48`) | `False` |
| `bitext_cal_correct_count` | integer | `689` / 690 (`mean_max_prob=0.977113477424977`) | `>= 687` (baseline `689/690`) | `True` |
| `pos_train_added_18_correct_count` | integer | `18` / 18 (`mean_max_prob=0.9779935172352408`) | `>= 15` (baseline `8/18`) | `True` |
| `boundary_pos_cal_sup12_conf_ge_070_count` | integer | `33` / 48 | `>= 26` (baseline `28/48`) | `True` |
| `boundary_pos_cal_sup12_conf_ge_080_count` | integer | `29` / 48 | `>= 24` (baseline `28/48`) | `True` |
| `boundary_neg_cal_pred_sup12_count` | integer | `11` / 48 | `<= 9` (baseline `9/48`) | `False` |
| `boundary_pos_cal_delta_mean_max_prob` | float | `+0.03829489685014131` | `<= 0.015 + 3e-6` (baseline `0.6863441951590312`) | `False` |
| `boundary_pos_cal_esc34_delta_mean_max_prob` | float | `+0.03758129611384764` (`correct=30/38`) | `<= 0.015 + 3e-6` (baseline `0.6709624479394273`) | `False` |
| `boundary_pos_cal_esc34_max_sup12_mass` | float | `0.4914717523196043` | `<= 0.55 + 3e-6` (baseline `0.4673615502178657`) | `True` |
| `boundary_neg_cal_max_sup12_mass` | float | `0.7451280811564883` | `<= 0.7156928153564155 + 3e-6` | `False` |
| `boundary_neg_cal_max_single_sup12_prob` | float | `0.5895935447263043` | `<= 0.5576920642670788 + 3e-6` | `False` |

---

## 4. Disclosed Limitations & Next Step

- **3 inherited noisy overlaps:** Same canonical Bitext noisy overlap (`historical_bitext_train_noisy_vs_eval_norm_overlap_count = 3`) inherited unchanged from Original Fit2's prep.
- **Comparative-only causal confound:** Warm-started from converged Original Fit2 (`f695b1fe...`) for 3 extra epochs over 11,338 train rows / 13,080 effective rows with no matched no-added-data continuation control.
- **Stop condition:** Worker A stopped cleanly after complete archival; Coordinator chooses whether any Worker C evaluation runs next.
