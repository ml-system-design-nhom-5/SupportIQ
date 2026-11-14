# Option A Continuation Fit Execution & Durable Archive (`fit2-orig-ret-channel-fit-v1`, Worker A)

- **Authorization & Provenance:** Executed per coordinator release (`task_e9b4b79312cb`) after Worker B final pre-fit `PASS` at `094531f40d632ae3bd6de262e2edf5d1daaa478b` ([prefit v3 review B](file:///F:/Năm%203/SD/project/SupportIQ/docs/audits/2026-11-14-fit2-orig-return-contrast-prefit-v3-review-b.md)), anchored to `v3-prep` commit `67b8730fab2e856f44b73ef9e016c4b12fa6989f` (`minh`, clean ancestor of `094531f40d632ae3bd6de262e2edf5d1daaa478b` with `19/19` matching dependency-closure hashes).
- **Exact Executed Command (1 Fit Only):**
  ```powershell
  .venv/Scripts/python.exe -m scripts.run_orig_fit2_return_contrast_fit --prep-dir artifacts/models/candidates/run-records-fit2-orig-ret-channel-v3-prep --run-id fit2-orig-ret-channel-fit-v1 --epochs 3 --lr 2e-5 --batch-size 32 --seed 42 --fit-mode fit2_supcon_energy --run-option-a-fit
  ```

---

## 1. Archived Candidate & Sidecar Records (MAIN)

- **Archived Candidate Directory:** `artifacts/models/candidates/fit2-orig-ret-channel-fit-v1/` (Git-ignored weights/artifacts durably stored in MAIN and inventoried)
- **Archived Sidecar Records Directory:** `artifacts/models/candidates/run-records-fit2-orig-ret-channel-fit-v1/`
- **Local Working Copy Directory:** `artifacts/evaluation/fit2_orig_ret_channel_20261114/fit2-orig-ret-channel-fit-v1/`

| Artifact | Path | Verified SHA-256 / Value |
| --- | --- | --- |
| Candidate Weights | `artifacts/models/candidates/fit2-orig-ret-channel-fit-v1/model.safetensors` | `dc3e88e713c71fe0e521a1dc5bec5831d9a0a91a83d4c3d1b413d3b1cd68e44d` (`267,967,920` bytes) |
| Tokenizer | `artifacts/models/candidates/fit2-orig-ret-channel-fit-v1/tokenizer.json` | `41b9d12a4c559e4098f30173bc0f76d092c43d7b1f873e7027da45a256f30f87` (`711,659` bytes) |
| Config | `artifacts/models/candidates/fit2-orig-ret-channel-fit-v1/config.json` | `6fa1fa9cc6a94063a977b0adaf2c9c3b296cf296d4ad9dcc6f2c52ca3bac9cb2` (`3,349` bytes) |
| Calibration Manifest | `artifacts/models/candidates/fit2-orig-ret-channel-fit-v1/calibration_manifest.json` | `e0d1bfd63f65e2e055af46a2e023ec398240008e166c2df91eb1fa5d111bb56c` (`T = 1.0`, `min_temperature = 1.0`, `selective_rejector.enabled = false`) |
| Provenance Manifest | `artifacts/models/candidates/fit2-orig-ret-channel-fit-v1/candidate_provenance_manifest.json` | `6f4287cabed4128162b1bcb68192fea815b159de016a230c3706ef376c13908d` (`provenance_passed = true`, `num_labels = 46`, `valid_46_label_bijection = true`) |
| Archive SHA Inventory | `artifacts/models/candidates/fit2-orig-ret-channel-fit-v1/archive_sha_inventory.json` | `fa4a0a458cfd288bb88a2e84aa2b24fb0b647e836a8b547a052ce2b9fb591b0f` (`6/6` files, `0` mismatches) |
| Sidecar SHA Inventory | `artifacts/models/candidates/run-records-fit2-orig-ret-channel-fit-v1/sidecar_sha_inventory.json` | `3e9726b946f22cd754354d7fe19596a41018c9ae0a63e290ab0af51c375ac812` (`40/40` files, `0` mismatches) |
| Run Config | `artifacts/models/candidates/run-records-fit2-orig-ret-channel-fit-v1/run_config.json` | `c66322b044b987290a0b82774a47e0c42abad6d8c637b2a80c719a43e28fa980` |
| Run Status | `artifacts/models/candidates/run-records-fit2-orig-ret-channel-fit-v1/status.json` | `status = "complete"`, `fits_started = 1`, `fits_completed = 1` |
| Prep Input Snapshot | `artifacts/models/candidates/run-records-fit2-orig-ret-channel-fit-v1/inputs/inputs_sha256_inventory.json` | `15/15` dataset files, `0` mismatches vs `v3-prep` (`full_train_split = 63254304...`) |
| Source Snapshot | `artifacts/models/candidates/run-records-fit2-orig-ret-channel-fit-v1/source_snapshot/` | `19/19` files exact SHA-256 match vs `v3-prep` |

---

## 2. Training Execution Summary & Runtime Identity

- **Initializer:** Original Fit2 (`artifacts/models/candidates/reconstructed-fit2-supcon-20261113/model.safetensors`, `f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa`).
- **Hyperparameters & Resource Execution:** `fit_mode="fit2_supcon_energy"`, `epochs=3`, `lr=2e-5`, `batch_size=32`, `seed=42`, `max_length=64`, `min_temperature=1.0`, `enable_selective_rejector=False`, `train_total_examples=13080`, `device=cuda` (`NVIDIA GeForce RTX 5060`, `torch=2.11.0+cu128`, `transformers=5.22.1`), `train_seconds=111.37`.
- **Epoch Losses (`fit_result.json`):**
  - Epoch 1: `mean_loss=0.36607`, `pos=0.26084`, `neg=0.00873`, `supcon=0.0965`
  - Epoch 2: `mean_loss=0.34935`, `pos=0.25266`, `neg=0.00854`, `supcon=0.08816`
  - Epoch 3: `mean_loss=0.34616`, `pos=0.25066`, `neg=0.00853`, `supcon=0.08698`
- **Post-Fit Verification (`verify_reload_from_archive`, `validate_calibration_manifest`, `audit_candidate_provenance`):** All passed (`reload_verified=true`, `valid=true`, `temperature=1.0`, `rejector_enabled=false`, `provenance_passed=true`, `num_labels=46`). No full acceptance or holdout evaluation was run (reserved for Worker C).

---

## 3. Untouched Baselines, Serving State & Mandatory Limitations

- **Untouched Anchors & Preps Verified:**
  - Serving (`artifacts/models/trained/distilbert-supportiq/model.safetensors`): `dc7af8cffb19fe7711ed5a5d0137ffff3d7d1a1f43bad5a35edff8c8de4c1302` (not promoted/activated; runtime backend/frontend/`.local`/budgets untouched).
  - Original Fit2 (`reconstructed-fit2-supcon-20261113`): `f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa`.
  - Fit1 (`reconstructed-closure-fit1-20261113`): `95a940b630f44bf8d11882a26062c857839baa2d80d188f5451d52cecc2158a6`.
  - Prep bundles: `v1-prep` (`e844861d...`), `v2-prep` (`f24fb814...`), `v3-prep` (`prep_manifest.json` `24094bc72fade9493eceb37c93a6acecd0d00e34545f95bd70d3811be9bd60b6`, `sidecar_sha_inventory.json` `376b55c16c15170d7633c4b5f9a5c835fefe1e0dd8531fbdcdfa4ca25a2c9ee2`).
- **Disclosures & Limitations:**
  - Inherited `3` `bitext_train_noisy` vs `bitext_test_6690` normalized overlaps (`exclude_noisy_test_overlap=False`) remain unchanged from Original Fit2 baseline; `0` new overlaps from the 18-row contrast delta.
  - Warm-starting `epochs=3, lr=2e-5` from `f695b1fe...` yields a comparative continuation candidate only (not a matched causal data-only control; no second fit executed). Pending Worker C independent evaluation.
