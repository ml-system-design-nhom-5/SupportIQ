# Fit2 Classifier-Only Implementation & Zero-Fit Prep Archive (`fit2-orig-classifier-head-only-v1`)

- **Date:** 2026-11-14
- **Author:** Worker A (`task_id=task_580344b6d0ba`, `dispatch_id=ctx_a467eb993325`)
- **Design Basis:** Worker B proposal PASS ([2026-11-14-fit2-classifier-only-proposal-review-b.md](file:///F:/Năm%203/SD/project/SupportIQ/docs/audits/2026-11-14-fit2-classifier-only-proposal-review-b.md), `HEAD=a7fa5adfdd4b720caf48eabf596717bcec72e621`)
- **Execution Mode:** **PREP + UNIT TEST ONLY (`fits_executed: 0`, Attempt `1/2` unspent pending Worker B review + Coordinator release)**
- **Global Budget Cap:** `0/2` additional attempts used (`.local/training-cap-20261114.json` untouched)
- **Frozen Source/Test Commit:** `a433e9fa7ecaab0d2edfdbd46e834b9492772762` (branch `minh`)

## 1. Implementation Summary (`option_a_classifier_head_only_v1`)

Implemented the explicit, isolated opt-in classifier-head-only profile (`a433e9fa7ecaab0d2edfdbd46e834b9492772762`) leaving `DEFAULT_PREP_PROFILE = "lr5e6"` and all prior profiles (`option_a`, `lr5e6`, `option_a_teacher_kl`, `option_a_teacher_kl_deterministic`) unchanged:

1. **`pipeline/training/train_boundary_candidate.py`** (SHA-256 `950929005e687ed8ee591c5d4b6a89f3bb3715fdd726d9da3ae8d60300f30f87`):
   - Added `VALID_TRAINABLE_SCOPES = ("all", "classifier_head_only")`.
   - Added `_configure_trainable_scope`, `_snapshot_frozen_component_hashes`, `_tensor_bytes_sha256`, and `_set_epoch_module_modes`:
     - Under `trainable_scope="classifier_head_only"`, freezes all parameters (`66,953,472`) except exact `["classifier.weight", "classifier.bias"]` (`35,374` trainable params of `66,988,846` total), enforcing `expected_trainable_param_count=35374` and `expected_frozen_param_count=66953472`.
     - Per-epoch `_set_epoch_module_modes` replaces recursive `model.train()` with `model.eval()` followed by `model.classifier.train(True)`, keeping `distilbert`, `pre_classifier`, and `dropout` (`p=0.2`) deterministically in `.eval()` (zero dropout RNG consumption).
     - Builds `AdamW` and applies `clip_grad_norm_(..., 1.0)` strictly over `trainable_params` (`classifier.weight`, `classifier.bias`).
     - Leaves `L_pos` (`label_smoothing=0.03`) and `L_neg` (`0.80 * l_kl + 3.0 * l_ceil + 0.25 * l_eng`) completely unchanged; omits `output_hidden_states` / `SupCon` under frozen encoder (zero head-gradient equivalence verified at `0.0`); forbids any Teacher-KL / tether / rejector.
     - Snapshots bit-identical tensor+buffer hashes pre- vs post-loop and verifies `p.grad is None` on all frozen params, recording component freeze hashes, `unfrozen_transformer_layers: 0`, and `post_fit_freeze_verified: true` in `candidate_provenance_manifest.json`.

2. **`scripts/run_orig_fit2_return_contrast_prep.py`** (SHA-256 `9262284a69b4db0875958bcd5956ed6b956576f092ee52576ba3be69237e59ec`):
   - Added `"option_a_classifier_head_only_v1"` (`lr=1e-4`, `epochs=2`, `weight_decay=0.01`, `batch_size=32`, `seed=42`, `fit_mode="fit2_supcon_energy"`, `min_temperature=1.0`, `enable_selective_rejector=False`, `trainable_scope="classifier_head_only"`, `feature_dropout_eval_mode=True`, `expected_trainable_param_count=35374`, `expected_frozen_param_count=66953472`).
   - Added `_snapshot_init_freeze_component_hashes` (read-only `.eval()`, zero optimizer steps) to lock initial frozen tensor + component hashes in `prep_manifest.json["classifier_head_only_config"]` alongside `budget_attempt_label="Attempt_1_of_2_pending_coordinator_release"` (`budget_consumed_by_prep=0`).

3. **`scripts/run_orig_fit2_return_contrast_fit.py`** (SHA-256 `02065dde9d321a7fad40ef27a1c726e21e6867e86f9694d2a54674af4db52d9e`):
   - Added `--weight-decay`, `--trainable-scope`, `--feature-dropout-eval-mode` CLI flags and fail-closed mutual isolation in `validate_profile_settings`, `verify_locked_prep_bundle`, `run_authorized_fit`, and post-fit provenance verification (`post_fit_frozen_tensors_sha256 == initial_frozen_tensors_sha256`).

4. **`tests/unit/test_orig_fit2_return_contrast_prep.py`**:
   - Added 5 unit tests covering exact `35,374 / 66,953,472` counts + component freeze hashes + `AdamW` exact parameter list (no step) + non-zero `L_pos+L_neg` head grads + `p.grad is None` frozen check, deterministic `.eval()` dropout + zero RNG consumption + mode guards, inactive SupCon `0.0` head-grad equivalence, profile isolation + negative guards, and prep archival / `--validate-only` (`0` fits) / kwargs forwarding.

## 2. Archived Zero-Fit Prep Bundle & Initial Freeze Checksums

- **Prep Bundle Path:** [run-records-fit2-orig-classifier-head-only-v1-prep](file:///F:/Năm%203/SD/project/SupportIQ/artifacts/models/candidates/run-records-fit2-orig-classifier-head-only-v1-prep)
- **Target Future Run ID (NOT Executed):** `fit2-orig-classifier-head-only-v1`
- **`status.json`:** `{"status": "complete", "fits_executed": 0, "prep_archive": true, "budget_attempt_label": "Attempt_1_of_2_pending_coordinator_release", "budget_consumed_by_prep": 0}`
- **`prep_manifest.json`:** `schema_version="orig_fit2_return_contrast_prep.v4"`, `git_commit="a433e9fa7ecaab0d2edfdbd46e834b9492772762"`, SHA-256 `44432c82091c823f9df0a23a3c9038ac3fdd7068ff2f2f8229d77b15c4695fc6`
- **`sidecar_sha_inventory.json`:** SHA-256 `787d0b7c4b3b672775f159f3a0a321494731067bc1f18382cb511bbaadaf6672` (`39/39` entries verified, `0` mismatches)
- **Dataset Parity vs `run-records-fit2-orig-ret-channel-v4-prep/datasets`:** `15` files total; `14/14` data/split/extension files byte-identical, only `dataset_lock_manifest.json` differs (`2d05a04176ba1e166c38d2b6c90a73dc5e82fce6e08afd021d2cbdb67e93e041` vs `a07d1342a40298b76959d431a12ea967deb3add8d18408343a5e5c78682bd074`). Counts: `domain_pos_train=199` (`18` added), `full_train_split_rows=11338`.
- **Init Baseline (`f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa`, teacher unused):**
  - `initial_frozen_tensors_sha256`: `3b8b48f556d4f2f0c99dad938e470d6caa2184650f09f3af7c0bfb164364d31d`
  - `distilbert.embeddings`: `9662676024c6a6cb5fca578d3466f5e9c43ca91d39c98e396ffb900532c07262`
  - `distilbert.transformer.layer.0`: `4cdcd10c2469d3de420d0bb25ead6008096a4206b0f1d748613cd8d782b1bcee`
  - `distilbert.transformer.layer.1`: `a0d27f1fc52822d252b8c4146254806665eea459a8d02a428a6090d74849301a`
  - `distilbert.transformer.layer.2`: `febe747d5591c061c230d432e43077d3c63ac91c2742ef5aadb14c16715a9c61`
  - `distilbert.transformer.layer.3`: `e3d9604616019ddce3b6acd5146c3b1820ef5b21bae592601224006ef8afcc68`
  - `distilbert.transformer.layer.4`: `a72929efd64a023781ae687d245529d1ff264526a63066705c3735df681537d4`
  - `distilbert.transformer.layer.5`: `0df9904d111f7f430858ccba2dfa5339c49a6747b24dc77bd578994219b1fc1a`
  - `pre_classifier`: `ab5fb6bded85a99fdfb14ed784c28ebaf061bcdb9ffe2e81f35706ca28103c58`
  - `buffers`: `26ef7d8b98537c99d82b8d135adab799031872d26387aa5545315a0d87e4c57f`
- **No Future Fit Artifacts Created:** Verified `fit2-orig-classifier-head-only-v1`, `run-records-fit2-orig-classifier-head-only-v1`, and `artifacts/evaluation/fit2_orig_ret_channel_20261114/fit2-orig-classifier-head-only-v1` all `false`.

## 3. Verification Executed (Zero Real Fits)

1. **Unit Regression Suite (on frozen source/test commit):**
   - `.\.venv\Scripts\python.exe -m pytest tests/unit/test_orig_fit2_return_contrast_prep.py tests/unit/test_boundary_contrast_fit.py tests/unit/test_faithful_fit2_entrypoint.py tests/unit/test_gate_contract_b.py tests/unit/test_task_c_evaluation_gates.py tests/unit/test_model_provenance.py -v`
   - Result: **`74 passed, 2 deselected in 291.29s`** (`5` new classifier-head-only tests + `69` existing tests).
2. **Fail-Closed Negative CLI & Collision Checks (`7/7` exited `1`):**
   - `wrongScope` (`--trainable-scope all`): exit `1`
   - `missingEvalFlag` (omitted `--feature-dropout-eval-mode`): exit `1`
   - `wrongWD` (`--weight-decay 0.0`): exit `1`
   - `wrongLR` (`--lr 2e-5`): exit `1`
   - `wrongEpochs` (`--epochs 3`): exit `1`
   - `wrongProfile` (`--profile option_a` against head-only prep): exit `1`
   - `collision` (re-archiving prep bundle): exit `1` (`FileExistsError`)

## 4. Exact Quoted Future Fit CLI (NOT EXECUTED)

Recorded verbatim in `prep_manifest.json` (`execution_plan.planned_cli`), pending Worker B pre-fit PASS and explicit Coordinator Attempt `1/2` release:

```powershell
.\.venv\Scripts\python.exe -m scripts.run_orig_fit2_return_contrast_fit --prep-dir "F:\Năm 3\SD\project\SupportIQ\artifacts\models\candidates\run-records-fit2-orig-classifier-head-only-v1-prep" --run-id fit2-orig-classifier-head-only-v1 --profile option_a_classifier_head_only_v1 --epochs 2 --lr 1e-4 --batch-size 32 --seed 42 --fit-mode fit2_supcon_energy --weight-decay 0.01 --trainable-scope classifier_head_only --feature-dropout-eval-mode --run-authorized-fit
```

## 5. Design Disclosures & Early-Stop Boundaries

- **Exploratory Multi-Factor Scope:** Compares architectural head-only constraint + matched locked recipe (`AdamW lr=1e-4`, `epochs=2`, `weight_decay=0.01`) as an exploratory candidate, not a single-factor randomized causal isolation.
- **Frozen Feature Geometry Risk:** Worker B read-only `f695b1fe` eval-feature audit observed `8/18` `added_18` 1-NN/centroid match (`8/10` `return_policy`, `0/8` `return_product_in_store`). While this exposes a high risk of linear-separability ceiling, it does not prove impossibility; however, per Worker B / Coordinator rules, failure on **any** CAL accuracy or separation gate in Attempt `1/2` triggers a hard **EARLY STOP** leaving Attempt `2/2` unspent.
- **Inherited Limits Preserved:** `12` CAL guard checks unchanged, `46` labels preserved, `exclude_noisy_test_overlap: false` (`3` historical `bitext_train_noisy` overlaps preserved).
