# Worker B Pre-Fit Readiness Review: Masked Teacher-KL (`option_a_teacher_kl`)

- **Date:** 2026-11-14
- **Branch:** `minh` (Worker A source `6b7a0c4c020fa9565b9e11ce4864c05f8895f3d5`, Worker A audit `55bb42630f20cda9b92ac85e17c747d8100002ff`, predecessor Worker B design review `206191d6f29d6330370fc216fee8f606409bf57b`)
- **Verdict:** **PASS (Pre-Fit Technical Readiness Only — NOT fit release or promotion acceptance)**
- **Authorized Fits Executed Here:** `0` (future fit `fit2-orig-teacher-kl-v1` awaits Coordinator release; CAL & Worker C holdout evaluation still gate post-fit).

---

## 1. Frozen Prep Inventory & Integrity Reconciliation

- **Prep Bundle:** `artifacts/models/candidates/run-records-fit2-orig-teacher-kl-v1-prep`
- **`prep_manifest.json` SHA-256:** `3234e31bea47402b4d6ef2da1ceb0fe3434e470c707c848dbc538918b2049286`
- **Status / Target Absence:** `status.json` = `{"status": "complete", "fits_executed": 0, "prep_archive": true}`; neither `artifacts/models/candidates/fit2-orig-teacher-kl-v1` nor `artifacts/models/candidates/run-records-fit2-orig-teacher-kl-v1` exists.
- **`14` vs `15` Reconciliation vs `v4-prep`:** Both `run-records-fit2-orig-teacher-kl-v1-prep/datasets` and `run-records-fit2-orig-ret-channel-v4-prep/datasets` contain **`15` files** (zero missing). **`14/14` data/split/extension/manifest files** are byte-for-byte identical; only `dataset_lock_manifest.json` differs (`b0a1ffa56c14417e3f63a90db5a3d3b89a6b7fbb30fabfab87683b8cb845b443` vs `a07d1342a40298b76959d431a12ea967deb3add8d18408343a5e5c78682bd074`), strictly on the `locked_at` timestamp key.
- **Mask Counts on Archived Splits:** `13,080` effective TRAIN rows (`canonical_pos=772` from `181` raw + `bitext=11,040` + `neg=1,188` -> **`13,000` anchored `m_i=1`**; `orig_ret_ch_*` `18` raw -> **`80` effective excluded `m_i=0`**). Prior sealed prep bundles, baseline `f695b1fe`, candidate models, `.gitkeep`, `.codegraph/`, and user `docs/report.template.pptx` remain untouched.

---

## 2. Code Audit Against Design (`206191d6`) & Safety Requirements

| Requirement | Verified Implementation (`6b7a0c4c`) | Result |
| --- | --- | --- |
| **Frozen Teacher Load & Alignment** | `_load_and_verify_frozen_teacher` (`train_boundary_candidate.py:797-832`) checks `model.safetensors` SHA-256 pre-loop, exact 46-label `id2label` bijection, `tokenizer.json` SHA-256 vs `init_model_dir`, sets `requires_grad_(False)` + `.eval()` + `.to(device)`, and re-verifies SHA-256 post-loop (`1333-1338`). Baseline checkpoint `reconstructed-fit2-supcon-20261113` has `46` `id2label` entries and matching tokenizer files. | **PASS** |
| **Zero Gradient & Forward KL Math** | Inside `run_fit_and_lock_candidate` (`1299-1312`), `teacher_model` runs in `.eval()` + `torch.no_grad()`, logits are `.detach()`ed, and `compute_masked_teacher_kl_loss` (`770-794`) computes forward `F.kl_div(log_softmax(student), softmax(teacher), reduction="none").sum(-1)` normalized strictly by `active_count = sum(m_i)` (finite `0.0` when `active_count == 0`). Distinct from native `0.80 * KL(uniform_46 \|\| p)` on `is_neg == 1` (`1283-1297`). | **PASS** |
| **Provenance Mask & Collation** | `build_teacher_anchor_mask` (`687-767`) reads `orig_fit2_return_contrast_extension.jsonl` (`orig_ret_ch_*` exact `sample_id` set; fail-closed on empty/duplicate/missing/unregistered/leaked IDs; no broad prefix mask, no CAL/EVAL in teacher loss). `_BoundaryDataset` (`654-684`) + `DataLoader(shuffle=True)` preserve sample-level `m_i` alignment across duplicate `4x`/`5x`/`12x` replays and multi-epoch shuffling. | **PASS** |
| **RNG / Seed Isolation Check** | Verified empirically on CUDA (`seed=42`): `_load_and_verify_frozen_teacher` + `teacher_model.eval()` forward draws **0** CPU `torch`, **0** CUDA, **0** `numpy`, and **0** Python `random` RNG states (`teacher_eval_deterministic_exact=True`, `teacher_training_flag=False`, `any_teacher_requires_grad=False`). No extra RNG wrapper needed beyond standard hardware cuDNN nondeterminism. | **PASS** |
| **Profile, Runner & Provenance** | Base profiles (`option_a`, `lr5e6`, `zero_delta_control`, `DEFAULT_PREP_PROFILE="lr5e6"`) unchanged and reject teacher-KL args. `option_a_teacher_kl` locks `epochs=3, lr=2e-5, bs=32, seed=42, fit2_supcon_energy, minT=1.0, rejector=False, alpha_kl=1.0, T_teacher=1.0, init=teacher=f695b1fe`. `run_authorized_fit` forwards all teacher kwargs (`576-598`), logs epoch KL stats + `run_config.json` + `training_lineage`, writes `candidate_model_option_a_teacher_kl`, and enforces all `12` `CAL_GUARD_DEFINITION` checks. | **PASS** |

---

## 3. Independent Verification Evidence

- **Unit & Regression Guards (Worker B independent run, `0` real fits):**
  - `tests/unit/test_orig_fit2_return_contrast_prep.py`: **`16 passed, 1 deselected`** in `135.23s` (covers all 5 `test_teacher_kl_*` tests + base `option_a` / `lr5e6` / `zero_delta_control` / CAL-guard tests).
  - `tests/unit/test_model_provenance.py tests/unit/test_task_c_evaluation_gates.py`: **`20 passed, 1 deselected`** in `3.93s`.
  - *(Worker A's broader 6-file targeted suite reported `64 passed, 2 deselected` on `6b7a0c4c`.)*
- **Synthetic Multi-Epoch Collation, Non-Dilution & RNG Probes:**
  - Confirmed 3-epoch shuffled `_BoundaryDataset` replay keeps exact `16` anchor (`4` neg + `12` pos) and `4` excluded counts per epoch; mixed `[1, 1, 0, 0, 0, 0]` batch yields identical loss (`atol=1e-7`) and canonical gradients vs clean `[1, 1]` batch with `0.0` gradients on `m=0` rows.
- **Fail-Closed Negative CLI Guards (`--validate-only`, all exit `1`):**
  - `--teacher-kl-weight 0.5` -> `ValueError`
  - `--teacher-temperature 2.0` -> `ValueError`
  - `--teacher-weights-sha256 0000...` -> `ValueError`
  - `--lr 5e-6` -> `ValueError`
  - `--profile option_a` vs locked `option_a_teacher_kl` prep -> `ValueError`
  - Colliding `--run-id fit2-orig-ret-channel-lr5e6-v1` -> `FileExistsError`
- **`--validate-only` Safe HEAD Gate:** Pre-commit check passed (`validated_only: true`, `fits_executed: 0`, `head_git_commit: 55bb42630f20cda9b92ac85e17c747d8100002ff`); post-commit check executed immediately after sealing this review commit.

---

## 4. Future Release Command & Disclosed Limits

- **Runnable Future Command (ONLY after Coordinator release):**
```powershell
.\.venv\Scripts\python.exe -m scripts.run_orig_fit2_return_contrast_fit --prep-dir "F:\Năm 3\SD\project\SupportIQ\artifacts\models\candidates\run-records-fit2-orig-teacher-kl-v1-prep" --run-id fit2-orig-teacher-kl-v1 --profile option_a_teacher_kl --epochs 3 --lr 2e-5 --batch-size 32 --seed 42 --fit-mode fit2_supcon_energy --teacher-kl-weight 1.0 --teacher-temperature 1.0 --teacher-weights-sha256 f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa --run-authorized-fit
```
- **Limits Preserved:** `alpha_kl = 1.0` at `T_teacher = 1.0` is exploratory (`40.0%` teacher accuracy on excluded `added_18`); historical `3` `bitext_train_noisy` vs eval exact-norm overlaps remain disclosed (`exclude_noisy_test_overlap: false`); technical readiness clears **execution eligibility only** — promotion remains gated by `12` CAL guards and Worker C full independent holdout evaluation.
