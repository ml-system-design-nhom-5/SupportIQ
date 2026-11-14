# Fit2 Classifier-Only Proposal Review (Worker B Design Audit)

- **Verdict:** **`PASS` (Conditional Single-Shot Design for Attempt `1/2` Prep+Pre-Fit Review Only; `0` fits executed, NO fit authorized now; hard `EARLY STOP` rule if `1/2` misses accuracy or separation gates)**
- **Budget Lock:** Global additional attempt cap `2`; `0/2` used post-detKL ([.local/training-cap-20261114.json](file:///F:/Năm%203/SD/project/SupportIQ/.local/training-cap-20261114.json) preserved untouched).
- **Reviewed Baseline:** Original Fit2 `f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa` and Worker C decision brief [2026-11-14-fit2-deterministic-kl-cal-review-c.md](file:///F:/Năm%203/SD/project/SupportIQ/docs/audits/2026-11-14-fit2-deterministic-kl-cal-review-c.md) (`ecb5d1bce95fa7a07785d6947f6f155350f8428a`).

---

## 1. Exact Architecture, Parameter Count & Feature/Dropout Modes

Measured directly on `reconstructed-fit2-supcon-20261113` (`f695b1fe`):
- **Total Params:** `66,988,846`
  - **Frozen (`66,953,472` = `99.9472%`):** `distilbert.embeddings` (`23,835,648`) + `distilbert.transformer.layer.0..5` (`42,527,232`) + `pre_classifier` (`590,592`) — all `requires_grad=False`.
  - **Trainable (`35,374` = `0.0528%`):** `classifier` (`nn.Linear(768, 46)`: `768 * 46 + 46`) — `requires_grad=True` ONLY.
- **Inspected `DistilBertForSequenceClassification.forward` Path:**
  `hidden_state = self.distilbert(...)[0]` → `pooled_output = hidden_state[:, 0]` → `self.pre_classifier(pooled_output)` → `nn.ReLU()` → `self.dropout(pooled_output)` (`p = 0.2`) → `self.classifier(pooled_output)`.
- **Explicit Module `.training` Mode Contract (Per-Epoch):**
  - `model.distilbert.eval()`, `model.pre_classifier.eval()`, `model.dropout.eval()`: even with `requires_grad=False`, calling `model.train()` enables transformer attention dropout and head-input `dropout(p=0.2)` (`1.25×` rescaling variance on frozen features). Keeping frozen modules and `self.dropout` in `.eval()` yields **strictly deterministic** frozen features $\phi(x) = \mathrm{ReLU}(\mathrm{pre\_classifier}(\mathrm{distilbert}(x)[:, 0]))$, zero forward-dropout RNG consumption, and distribution parity with `T=1.0` `eval()` calibration.
  - `model.classifier.train()`: linear `nn.Linear(768, 46)` has no internal dropout of its own and trains cleanly on deterministic $\phi(x)$.

---

## 2. Minimal Justified Objective & No Effective Objective Change

Using `pipeline/training/train_boundary_candidate.py` Stage-2 loss (`fit2_supcon_energy`):
- **`SupCon` Invariance (Zero Effective Objective Change):** `l_sc = 0.25 * _supcon_loss(F.normalize(out.hidden_states[-1][:, 0, :], dim=-1), ...)` consumes transformer `layer.5` output strictly upstream of `pre_classifier` and `classifier`. Verified by autograd on `f695b1fe`: `l_sc.requires_grad == False`, `max_diff(classifier.weight.grad, with_vs_without_l_sc) == 0.000e+00`, `max_diff(classifier.bias.grad) == 0.000e+00`, `frozen_grads = (0, 0)`. Omitting `output_hidden_states=True`/`l_sc` (or keeping it disabled when encoder is frozen) is a mathematical no-op on head gradients, **not** a new algorithm.
- **Unchanged Classification & Negative Losses:** `l_pos` (CE, `label_smoothing=0.03`) and `l_neg` (`0.80 * l_kl_uniform + 3.0 * relu(sup12_mass - 0.18)^2 + 0.25 * relu((pos_energy_mean.detach() + 2.0) - neg_energy)^2`) act directly on `logits`. Autograd verified non-zero negative-head gradient (`lneg_only_head_grad_norm = 0.0389`, full-dataset expectation `0.0042` across `1,188` effective `neg_train` rows), with exact masking, normalization, and `.detach()` untouched. `teacher_kl_weight = 0.0` (representation drift is `0.0000` by freeze; no KL, tether, LoRA, or new dependencies).

---

## 3. Fixed A-Priori Recipe (`1` Recipe Only; No Grid)

| Setting | Choice (`2e-5 / 3ep` vs **`1e-4 / 2ep`**) | Scientific Rationale |
|---|---|---|
| **Selected Recipe** | **`option_a_classifier_head_only_v1`: `AdamW(lr=1e-4, weight_decay=0.01)`, `epochs=2`, `batch_size=32`, `seed=42`, `fit_mode="fit2_supcon_energy"` (`l_pos + l_neg`, no KL/SupCon/tether), `min_temperature=1.0`, `enable_selective_rejector=False`** | Under AdamW, per-coordinate displacement scales with `~lr * lr_sched`, not gradient magnitude. `10%` warmup + linear decay (`area ≈ 0.5 * steps`) yields `~0.0409` per-coord capacity over `818` steps (`2ep, 1e-4`) vs `~0.0123` over `1,227` steps (`3ep, 2e-5`) — `3.33×` stronger head rotation on `||W_cls||_F = 4.6205` (`mean |w| = 0.01992`) to overcome `-1.59` to `-5.58` logit margins on `added_8_ris` while reducing canonical replay steps by `33%`. At step 0, `cos(-g_full_batch, W_cls) = -0.3682` (`canon = -0.5607`), so updates initially contract rather than inflate weight norm. |
| **Compute & Memory** | **`35,374` trainable params (`< 0.6 MB` AdamW state + grads)** | Eliminates `> 535 MB` optimizer state and all encoder autograd activations; zero change to data pipeline, `seed=42` DataLoader shuffle, `seed+99` negative noise RNG, `46`-class taxonomy, `13,080` effective TRAIN split (`11,812` canon + `80` `added_18` + `1,188` neg), `12` CAL guards, or `3` historical noisy overlap disclosure (`exclude_noisy_test_overlap=false`). |

---

## 4. Read-Only `f695b1fe` Feature Separation Audit (`0` Optimizer Steps, No Holdouts, No Toy Fit)

Inspected frozen `f695b1fe` `eval()` representations `h_pre = relu(pre_classifier(cls(x)))` across **TRAIN + CAL only**:
- **Canonical Class Separation & Global Step Alignment (Supportive):** Canonical TRAIN centroids are cleanly separated (`centroid_cos(return_product_in_store, return_policy) = 0.4414`, `return_product = 0.4086`, `store_location = 0.3310`, `exchange_product_in_store = 0.4054`; `mean ||h_pre||_2`: `canon_pos = 17.944`, `ext_ris = 10.848`, `neg_tr = 2.598`). Step-0 weighted full-epoch head gradient (`||g_full|| = 0.0442`: `canon = 0.0271`, `ext_ris = 0.0298`, `ext_rp = 0.0200`, `neg = 0.0042`) is helpful/neutral on CAL risk metrics: `cos(-g_full, g_pcal_mmp_ascent) = -0.1306`, `cos(-g_full, g_ncal_sup12_ascent) = -0.1558`, `cos(-g_full, g_inv_sup12_ascent) = -0.0343`, `cos(-g_full, g_esc_sup12_ascent) = +0.0123`. Canonical `return_product_in_store` count on `pos_cal` is `0` (`return_policy = 4`).
- **Hard Feature Conflicts on `added_18` vs Canonical Replay & CAL (Major Feasibility Risk):**
  - `added_18` matches canonical TRAIN centroid / 1-NN on **`8/18`** only (`8/10` on `return_policy`, **`0/8` on `return_product_in_store`**).
  - All `8` `return_product_in_store` targets sit closer to wrong canonical classes: `g04_ris_00` (`cos=0.952` canonical `return_policy`, `0.932` `pos_cal` `shipping_costs`, margin `-5.58`); `g01_ris_00` (`cos=0.932` canonical `return_product`, `0.807` `pos_cal` `cls_rpr_qc_inspection_2_80de0abcbaeb`, `0.810` `neg_cal` `cls_neg_und_cal_3_1_2f79d2f85f6d`, margin `-4.62`); `g03_ris_01`/`g04_ris_01`/`g02_ris_00` (`0.722–0.819` `return_policy`); `g03_ris_00` (`0.771` `human_agent`); `g01_ris_01`/`g02_ris_01` (`same_max = 0.249/0.280 < max_neg_tr = 0.629/0.578`).
  - Because `orig_fit2` sits at **exact `0`-row slack** on `pos_cal >= 68/86`, `sup12 >= 38/48`, `neg_cal <= 9/48`, and must raise `added_18` from `8/18` to `>= 15/18` linearly in fixed `768-d` `h_pre`, this single head-only probe is high-variance and may still expose a linear-separability ceiling.

---

## 5. Required Pre-Prep / Pre-Fit Contract & Hard Budget Gates

Worker A implementation (not started; requires Coordinator prep release) MUST include unit tests proving:
1. **Freeze Hash Bit-Identity:** SHA-256 of every frozen tensor (`distilbert.embeddings`, `transformer.layer.0..5`, `pre_classifier`) is bit-identical pre- vs post-optimizer steps (`max_abs_delta == 0.0`).
2. **Optimizer & Grad Isolation:** Optimizer covers **exact `35,374` params** (`classifier.weight`, `classifier.bias` only); grad clipping applies only to trainable params; `classifier` receives nonzero grads from both `l_pos` and `l_neg`; all `66,953,472` frozen params keep `p.grad is None`; retaining vs omitting `l_sc` matches head grads to `0.0`.
3. **Deterministic Mode & RNG Check:** Per-epoch check locks `distilbert`, `pre_classifier`, and `dropout` to `.eval()` (`.training == False`) and `classifier` to `.train()` (`.training == True`); repeated forward passes match `0.0`; DataLoader (`seed=42`) & negative noise (`seed+99`) RNG preserved.
4. **Provenance, Guards & Archival Parity:** Isolated profile (`validate_profile_settings`), `--validate-only` (`0` fits), untouched `12`-check CAL guard + `3`-overlap disclosure, complete archive/sidecar SHA inventories, `ModelContainer` reload parity, and explicit provenance fields (`trainable_param_count=35374`, frozen scope, optimizer/schedule, small compute budget).
5. **Hard Decision Gate After Attempt `1/2`:**
   - **`EARLY STOP` (Leave Attempt `2/2` Unspent):** If Attempt `1/2` fails **any** integer accuracy/leakage gate (`pos_cal < 68`, `sup12 < 38`, `bitext_cal < 687`, `added_18 < 15`, `neg_cal_pred_sup12 > 9`, `sup12_conf070 < 26`, `sup12_conf080 < 24`) or `esc34_max_sup12_mass > 0.55` or `neg_cal` float ceilings.
   - Attempt `2/2` is **not pre-authorized** and may be proposed only if `1/2` passes all accuracy/separation gates and misses **solely** on `delta_mean_max_prob <= 0.015` from head norm growth (isolated diagnosed fix e.g. head L2 tether, no arbitrary sweeps).
