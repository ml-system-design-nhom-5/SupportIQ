# Fit2 Final Attempt (2/2) Pre-Implementation Design Review (Worker B)

- **Date (UTC):** `2026-11-14T17:02:00Z` | **Branch:** `minh` | **Base HEAD:** `2f6ff96d55a21cae0df6f6bbcb3aebd483549240`
- **Role / Task:** Worker B (`task_097c8b16505c`, `dispatch_id=ctx_66fcbbc11b05`)
- **Mode:** Design Review + Read-Only Probes Only (`0` optimizer steps, `0` toy fits, `0` real fits, `0` temperature fits, `0` holdouts read)
- **Budget Status (`.local/training-cap-20261114.json`):** `additional_attempt_limit = 2`, `additional_attempts_started = 1` (`fit2-orig-classifier-head-only-v1`, `c0908ffb...`, `CAL_GUARD_REJECT_DO_NOT_PROMOTE`), **1 remaining final optimizer attempt (`Attempt 2/2`)**

---

## 1. Verdict: **CONDITIONAL `PASS` FOR ONE FINAL ATTEMPT (`2/2`)**

Authorize prep + implementation + unit tests + **at most one (1) optimizer attempt** using **`pre_classifier_and_classifier`** (`625,966` trainable params, `66,362,880` frozen encoder+embedding params) initialized from Original Fit2 (`f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa`), pending clean Worker A prep/code review before any `.fit()` starts.

### Why `pre_classifier_and_classifier` (vs Halt or Classifier-Only)
1. **Fixes the exact `h_pre` collapse that crippled Attempt `1/2` (`c0908ffb`):**
   Read-only inspection of `f695b1fe` across TRAIN (`18` added + `11,221` canonical positive) and CAL (`86` `pos_cal` + `48` `neg_cal`) proves frozen `pre_classifier + ReLU` (`h_pre`) compressed the `+8` added `return_product_in_store` (`ris`) rows onto `return_policy` (`rp`) and canonical CAL neighbors:
   - `cos(add_ris, add_rp)`: `0.7945` in raw `h_cls` (`distilbert(x)[:, 0]`) $\rightarrow$ **`0.9304`** in `h_pre`
   - `cos(add_ris, canon_rp)`: `0.4961` in `h_cls` $\rightarrow$ **`0.8214`** in `h_pre`
   - `cos(canon_ris, canon_rp)`: **`0.0472`** (orthogonal) in `h_cls` $\rightarrow$ **`0.4422`** in `h_pre`
   - `added_ris` vs non-RIS `pos_cal` max cosine: `0.8055` (`mean_top1 = 0.6317`) in `h_cls` $\rightarrow$ **`0.9319`** (`mean_top1 = 0.7360`) in `h_pre`
   Under `c0908ffb` (`classifier_head_only`), every `classifier.weight` row shifted `~0.20` L2 (overall `27.48%`, `1.2697` L2), pushing `added_ris` mean true-class prob only `0.0166 -> 0.0673` (`1/8`), flipping `cls_e34_avonl_cal_1_af025937dd54` (`availability_online` `0.1254 -> 0.0997` vs `return_product_in_store` `0.0760 -> 0.1419`), and pushing `bnd_neg_homonym_cal_0_b32c79aceec4` (`return_policy` `0.0447 -> 0.0516`, rank 2 $\rightarrow$ 1) across the `sup12` ceiling (`10 > 9`).
2. **Adds `17.7x` piecewise-linear gating capacity with `0.0` encoder forgetting:**
   `625,966` (`768` ReLU half-spaces + `46` head vectors) operate directly on uncollapsed `h_cls`, while `66,362,880` (`99.0656%`) embedding + 6-layer transformer weights remain bit-identical (`0.0` drift vs `2.22–2.31` L2 encoder drift in full-backbone fits).

### Remaining Failure Risk (Why Outcome Is Uncertain)
- Even in `h_cls`, `added_ris` (`n=8`) has `0/8` 1-NN to `canon_ris` (`cos(add_ris, canon_ris) = -0.0427`; nearest canonical neighbors: `return_policy x4`, `exchange_product_in_store x1`, `human_agent x1`, `pay x1`, `return_product x1`), and `max_cos_to_neg_cal = 0.8639` (`mean_top1 = 0.6250`).
- Read-only step-0 full-epoch gradient over `pre_classifier + classifier` (`13,080` effective rows) shows `g_add18_norm = 0.037557 > g_canon_norm = 0.030849` with near-zero alignment (`cos = +0.0286`), while `-g_all` aligns negatively with `pos_cal` confidence (`cos(-g, g_pcal_mmp) = -0.1333`) and `neg_cal` `sup12` mass (`cos(-g, g_ncal_sup12) = -0.1619`). Thus, `pre_classifier + classifier` is NOT guaranteed to clear all 12 CAL gates; however, it is the sole scientifically unconfounded final test of whether `f695b1fe`'s frozen `h_cls` can absorb `+18` without breaking CAL.

---

## 2. Exact Architecture, Mode Semantics, & Parameter Breakdown

From `DistilBertForSequenceClassification.forward` inspected on `reconstructed-fit2-supcon-20261113` (`f695b1fe...`):
```text
input_ids, attention_mask
  -> distilbert(...) [0][:, 0]          # h_cls (768d)       [FROZEN, .eval()]
  -> pre_classifier(h_cls)               # Linear(768 -> 768) [TRAINABLE, .train()]
  -> nn.ReLU()                           # h_pre (768d)
  -> dropout(p=0.2, inplace=False)       # [FORCED .eval() -> identity]
  -> classifier(...)                     # Linear(768 -> 46)  [TRAINABLE, .train()]
```

| Component | Tensors (+Buffers) | Params | Share | Mode During Fit | `requires_grad` |
|---|---|---|---|---|---|
| `distilbert.embeddings` | `4` (`+1` `position_ids`) | `23,835,648` | `35.5815%` | `.eval()` (dropout OFF) | `False` (frozen) |
| `distilbert.transformer.layer.0..5` | `96` (`16` $\times$ `6`) | `42,527,232` | `63.4841%` | `.eval()` (dropout OFF) | `False` (frozen) |
| **Total Frozen** | **`100` (`+1` buffer)** | **`66,362,880`** | **`99.065567%`** | **`.eval()` (no blanket `model.train()`)** | **`False`** |
| `pre_classifier` (`weight`, `bias`) | `2` | `590,592` | `0.881627%` | `.train()` | `True` |
| `classifier` (`weight`, `bias`) | `2` | `35,374` | `0.052806%` | `.train()` | `True` |
| `dropout` (`Dropout(p=0.2)`) | `0` | `0` | `0.000000%` | **`.eval()` (`feature_dropout_eval_mode=True`)** | `—` |
| **Total Trainable (`pre_classifier + classifier`)** | **`4`** | **`625,966`** | **`0.934433%`** | **Explicit per-module** | **`True`** |
| **Baseline Attempt 1 (`classifier_head_only`)** | `2` trainable / `102` frozen | `35,374` / `66,953,472` | `0.0528%` / `99.9472%` | `classifier.train()`, rest `.eval()` | `classifier.*` only |

- **Why `dropout.eval()` (`feature_dropout_eval_mode=True`):** Empirically measured on a `32`-row training batch of `f695b1fe`: enabling `dropout(p=0.2)` injects `max_diff = 1.323954` (`std = 0.334634`) stochastic logit noise, whereas `distilbert.eval()` + `dropout.eval()` + `pre_classifier.train()` + `classifier.train()` yields `repeat_forward_max_diff = 0.0` and `rng_preserved_before_after_forward = true`, preventing noise-induced variance on `80` added effective rows and keeping training aligned with deterministic `eval()` calibration (`T = 1.0`). Note that `ReLU` activation sparsity (`> 0`) on `f695b1fe` is already `0.5111` (`added_18`), `0.5451` (`pos_cal`), and `0.2803` (`neg_cal`).

---

## 3. Loss & Autograd Equivalence Proof (`L_pos + L_neg` Only; `SupCon` Exact `0`)

Verified empirically via autograd on shuffled batch `0` (`seed=42`, `0` optimizer steps):
1. `SupCon` in `pipeline/training/train_boundary_candidate.py` uses `out.hidden_states[-1][:, 0, :]` (`h_cls` upstream of `pre_classifier`). With all `100` `distilbert.*` parameter tensors frozen:
   - `l_sc.requires_grad == False`
   - `max |grad(L_pos + L_neg + l_sc) - grad(L_pos + L_neg)| == 0.0` across all 4 trainable tensors (`pre_classifier.weight`, `pre_classifier.bias`, `classifier.weight`, `classifier.bias`).
   - All `100` frozen tensors have `p.grad is None` (`frozen_non_none_grads = []`).
   - Implementation rule: set `use_supcon = (fit_mode == "fit2_supcon_energy") and (trainable_scope == "all")`, avoiding wasted `output_hidden_states=True` compute while remaining mathematically identical to `supcon_loss_sum = 0.0`.
2. **`L_pos + L_neg` flow through both unfrozen layers (`batch 0` grad norms):**
   `pre_classifier.weight = 0.017771`, `pre_classifier.bias = 0.001905`, `classifier.weight = 0.030702`, `classifier.bias = 0.002308` (all strictly positive; full epoch `||g_all|| = 0.022554` on `pre_classifier` and `0.043430` on `classifier`).
3. **No unrequested confounders:** No L2 tether, no teacher KL (`teacher_used = false`), no LoRA, no selective rejector (`enable_selective_rejector = False`), `min_temperature = 1.0`, canonical `fit2_supcon_energy` constants unchanged (`13,080` effective rows = `409` steps/epoch).

---

## 4. Selected Single Fixed A-Priori Hyperparameter Recipe

- **Profile Name:** `option_a_pre_classifier_head_v1` (`trainable_scope = "pre_classifier_and_classifier"`, `feature_dropout_eval_mode = True`)
- **Fixed Recipe:** **`lr = 5e-5`, `epochs = 3`, `weight_decay = 0.01`**, `batch_size = 32`, `seed = 42`, linear warmup (`10%` = `122` of `1,227` steps) + linear decay (canonical `train_boundary_candidate.py` AdamW schedule).

### Quantitative Justification (No Sweeps / No Retries)
- Parameter RMS entry scale on `f695b1fe`: `pre_classifier.weight` (`||W||_F = 16.4077`) has RMS `0.02136`; `classifier.weight` (`||W||_F = 4.620542`) has RMS `0.02458`. Both sit around `~0.021–0.025`.
- Under AdamW linear warmup/decay (`effective LR integral ≈ 0.50 * lr * total_steps`), Attempt `1/2` (`lr=1e-4, epochs=2, steps=818`) had integral `~0.0409` (causing up to `0.0454` max-abs shift and `~0.20` L2 shift on untouched canonical classes, driving `pos_cal` `68 -> 67` and `neg_cal` `9 -> 10`).
- **`lr = 5e-5, epochs = 3`** (`1,227` steps, integral `0.030675`, `240` effective `added_18` updates vs `160` in `2ep`):
  - Halves peak per-step AdamW noise vs `1e-4` (limiting per-step shock on `pre_classifier` ReLU gates for canonical/CAL rows).
  - Keeps cumulative capacity `50%` above `5e-5 x 2ep` (`integral 0.02045`) and matches Fit2's original `epochs=3` replay cadence so `added_ris` (`0.0166` baseline prob) has sufficient updates (`240` vs `160`) to form separating `pre_classifier` ReLU features for `>= 15/18`.

---

## 5. Required Implementation & Verification Specs (For Worker A)

### Minimal Code Scope (Zero Unused Refactoring)
1. [train_boundary_candidate.py](file:///F:/Năm%203/SD/project/SupportIQ/pipeline/training/train_boundary_candidate.py):
   - Extend `VALID_TRAINABLE_SCOPES` with `"pre_classifier_and_classifier"`.
   - Extend `_configure_trainable_scope`: unfreeze exact `["classifier.bias", "classifier.weight", "pre_classifier.bias", "pre_classifier.weight"]`; enforce `expected_trainable_param_count == 625966` and `expected_frozen_param_count == 66362880`.
   - Extend `_set_epoch_module_modes`: call `model.eval()`, set `model.pre_classifier.train(True)` + `model.classifier.train(True)`, fail closed if ANY other submodule (specifically `model.dropout` and `model.distilbert` submodules) has `.training == True`.
   - Extend `run_fit_and_lock_candidate`: `HEAD_ONLY_SCOPES = ("classifier_head_only", "pre_classifier_and_classifier")`; set `use_supcon = (fit_mode == "fit2_supcon_energy") and (trainable_scope == "all")`; capture pre/post `_snapshot_frozen_component_hashes` (100 frozen tensors + `1` buffer; note `pre_classifier` key is naturally absent when unfrozen), fail closed on any non-`None` frozen `.grad` or hash mismatch.
2. [run_orig_fit2_return_contrast_prep.py](file:///F:/Năm%203/SD/project/SupportIQ/scripts/run_orig_fit2_return_contrast_prep.py) & [run_orig_fit2_return_contrast_fit.py](file:///F:/Năm%203/SD/project/SupportIQ/scripts/run_orig_fit2_return_contrast_fit.py):
   - Add `option_a_pre_classifier_head_v1` to `AUTHORIZED_FIT_PROFILES` with exact locked constants (`lr=5e-5, epochs=3, batch_size=32, seed=42, weight_decay=0.01, fit_mode="fit2_supcon_energy", enable_selective_rejector=False, trainable_scope="pre_classifier_and_classifier", feature_dropout_eval_mode=True, expected_trainable_param_count=625966, expected_frozen_param_count=66362880`).
   - Validate schema/manifest/optimizer param membership & forbid KL/tether/LoRA/rejector across `prep` and `fit` scripts via a shared subhead-scope helper/tuple.

### Mandatory Unit Tests & Pre/Post-Fit Gates
- **Freeze & Param Count Test:** Exact `4` trainable tensors (`625,966` params) + `100` frozen tensors (`66,362,880` params) + `1` buffer; fail-closed on mismatch.
- **Explicit Module-Mode & Dropout/RNG Invariance Test:** Every `distilbert.*` module and `model.dropout` stays `.training == False` during epochs; `pre_classifier` and `classifier` are `.training == True`; repeat forward `max_diff == 0.0` and CPU/CUDA RNG state unchanged.
- **Autograd & `SupCon` Equivalence Test:** Nonzero grads on both `pre_classifier.*` and `classifier.*`; `p.grad is None` for all `100` frozen params; `supcon_loss_sum == 0.0` and `0.0` gradient difference with `SupCon` path enabled vs disabled.
- **Optimizer Param-Group & Provenance Test:** `optimizer.param_groups` contains exact `4` tensors (`625,966` elements) at `lr=5e-5, weight_decay=0.01`; fail-closed manifest checks for `option_a_pre_classifier_head_v1`.
- **Post-Fit Archival, `ModelContainer` Parity & `12`-Check CAL Guard:** Post-archive reload verifies bit-identical frozen `distilbert.embeddings` + `layer.0..5` + `buffers` vs `f695b1fe`, `6`-file archive + full sidecar SHA inventories, `ModelContainer` parity (`<= 3e-6`), and all `12` canonical CAL guard checks.

---

## 6. Confounds & Strict Final Stop Protocol (`Attempt 2/2`)

- **Methodological Confounds (Must Disclose in Final Audit):** Simultaneous change of unfrozen capacity (`classifier` $\rightarrow$ `pre_classifier + classifier`), `lr` (`1e-4` $\rightarrow$ `5e-5`), and `epochs` (`2` $\rightarrow$ `3`) at `n = 1` (`seed = 42`); retention of `3` historical noisy overlaps (`exclude_noisy_test_overlap = false`).
- **Hard Attempt-2/2 Budget & Stop Rule (`.local/training-cap-20261114.json`):**
  1. Increment `additional_attempts_started` to **`2 / 2`** BEFORE calling `optimizer.step()`. Any crash/abort after optimizer start **consumes Attempt `2/2`**.
  2. **Zero retries, zero secondary LR/epoch tries, zero holdout peeks prior to CAL `12/12` PASS.**
  3. **If `cal_guard_passed == false` (`< 12/12` checks) OR crash occurs:** immediately **`CAL_GUARD_REJECT_DO_NOT_PROMOTE` — PERMANENT FIT2 STOP** (`training_stopped = true`). No Attempt 3; active serving (`dc7af8cf...`) stays untouched; Worker C runs holdouts ONLY if CAL `12/12` passes and no further tuning occurs.
