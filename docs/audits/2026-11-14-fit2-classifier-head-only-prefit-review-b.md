# Fit2 Classifier-Head-Only Pre-Fit Review (Worker B)

- **Verdict:** **`PASS`** (pre-fit code, freeze contract, and prep bundle verified for Attempt `1/2`; **`0` fits executed**, no optimizer updates, Coordinator explicit release required; hard **`EARLY STOP`** rule if `1/2` fails accuracy or separation gates)
- **Reviewed Commits & Budget Lock:**
  - Worker B approved design: `a7fa5adfdd4b720caf48eabf596717bcec72e621`
  - Worker A frozen implementation: `a433e9fa7ecaab0d2edfdbd46e834b9492772762`
  - Worker D doc-only cleanup plan: `da36647a5bc4e9616a3c2dfb658b5d1f2d3e0ac9` (`docs/audits/2026-11-14-code-cleanup-preparation-d.md` only; `0` active code edits)
  - Worker A prep audit (`docs/audits/2026-11-14-fit2-classifier-head-only-prep-a.md`): `6e912e0b3b88806bdffda68013b6d5a8872b8964`
  - Global budget: [.local/training-cap-20261114.json](file:///F:/Năm%203/SD/project/SupportIQ/.local/training-cap-20261114.json) untouched (`additional_attempt_limit = 2`, `additional_attempts_started = 0`; Coordinator counts optimizer start even on crash).

---

## 1. Prep Bundle Reconciliation (`run-records-fit2-orig-classifier-head-only-v1-prep`)

- **`prep_manifest.json` SHA-256:** `44432c82091c823f9df0a23a3c9038ac3fdd7068ff2f2f8229d77b15c4695fc6` (`schema_version=orig_fit2_return_contrast_prep.v4`, `git_commit=a433e9fa7ecaab0d2edfdbd46e834b9492772762`, `authorized_to_train_now=false`, `fits_executed=0`).
- **`sidecar_sha_inventory.json` SHA-256:** `787d0b7c4b3b672775f159f3a0a321494731067bc1f18382cb511bbaadaf6672` — **`39/39` verified**, `0` mismatches.
- **`status.json`:** `complete`, `fits_executed=0`, `prep_archive=true`, `budget_attempt_label="Attempt_1_of_2_pending_coordinator_release"`, `budget_consumed_by_prep=0`.
- **Initial Freeze SHA (`f695b1fe`):** `initial_frozen_tensors_sha256 = 3b8b48f556d4f2f0c99dad938e470d6caa2184650f09f3af7c0bfb164364d31d` (embeddings, layers `0..5`, `pre_classifier`, and `buffers` hashes locked).
- **Dataset Parity vs `run-records-fit2-orig-ret-channel-v4-prep`:** `15` files total; `14/14` data/split/extension files byte-identical, only `dataset_lock_manifest.json` differs (`locked_at` key only). Future output dirs (`fit2-orig-classifier-head-only-v1`, `run-records-fit2-orig-classifier-head-only-v1`, `artifacts/evaluation/fit2_orig_ret_channel_20261114/fit2-orig-classifier-head-only-v1`) absent; prior models/preps, `docs/report.template.pptx`, and `.codegraph/` intact.

---

## 2. Implementation, Freeze & Isolation Audit (`a7fa5adf..a433e9fa`)

| File | Verified SHA-256 | Verified Behavior & Guards |
|---|---|---|
| `pipeline/training/train_boundary_candidate.py` | `950929005e687ed8ee591c5d4b6a89f3bb3715fdd726d9da3ae8d60300f30f87` | Freezes `66,953,472` params+buffers and selects strictly `classifier.weight`, `classifier.bias` (`35,374`); `_set_epoch_module_modes` replaces recursive `model.train()` with `model.eval()` + `model.classifier.train(True)` (deterministic `dropout` off, `trainable_scope="all"` unchanged); `AdamW(opt_params, lr=1e-4, weight_decay=0.01)` & `clip_grad_norm_(opt_params, 1.0)` over `35,374` params only; `L_pos + L_neg` unchanged (`use_supcon=False` omits redundant upstream SupCon; no KL/tether/rejector); post-loop fail-closed check enforces `p.grad is None` and bit-identical frozen tensor+buffer SHA-256 pre- vs post-loop. |
| `scripts/run_orig_fit2_return_contrast_prep.py` | `9262284a69b4db0875958bcd5956ed6b956576f092ee52576ba3be69237e59ec` | Registers isolated `option_a_classifier_head_only_v1` (`lr=1e-4`, `epochs=2`, `weight_decay=0.01`, `bs=32`, `seed=42`, `minT=1.0`, `rejector=OFF`, `35,374/66,953,472`); snapshots `f695b1fe` initial component+buffer freeze SHAs; keeps `DEFAULT_PREP_PROFILE="lr5e6"`, all base profiles, `12` CAL guards, and `3` noisy overlaps unchanged. |
| `scripts/run_orig_fit2_return_contrast_fit.py` | `02065dde9d321a7fad40ef27a1c726e21e6867e86f9694d2a54674af4db52d9e` | Enforces fail-closed mutual isolation on `--weight-decay`, `--trainable-scope`, `--feature-dropout-eval-mode`; forwards exact `trainer_kwargs`; verifies post-fit lineage `post_fit_frozen_tensors_sha256 == initial_frozen_tensors_sha256`, `unfrozen_transformer_layers == 0`, archive/sidecar SHAs, and `ModelContainer` reload parity. |

---

## 3. Independent Probes, Guards & Focused Tests (`0` Optimizer Steps)

- **Real `f695b1fe` CUDA Probe (`0` steps):**
  - `_configure_trainable_scope`: `trainable_param_count=35374`, `frozen_param_count=66953472`, names `["classifier.weight", "classifier.bias"]`.
  - CUDA `_snapshot_frozen_component_hashes` == `3b8b48f556d4f2f0c99dad938e470d6caa2184650f09f3af7c0bfb164364d31d`, matching all `9` manifest component/buffer SHAs byte-for-byte.
  - `AdamW` covers only `[classifier.weight, classifier.bias]`; per-epoch mode lock overrides prior `model.train()` with `distilbert`, `pre_classifier`, `dropout` `.eval()` and `classifier` `.train()`; `trainable_scope="all"` retains recursive `.train()`.
  - Deterministic forward repeat `max_diff=0.000e+00`; `L_pos+L_neg` vs `+SupCon` classifier grad diff `(0.000e+00, 0.000e+00)`; `grad_norm_w=12.5746`, `grad_norm_b=0.6517`; all frozen `p.grad is None`; RNG states (`cpu`, `cuda`, `np`, `py`) unchanged.
- **Negative CLI Guards (`8/8` exited `1`):** `wrong_scope_all`, `missing_eval_dropout_flag`, `wrong_weight_decay`, `wrong_lr_2e5`, `wrong_epochs_3`, `wrong_profile_option_a`, `teacher_kl_on_head_only`, `existing_run_id_collision`.
- **Focused `pytest` (`tests/unit/test_orig_fit2_return_contrast_prep.py`, `tests/unit/test_model_provenance.py`, `tests/unit/test_task_c_evaluation_gates.py`):** `46 passed, 2 deselected in 140.02s`.
- **Pre-Commit `--validate-only` (`HEAD=6e912e0b3b88806bdffda68013b6d5a8872b8964`):** exited `0` (`validated_only=true, fits_executed=0`).

---

## 4. Quoted Future Execution CLI (Not Executed)

```powershell
.\.venv\Scripts\python.exe -m scripts.run_orig_fit2_return_contrast_fit `
  --prep-dir "F:\Năm 3\SD\project\SupportIQ\artifacts\models\candidates\run-records-fit2-orig-classifier-head-only-v1-prep" `
  --run-id fit2-orig-classifier-head-only-v1 `
  --profile option_a_classifier_head_only_v1 `
  --epochs 2 `
  --lr 1e-4 `
  --batch-size 32 `
  --seed 42 `
  --fit-mode fit2_supcon_energy `
  --weight-decay 0.01 `
  --trainable-scope classifier_head_only `
  --feature-dropout-eval-mode `
  --run-authorized-fit
```

---

## 5. Limits & Early-Stop Rule

- **Feature Geometry Risk (`0/8`):** Frozen `f695` `h_pre` gives `0/8` centroid/1-NN match on added `return_product_in_store` under `0`-row CAL slack.
- **Exploratory Multi-Factor Scope (`n=1`):** Bundles architecture freeze (`35,374` head-only params) with matched recipe (`lr=1e-4, epochs=2, wd=0.01`); evaluates Attempt `1/2` viability, not a single-factor causal isolation claim.
- **Inherited Limits:** Retains `3` historical noisy test-overlap IDs (`exclude_noisy_test_overlap=false`) and unchanged `12`-check CAL guard.
- **Hard `EARLY STOP`:** Any failure on accuracy or separation CAL gates in Attempt `1/2` stops immediately with Attempt `2/2` left unspent; no automatic Attempt `2`, weight tether, LR sweep, or out-of-budget optimizer runs permitted.
