# Worker C Bounded CAL Verification & Next-Attempt Decision Brief (`fit2-orig-deterministic-kl-v1`)

**Reviewer:** Worker C (`review` / independent CAL & feasibility audit)
**Target Candidate:** [fit2-orig-deterministic-kl-v1](file:///F:/Năm%203/SD/project/SupportIQ/artifacts/models/candidates/fit2-orig-deterministic-kl-v1) (A's audit at `6b54be18b63c29f9753666ba3068877d7932df3c`: [2026-11-14-fit2-deterministic-kl-run-a.md](file:///F:/Năm%203/SD/project/SupportIQ/docs/audits/2026-11-14-fit2-deterministic-kl-run-a.md); frozen code `e82ec7d6bd3bcf18fe6227837fe2c42845cab943`; B pre-fit `ac684c2fb091e30d78e3233151c18bad1be7a183`)
**Scope & Budget Lock:** Strictly read-only (**0** new fits, **0** optimizer steps, **0** calibrator/paid-LLM/holdout/OOD runs); [.local/training-cap-20261114.json](file:///F:/Năm%203/SD/project/SupportIQ/.local/training-cap-20261114.json) untouched (`additional_attempt_limit = 2`, `additional_attempts_started = 0`).
**Deliverables:**
- Script: [verify_det_kl_cal.py](file:///F:/Năm%203/SD/project/SupportIQ/artifacts/evaluation/fit2_det_kl_cal_review_c_20261114/verify_det_kl_cal.py)
- Metrics, Weight-Delta & Head-Feasibility JSON: [det_kl_cal_and_head_feasibility.json](file:///F:/Năm%203/SD/project/SupportIQ/artifacts/evaluation/fit2_det_kl_cal_review_c_20261114/det_kl_cal_and_head_feasibility.json)
- Manifest: [run_manifest.json](file:///F:/Năm%203/SD/project/SupportIQ/artifacts/evaluation/fit2_det_kl_cal_review_c_20261114/run_manifest.json)

---

## 1. Dual Verdict Summary

- **Implementation & Lineage Verdict:** **`PASS`** — exact match to `option_a_teacher_kl_deterministic` (`eval_no_dropout_autograd_enabled`, `alpha_kl=1.0`, `T_teacher=1.0`, `lr=2e-5`, `epochs=3`, `bs=32`, `seed=42`, `13,000` anchored / `80` excluded, `train_seconds=229.79`), `_forward_student_logits_eval_mode` cleanly disables student dropout during KL forward while restoring nested `.training` state (`0` code/lineage bugs).
- **CAL Guard Verdict:** **`CAL_GUARD_REJECT_DO_NOT_PROMOTE` (`BLOCK`)** — independently reproduced **`6/12 PASS`, `6/12 FAIL`** (`max_guard_float_diff = 0.0 <= 3e-6`; `ModelContainer` parity `134/134` boundary CAL rows, `0` intent mismatches, `max_confidence_abs_diff = 2.08e-6 <= 3e-6`).
- **Mechanism Proven:** Removing student dropout cured stochastic KL over-sharpening (`neg_cal` `max_sup12_mass` `0.7650 -> 0.6673` PASS; `pos_cal` drift `+0.0558 -> +0.0298`; final `student.eval()` entropy `0.495884` vs teacher `0.498786`), **yet** `avg_teacher_kl_loss` (`0.001713 -> 0.001602 -> 0.001065`) remained `< 0.5%` of total loss (`0.348-0.367`). All `6` encoder layers (`42.53M` params) still drifted **`2.2195` L2** (`96.2%` of unanchored `prior_2e5`'s `2.3064`), keeping all `3` accuracy/leakage integer gates and `3` drift/mass gates failed.

---

## 2. Archive, Sidecar, Prep, Source, Input Parity & Untouched Assets

| Check | Result | Verified Evidence / SHA-256 |
|---|---|---|
| Candidate Archive (`6/6`) | **PASS** | `model.safetensors` `e63d1ea963e165aaabdd8b619f2e1bf26914fff746bc9f1b7f888c3acf0191f1`; `calibration_manifest.json` `9c529f862a50ed31ebb6f0091b286c84a92eef73cb8736229c410c119f9468ac` (`T=1.0`, `min_T=1.0`, `rejector=false`); `candidate_provenance_manifest.json` `dd2e7b1c97dabae4a7bef6cc4c4f73fae16946bbeb3f178ff0a5a03a42692c38` |
| Sidecar (`41/41`) & Prep (`39/39`) | **PASS** | Sidecar `cal_guard_report.json` `bbe60c54dbca5361ac117ecc7ae53652cb4dec6b91d1d6ff0b47694ea6160ef1`; `prep_manifest.json` `a2b1983dcaa328423b182ec9ebcaeb969ee5e74330fd13394f01af68426d6fb6`; `0` inventory mismatches |
| Input Parity & Overlaps | **PASS** | `0` diffs (`records/inputs` vs `prep/datasets` and shared `.jsonl` + `split_manifest.json` vs `v4-prep`); historical overlaps preserved (`noisy_vs_bitext_test=3`, `noisy_vs_cal=0`, `clean_vs_cal=0`, `clean_vs_eval_total=0`) |
| Source Snapshot & Untouched | **PASS** | `0` diffs across `source_snapshot/` vs `run_config.json`, `prep_manifest.json`, and disk; `orig_fit2` (`f695b1fe...`), `zero_delta` (`904188...`), `prior_2e5` (`dc3e88...`), `lr5e6` (`b7a285...`), `teacher_kl` (`3994af...`), `serving` (`dc7af8...`), `fit1` (`95a940...`) untouched |

---

## 3. Recomputed 12-Check CAL Guard & 4-Way Comparison (vs Paired Baselines)

| Surface (`n`) / Gate | Metric / Limit | `orig_fit2` (`f695b1fe`) | `prior_2e5` (`dc3e88e7`) | `stoch_kl` (`3994af2c`) | `det_kl` (`e63d1ea9`) | Guard Status |
|---|---|---:|---:|---:|---:|---|
| `pos_cal` (`86`) | Correct (`>= 68`) | `68` | `68` | `67` | **`67`** (`0.779070`) | **FAIL** |
| `pos_cal sup12` (`48`) | Correct (`>= 38`) / `>=0.70` / `>=0.80` | `38` / `28` / `28` | `38` / `34` / `29` | `37` / `34` / `32` | **`37`** / `33` / `29` | **FAIL** (`37<38`), **PASS** (`>=26, >=24`) |
| `bitext_cal` (`690`) | Correct (`>= 687`) / `mean_max_prob` | `689` / `0.977800` | `689` / `0.976676` | `689` / `0.979658` | `689` / `0.977158` | **PASS** |
| `added_18` (`18`) | Correct (`>= 15`) / `mean_max_prob` | `8` / `0.504559` | `18` / `0.979646` | `18` / `0.981548` | `18` / `0.980365` | **PASS** |
| `neg_cal` (`48`) | `pred_sup12` (`<= 9`) | `9` | `10` | `10` | **`10`** | **FAIL** |
| `pos_cal` (`86`) | `delta_mean_max_prob` (`<= 0.015`) | `0.686344` | `+0.036095` | `+0.055831` | **`+0.029798`** (`0.716142`) | **FAIL** |
| `pos_cal esc34` (`38`) | `delta_mean_max_prob` (`<= 0.015`) | `0.670962` | `+0.036078` | `+0.060602` | **`+0.031540`** (`0.702503`) | **FAIL** |
| `pos_cal esc34` (`38`) | `max_sup12_mass` (`<= 0.55`) | `0.467362` | `0.682218` | `0.671330` | **`0.673281`** | **FAIL** |
| `neg_cal` (`48`) | `max_sup12_mass` (`<= 0.715693`) | `0.715693` | `0.733993` | `0.764955` | **`0.667270`** | **PASS** (improved) |
| `neg_cal` (`48`) | `max_single_sup12_prob` (`<= 0.557692`) | `0.557692` | `0.582643` | `0.611628` | **`0.527478`** | **PASS** (improved) |
| `pos_cal` (`86`) | Right / **Wrong** `mean_max_prob` / `KL` | `0.7328` / `0.5107` / `0` | `0.7539` / `0.6036` / `0.054` | `0.7853` / `0.5902` / `0.062` | `0.7512` / **`0.5925`** / `0.0542` | — |
| `esc34` (`38`) | Right / **Wrong** `mean_max_prob` / `KL` | `0.7243` / `0.4709` / `0` | `0.7305` / `0.6189` / `0.073` | `0.7573` / `0.6351` / `0.079` | `0.7268` / **`0.6113`** / `0.0692` | — |
| `pos_train` (`199`) / `neg_train` (`99`) | Pos right / `neg_max_sup12` | `189` / `0.222151` | `199` / `0.219649` | `199` / `0.220075` | `199` / `0.219535` | — |

- **CAL Flips vs `orig_fit2`:** `det_kl` gained `2` (`cls_dtm_pre_order_eta_0_0ab138c43752`, `cls_e34_chg_cal_0_c36a18761dec`), lost `3` (`cls_rpr_qc_inspection_2_80de0abcbaeb`, `cls_hum_escalate_now_1_58df76a91338`, `cls_e34_avonl_cal_1_af025937dd54`) -> net `-1`; `neg_cal` entered `2` (`cls_neg_off_cal_finance_1_c16b2323f38a`, `bnd_neg_homonym_cal_0_b32c79aceec4`), exited `1` (`cls_neg_cmi_cal_pay_inv_pinfo_2_ed26ede4b742`) -> net `+1`.

---

## 4. Deterministic KL Probes & Encoder vs Head Weight Deltas

- **Read-Only `16`-Batch Probe on Final `det_kl` (`0` Optimizer Steps):** `mean_det_eval_kl = 0.001894`, `mean_train_dropout_kl = 0.005452`, `teacher_eval` entropy `0.498786` vs `student.eval()` `0.495884` (`student.train()` `0.550940`), `||grad(base)||_2 = 0.639438`, `||grad(det_kl)||_2 = 0.239748` (`0.375x`), `cos(grad_base, grad_det_kl) = +0.073846`.
- **Frobenius Weight Delta `||W_cand - W_orig||_F` Across Modules:**

| Block | Params | `prior_2e5` L2 (rel) | `stoch_kl` L2 (rel) | `det_kl` L2 (rel) |
|---|---:|---:|---:|---:|
| `embeddings` | `23,835,648` | `0.569630` (`0.194%`) | `0.557322` (`0.189%`) | `0.564921` (`0.192%`) |
| `encoder_all_6` | `42,527,232` | `2.306357` (`0.784%`, `L5=1.251`) | `2.234242` (`0.760%`, `L5=1.141`) | **`2.219518`** (`0.755%`, `L5=1.176`) |
| `pre_classifier` | `590,592` | `0.503883` (`3.071%`) | `0.411239` (`2.506%`) | `0.439759` (`2.680%`) |
| `classifier` | `35,374` | `0.321431` (`6.957%`) | `0.231604` (`5.012%`) | `0.273319` (`5.915%`) |

- **Why Representation Drift Drove CAL Failure:** The worst `esc34` item `bnd_invoice_cal_0_18edf492ca0b` (`gold=request_invoice`, `orig_sup12_mass=0.467362` -> `det_kl=0.673281`) has low frozen feature similarity (`max h_pre cos = 0.3204` to `added_18`), confirming `2.22` L2 drift in the `6`-layer encoder distorted canonical CAL boundaries even with deterministic KL active.

---

## 5. Decision Brief for Remaining `2` Attempts (`0/2` Used): Frozen-6-Encoder Head-Only Adaptation

### 5.1 Read-Only Feasibility Assessment on Original `orig_fit2` (`f695b1fe`)
- **Parameter Architecture:** Total `66,988,846`. Freezing embeddings (`23,835,648`) + all `6` transformer layers (`42,527,232`) = `66,362,880` params (`99.0656%`) leaves two candidate head scopes:
  - **Linear `classifier`-only (`Linear(768, 46)`):** **`35,374` params (`0.0528%`)**, keeping `pre_classifier` (`590,592` params + ReLU/dropout) also frozen in `.eval()` so $\phi(x) = \mathrm{ReLU}(\mathrm{pre\_classifier}(\mathrm{CLS}(x)))$ has **strictly zero feature/representation drift**.
  - `pre_classifier + classifier`: `625,966` params (`0.9344%`), which re-introduces nonlinear representation drift and head dropout.
- **Objective Effect:** `SupCon` (`hidden_states[-1][:,0,:]`, upstream of `pre_classifier`) has **exact `0.0` gradient** when the `6`-layer encoder is frozen; only `l_pos` (CE, `label_smoothing=0.03`) + `l_neg` (`0.80*KL + 3.0*ceil + 0.25*eng`) operate on the head, **without KL stacking**.
- **Critical Head-Only Risks Observed Read-Only:**
  1. **Zero baseline on `return_product_in_store` (`0/8`):** On `orig_fit2`, `added_18` (`10` `return_policy`, `8` `return_product_in_store`) scores `8/18`: **`8/10` right on `return_policy`**, **`0/8` right on `return_product_in_store`** (`return_policy` x4, `return_product`, `store_location`, `exchange_product_in_store`, `human_agent`). A strictly linear `35,374`-param step must raise `return_product_in_store` to at least `5/8`-`7/8` on fixed $\phi(x)$ without overfitting `return_product` / `return_policy`.
  2. **Frozen Feature Overlap & Head Logits-Mass Drift:** `h_pre` cosine similarity to `added_18` reaches **`0.9648`** (`sup12_cal`), **`0.8165`** (`neg_cal`: `cls_neg_und_cal_3_1_2f79d2f85f6d`), and **`0.6875`** (`esc34_cal`, mean-max `0.5204`).
  3. **125x Gradient Shock & Norm Growth:** On `orig_fit2` `classifier`, `grad_norm_added18_ce = 4.8513` vs `grad_norm_canon_ce = 0.0387` (`125x`) and `grad_norm_neg_train_lneg = 0.00416`. While `added_18` CE has near-zero cosine with `esc34 sup12_mass` ascent (`-0.0082`) and negative `cos` (`+0.0918` toward decrease) on `neg_cal`, **freezing the encoder prevents representation drift but does NOT prevent head weight-norm growth or `pos_cal delta_mean_max_prob > 0.015`** if unconstrained over `1,227` steps on `13,080` rows.

### 5.2 Recommendation for Worker B + Coordinator (No Training Executed Here)
- **Should We Spend Attempt `1/2` vs `EARLY STOP` Now?**
  - **Conditional `1`-Attempt Probe (`1/2` of remaining budget) — ONLY IF B & Coordinator judge linear `classifier`-only worth testing once**, otherwise **`EARLY STOP NOW` (`0/2` additional fits)**. Under **no** circumstances spend either remaining attempt on full-backbone training, LoRA/new dependencies, fresh base retrain, or KL parameter sweeps.
- **One Fixed A Priori Recipe (No Grid; Not Bundled with KL or Anchor):**
  - **Init / Backbone:** `orig_fit2` (`f695b1fe`), **freeze `distilbert` (`embeddings + transformer.layer.0..5`) + `pre_classifier`** in `.eval()` (`torch.no_grad()` feature pass or `requires_grad=False`).
  - **Trainable Module:** `classifier` ONLY (**`35,374` params**, `0.0528%` of total; optimizer states + grads `< 0.6 MB`, eliminating `> 535 MB` of AdamW states vs full-backbone and encoder autograd activations).
  - **Objective:** Canonical + `+18` `13,080`-row Stage-2 TRAIN with `l_pos` (CE, `label_smoothing=0.03`) + `l_neg` (`fit2_supcon_energy` weights, **no KL** `alpha_kl=0`, **no SupCon**); `AdamW(lr=1e-4, weight_decay=0.01)`, `epochs=2` (`818` steps, `batch_size=32`, `seed=42`), linear warmup `10%` + linear decay, frozen `T=1.0`, `selective_rejector=False`.
  - **Optional Head Anchor (ONLY If Needed in Attempt `2/2`, NOT Bundled in `1/2`):** Add L2 head weight tether $\lambda_{\text{head}}\|\theta_{\text{cls}} - \theta_{\text{cls}}^{(0)}\|_2^2$ (NOT Teacher-KL) **only** if Attempt `1/2` passes `pos_cal >= 68`, `sup12 >= 38`, `added_18 >= 15`, `neg_cal_pred_sup12 <= 9`, `esc34_max_sup12_mass <= 0.55` and fails **solely** on `delta_mean_max_prob <= 0.015` from classifier norm growth.
  - **Hard Early-Stop Rule:** If Attempt `1/2` fails **any** accuracy (`pos_cal < 68`, `sup12 < 38`, `added_18 < 15`) or boundary separation (`neg_cal_pred_sup12 > 9`, `esc34_max_sup12_mass > 0.55`) gate, **`EARLY STOP` immediately after `1/2`** (leave Attempt `2/2` unspent; keep `orig_fit2` `f695b1fe` + downstream post-hoc `selective_rejector`/routing). Frozen `12`-check CAL guard and `3` historical overlaps remain unchanged.
