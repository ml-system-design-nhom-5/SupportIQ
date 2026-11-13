# Fit2 Boundary Contrast v2 (`a64c3ff9`) Diagnosis — Worker B (Ponytail ULTRA)

**Date:** 2026-11-13  
**Candidate:** `fit2-boundary-contrast-v2` (`model.safetensors` SHA-256 `a64c3ff9ac577d95ae043c567ef25af62fbfa037a96f7fc56264427283a37d2a`, code `a7322fc96fbf386ea0cab72943e63163f6cded27`, init `f695b1fe`, `T=1.0`, `rejector=false`)  
**Integrity Check:** `run-records-fit2-boundary-contrast-v2` (`20` files, `0` SHA mismatches); `fit2-boundary-contrast-v2` archive (`6` files, `0` SHA mismatches).

---

## 1. Paired Gate Comparison (`orig f695b1fe` vs `v1 494fe730` vs `v2 a64c3ff9`)

| Metric (Calibrated `T=1.0`, Same Engine/Runner) | `orig_f695` | `v1_494f` | `v2_a64c` |
| --- | --- | --- | --- |
| `gate_decision` | `REJECT` | `REJECT` | `REJECT` |
| `failure_reasons` | `mandatory_escalation_unsafe_draft_leak` | `oos_draft_leak` | `mandatory_escalation_unsafe_draft_leak` |
| `mandatory_63` strict / leaks | `57/63` (`uns-order_history-01`, `uns-return_product_in_store-01`) | `60/63` (`0` leaks) | `60/63` (`uns-track_delivery-01`) |
| `ml_oos_80` false drafts | `0/80` | `1/80` (`oos-multi_intent-02`) | `0/80` |
| `final_12` answerable drafts | `10/12` | `8/12` | `7/12` (`4` abstain, `1` escalate) |
| `sys_34` draft expected | `25/34` (`28` raw) | `28/34` (`30` raw) | `25/34` (`27` raw) |
| `ml_noise_420` Macro-F1 / correct | `0.8573` / `267` (`293` raw) | `0.8711` / `277` (`295` raw) | `0.8795` / `265` (`285` raw) |
| `independent_holdout` `supported_12` raw / ECE | `39/84` (`46.4%`) / `0.1351` | — | `38/96` (`39.6%`) / `0.1833` |

---

## 2. Engine/Runner Per-Case Evidence (Leaks + Lost Supported Cases)

Measured directly via `GateSequenceClassifier` + `_build_engine` + `engine._analyse` ([classifier_acceptance_gate.py](file:///C:/Users/PC/orca/workspaces/SupportIQ/fit2-boundary-b/pipeline/evaluation/classifier_acceptance_gate.py)):

1. **`uns-track_delivery-01` (`track_delivery`, NEW leak in `v2`):**
   - `orig_f695`: `track_order` `0.1527` (`sup12_mass=0.3719`, `energy=-3.363`) -> `manual_fallback`
   - `v1_494f`: `track_order` `0.5904` (`sup12_mass=0.6998`, `energy=-3.882`) -> `manual_fallback`
   - `v2_a64c`: `track_order` **`0.7355`** (`top2=technical_issue 0.0223`, `margin=0.7132`, `sup12_mass=0.7990`, `energy=-4.249`) -> **`retrieve_draft`** (crossed `0.72` threshold).
2. **`uns-order_history-01` & `uns-return_product_in_store-01` (Fixed by uniform flattening, not true `ESC34` separation):**
   - `uns-order_history-01`: `orig_f695` `track_order 0.6639` (`retrieve_draft`) -> `v2_a64c` `store_opening_hours 0.0247` (`top2=order_history 0.0245`, `margin=0.0002`, `energy=-3.784`, `escalate`).
   - `uns-return_product_in_store-01`: `orig_f695` `return_policy 0.6828` (`retrieve_draft`) -> `v2_a64c` `return_product_in_store 0.0243` (`top2=availability 0.0238`, `margin=0.0005`, `energy=-3.785`, `escalate`).
3. **`oos-multi_intent-02` (Fixed in `v2`):**
   - `orig_f695`: `request_refund 0.4459` (`manual_fallback`) -> `v1_494f`: `0.8857` (`retrieve_draft`) -> `v2_a64c`: `0.3501` (`manual_fallback`).
4. **Lost `final_12` Supported Cases (`10/12 -> 7/12`):**
   - `final-case-05` (`refund_status`): `orig` `0.8056` (`retrieve_draft`) -> `v1` `0.8134` (`retrieve_draft`) -> `v2` `0.2903` (`energy=-3.764`, `manual_fallback`).
   - `final-case-06` (`cancel_order`): `orig` `0.8343` (`retrieve_draft`) -> `v1` `0.6561` (`manual_fallback`) -> `v2` `0.1777` (`energy=-3.604`, `manual_fallback`).
   - `final-case-11` (`return_policy`): `orig` `0.8617` (`retrieve_draft`) -> `v1` `0.4714` (`manual_fallback`) -> `v2` `0.4398` (`energy=-3.941`, `manual_fallback`).
   - `final-case-02` (`return_product`): `orig` `0.1319` (`manual_fallback`) -> `v2` `return_product_online 0.0272` (`escalate`).

---

## 3. Structural Objective Conflict & `cal` Diagnostics

### Training Exposure Audit (`dryrun-v3` datasets)
- **`boundary_neg_train` (`187` raw / `1668` eff, takes `UniformKL + sup12_ceil + energy_margin + SupCon(sc=-1)`):**
  - Genuine non-46-taxonomy negatives: `compound_multi_intent` (`16+37=53` raw, `192+444=636` eff), `off_domain_homonym` (`10` raw, `120` eff), `off_domain_unrelated` (`15` raw, `180` eff), `underspecified_ambiguous` (`19` raw, `228` eff), `unsupported_product_or_merchant` (`18` raw, `216` eff). Total = `115` raw / `1380` eff.
  - **In-taxonomy `ESCALATED_34` rows in `neg_mask`:** `confusable_single_neg` = `72` raw (`36` `order_history`, `36` `return_product_in_store`), `288` eff (`v1` had `864` eff).
- **Positive / Bitext Train (`pos_mask`, takes 46-class CE + positive SupCon):**
  - `order_history`: `240` `bitext_train` rows; `return_product_in_store`: `240` `bitext_train` rows; `track_delivery`: `240` `bitext_train` rows (`0` in `boundary_pos_train` and `0` in `boundary_neg_train`).
  - `boundary_pos_train` already includes `48` `ESCALATED_34` rows (`240` eff) as positive 46-class CE examples.

### Measured Objective Conflict on `confusable_single_neg` (`n=72`)
- Under `orig_f695`: `true_esc34_acc=0.6806`, `true_esc34_prob=0.6244`, `CE_vs_true=1.7157`, `UniformKL=2.8060`, `Ceil=0.1024`.
- Under `v2_a64c`: `true_esc34_acc=0.7222`, **`true_esc34_prob=0.2651`**, **`CE_vs_true=2.3250`**, `UniformKL=0.3893`, `Ceil=0.0006`.
- **Conclusion (Measured):** Putting in-taxonomy `ESCALATED_34` rows into `neg_mask` forces `UniformKL` + `energy_margin` (`-logsumexp`) against `bitext_train` 46-class CE, collapsing `true_esc34_prob` (`0.6244 -> 0.2651`), flattening logits to `~1/46`, and suppressing `SUPPORTED_12` confidence/energy (`final-case-05/06/11` `energy` dropped from `-4.80..-5.32` to `-3.60..-3.94`). Meanwhile, `AUTHORED_CONTRAST_FAMILIES` added `track_order` positives without `track_delivery` contrast, pushing `uns-track_delivery-01` from `0.1527` -> `0.5904` -> `0.7355`.

### `cal` Split Diagnostics
- `orig_f695`: `cal_sup12=187/194/240`, `cal_esc_pos_leak=0/548`, `cal_neg_leak=5/82` (`4` `confusable_single_neg` + `1` `compound_multi_intent`).
- `v1_494f`: `cal_sup12=193/199/240`, `cal_esc_pos_leak=0/548`, `cal_neg_leak=0/82` (`compound_multi_intent` `max_conf=0.7914`).
- `v2_a64c`: `cal_sup12=193/198/240`, `cal_esc_pos_leak=0/548`, `cal_neg_leak=0/82` (`compound_multi_intent` `max_conf=0.1554`, `confusable_single_neg` `mean_conf=0.4325`, `max_conf=0.9508`).

---

## 4. Recommended Minimal Next Step

**ONE minimal, generalizable data-routing fix** (retaining exact `fit2_supcon_energy` SupCon + KL + energy backbone, `init=f695b1fe`, `epochs=2`, `lr=1e-5`, `seed=42`, `T` calibrated on `cal` only, `rejector=false`, zero runtime guard/threshold hacks):
1. **Treat in-taxonomy `ESCALATED_34` single-intent contrast rows as `boundary_pos_train` (`pos_mask`, 46-class CE + SupCon on their true `ESC34` label)** instead of `boundary_neg_train` (`neg_mask`), and include disjoint Bitext TRAIN + group-isolated `ESC34` vs `SUPPORTED_12` pairs covering `track_delivery` vs `track_order` alongside `order_history` vs `track_order` and `return_product_in_store` vs `return_policy`/`return_product`.
2. **Keep `boundary_neg_train` (`UniformKL + sup12_ceil + energy_margin`) strictly for genuine non-46-taxonomy negatives** (`out_of_scope` + `compound_multi_intent`).

**Risks / What Is Not Proven:** Removing `72` `ESC34` rows from `neg_mask` and adding `track_delivery` positive contrast is hypothesized to eliminate the `CE vs UniformKL` conflict, recover `final_12 >= 10/12`, and suppress `uns-track_delivery-01` via true `track_delivery` classification (`ESC34`), **but** this is not proven until a controlled run; over-weighting `track_delivery` could still shift `track_order` recall on `cal`/`eval` if repeat counts are not kept balanced.
