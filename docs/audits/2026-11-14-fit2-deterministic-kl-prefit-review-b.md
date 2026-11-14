# Fit2 Deterministic Teacher-KL Pre-Fit Review (Worker B)

- **Verdict:** `PASS` (pre-fit implementation & prep bundle verified; **0 fits executed**, fit execution remains unreleased pending Coordinator authorization)
- **Reviewed Commits:**
  - Worker B approved spec: `07748ac47ad2423a47fbbb9580ed4b425c057c20`
  - Worker A implementation: `e82ec7d6bd3bcf18fe6227837fe2c42845cab943`
  - Worker A prep audit (`docs/audits/2026-11-14-fit2-deterministic-kl-prep-a.md`): `65aaae7a626e8c994829580a82cc32f66fc51843`
- **Active Policy Stance:** `eval_no_dropout_autograd_enabled` fixes step-0 dropout noise on the Teacher-KL regularizer via a separate `model.eval()` student forward with autograd enabled, preserving base stochastic training and keeping all prior profiles untouched.

---

## 1. Single-Delta Implementation & Isolation Verification (`07748ac4..e82ec7d6`)

| File | Verified SHA-256 | Verified Contract & Isolation |
|---|---|---|
| `pipeline/training/train_boundary_candidate.py` | `7f160e637edc3c98b5762d938fe7dd2e38a0b2545f937d1bd6b999ffb32a2c9b` | `VALID_TEACHER_STUDENT_ANCHOR_MODES` (`train_stochastic`, `eval_no_dropout_autograd_enabled`); `_forward_student_logits_eval_mode` snapshots/restores per-module `.training` flags in `try/finally` under `model.eval()` + `torch.enable_grad()`; `(anchor_mask_t > 0).any()` skips extra forward when zero batch anchors are active; base stochastic `pos_ce + supcon + neg` runs before Teacher-KL; lineage records `"teacher_student_anchor_mode"`. |
| `scripts/run_orig_fit2_return_contrast_prep.py` | `d0822e334e5a08789ed491d78d8002793f9807ebcb0bcb641b7b9906e44f96d1` | Adds isolated profile `option_a_teacher_kl_deterministic` (`alpha_kl=1.0`, `T_teacher=1.0`, `lr=2e-5`, `epochs=3`, `batch_size=32`, `seed=42`, `fit2_supcon_energy`, `min_temperature=1.0`, `enable_selective_rejector=False`, `init=teacher=f695b1fe...`); leaves `option_a`, `lr5e6`, `zero_delta_control`, and `option_a_teacher_kl` unchanged; preserves 12 CAL gates and `exclude_noisy_test_overlap=false` (`3` historical IDs). |
| `scripts/run_orig_fit2_return_contrast_fit.py` | `cc8a89dd2b07416524dbb9f2e47f00b58b0f8c32617bb7c5119417b4330c4fb6` | Adds `--teacher-student-anchor-mode`; enforces strict bidirectional isolation between `option_a_teacher_kl` (`train_stochastic` only) and `option_a_teacher_kl_deterministic` (`eval_no_dropout_autograd_enabled` only); validates locked prep manifest, `run_config.json`, `trainer_kwargs`, and post-fit lineage. |
| `tests/unit/test_orig_fit2_return_contrast_prep.py` | `HEAD=65aaae7a` | Adds `_make_synthetic_dropout_classifier` and 5 `test_deterministic_kl_*` specs covering identity KL/grad, perturbed autograd + teacher freeze, RNG + nested mode restoration, CLI profile isolation, and `active_count == 0` guard. |

---

## 2. Prep Bundle Reconciliation (`run-records-fit2-orig-deterministic-kl-v1-prep`)

- **`prep_manifest.json` SHA-256:** `a2b1983dcaa328423b182ec9ebcaeb969ee5e74330fd13394f01af68426d6fb6` (`git_commit=e82ec7d6bd3bcf18fe6227837fe2c42845cab943`, `schema_version=orig_fit2_return_contrast_prep.v4`, `authorized_to_train_now=false`, `fits_executed=0`, `optimizer_invoked=false`).
- **`sidecar_sha_inventory.json` SHA-256:** `773c354f760e234cc3c6569a4e8203465bc9da31b34638b165394e66b1943515` — **`39/39` entries verified**, `0` missing, `0` SHA-256 mismatches.
- **Dataset Parity vs `run-records-fit2-orig-ret-channel-v4-prep`:** `14/15` dataset files byte-identical; only `dataset_lock_manifest.json` differs (`locked_at` timestamp key only). Canonical anchor split unchanged (`13,000` anchored TRAIN rows; `80` masked-off `orig_ret_ch_*` rows from `18` raw rows).
- **Clean Output Surface & Sealed Asset Preservation:** Future run paths (`artifacts/models/candidates/fit2-orig-deterministic-kl-v1`, `artifacts/models/candidates/run-records-fit2-orig-deterministic-kl-v1`, `artifacts/evaluation/fit2_orig_ret_channel_20261114/fit2-orig-deterministic-kl-v1`) do not exist. Prior sealed checkpoints/preps (`reconstructed-fit2-supcon-20261113`, `fit2-orig-teacher-kl-v1`, `run-records-fit2-orig-ret-channel-v4-prep`), `docs/report.template.pptx`, and `.codegraph/` remain intact.

---

## 3. Independent Runtime Probes, Negative CLI Guards & Unit Tests

- **Real CUDA DistilBERT (`f695b1fe...`) Autograd / RNG / Mode Probes (`0` optimizer steps):**
  - Identity (`student == teacher`): stochastic forward gave `KL=7.65390024e-02`, `grad_norm=1.71194572e+01`; deterministic `_forward_student_logits_eval_mode` gave `KL=3.10440873e-09`, `grad_norm=5.46709180e-06` (>3.1M× smaller gradient noise, matching fp32 kernel precision).
  - RNG invariance across deterministic forward + `.backward()`: `cpu=True`, `cuda=True`, `np=True`, `py=True`.
  - Asymmetric class-weight perturbation (`+0.25/-0.25`): `det_kl=6.29421692e+01`, `repeat_max_diff=0.00000000e+00`, `cls_grad_norm=1.49159269e+01` (`requires_grad=True`), `teacher_grad_count=0`.
  - Empty anchor mask (`[0, 0, 0, 0]`): `det_kl=0.00000000e+00`, `active=0`, `isfinite=True`.
  - Exception safety: injected `RuntimeError` inside forward cleanly restored mixed nested `train()`/`eval()` flags.
- **Fail-Closed Negative CLI Guards (`7/7` exited `1`):**
  - Missing `--teacher-student-anchor-mode` on deterministic profile (`exit=1`: requires `eval_no_dropout_autograd_enabled`, got `None`)
  - Deterministic profile + `--teacher-student-anchor-mode train_stochastic` (`exit=1`)
  - Stochastic `option_a_teacher_kl` + `--teacher-student-anchor-mode eval_no_dropout_autograd_enabled` (`exit=1`)
  - Deterministic prep dir + `--profile option_a_teacher_kl` (`exit=1`)
  - Wrong `--teacher-kl-weight 2.0` (`exit=1`)
  - Wrong `--teacher-temperature 2.0` (`exit=1`)
  - Existing `--run-id fit2-orig-teacher-kl-v1` collision (`exit=1`, `FileExistsError`)
- **Focused Unit Suite:**
  - `.\.venv\Scripts\python.exe -m pytest tests/unit/test_orig_fit2_return_contrast_prep.py tests/unit/test_model_provenance.py tests/unit/test_task_c_evaluation_gates.py -q` -> `41 passed, 2 deselected in 134.26s`.
- **Pre-Commit `--validate-only` (`HEAD=65aaae7a626e8c994829580a82cc32f66fc51843`):**
  - Exited `0` with `"validated_only": true, "fits_executed": 0`.

---

## 4. Quoted Future Execution CLI (Not Executed Here)

Exact `execution_plan.planned_cli` from `prep_manifest.json` (run only upon explicit Coordinator release):

```powershell
.\.venv\Scripts\python.exe -m scripts.run_orig_fit2_return_contrast_fit `
  --prep-dir "F:\Năm 3\SD\project\SupportIQ\artifacts\models\candidates\run-records-fit2-orig-deterministic-kl-v1-prep" `
  --run-id fit2-orig-deterministic-kl-v1 `
  --profile option_a_teacher_kl_deterministic `
  --epochs 3 `
  --lr 2e-5 `
  --batch-size 32 `
  --seed 42 `
  --fit-mode fit2_supcon_energy `
  --teacher-kl-weight 1.0 `
  --teacher-temperature 1.0 `
  --teacher-weights-sha256 f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa `
  --teacher-student-anchor-mode eval_no_dropout_autograd_enabled `
  --run-authorized-fit
```

---

## 5. Limits & Non-Guarantees

- Single exploratory budget (`n=1`, `alpha_kl=1.0`, `T_teacher=1.0`, `seed=42`).
- Preserves the `3` historical noisy test-overlap IDs (`exclude_noisy_test_overlap=false`) for apples-to-apples historical comparison.
- Removing step-0 dropout bias fixes the verified stochastic Teacher-KL drift mechanism, but does not guarantee CAL gate or holdout pass.
