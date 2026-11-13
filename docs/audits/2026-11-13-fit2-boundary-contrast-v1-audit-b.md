# Audit & Diagnosis: `fit2-boundary-contrast-v1` (`REJECT`)

**Verdict:** `REJECT` (unchanged; gate failed on `oos_draft_leak`: `oos-multi_intent-02`).

## 1. Artifact, SHA & Reload Verification
- **Candidate:** `MAIN/artifacts/models/candidates/fit2-boundary-contrast-v1` (`model.safetensors` SHA-256 `494fe7302be9477c262eff70bbf6443e20423d7a267b1401e6209f0120b284c8`).
- **Provenance & Code:** `git_commit=776e90c594f0837f2df37c00c09fee1e518da5a0`, `init_weights_sha256=f695b1fe...` (`reconstructed-fit2-supcon-20261113`), `T=1.0`, `selective_rejector.enabled=false`, `epochs=2`, `lr=1e-5`, `seed=42`.
- **Integrity:** `0` mismatches in `archive_sha_inventory.json`, `0` mismatches in `run-records-fit2-boundary-contrast-v1/inputs/inputs_sha256_inventory.json`, `0` dataset hash mismatches vs `candidate_provenance_manifest.json`, `validate_calibration_manifest` valid, `verify_reload_from_archive` passed (`46` labels).

## 2. Gate & Holdout Metrics (`494fe730` vs Fit2 `f695b1fe`)
- **`mandatory_63`:** `60/63` strict match, **`0` unsafe draft leaks** (fixed both `uns-order_history-01` and `uns-return_product_in_store-01` vs Fit2 `2` unsafe).
- **`system_34`:** `28/34` correct drafts (vs Fit2 `25/34`).
- **`ml_noise_420`:** Macro-F1 `0.8711`, `277/420` correct drafts, `safe_routing_rate=0.9571` (vs Fit2 `0.8573`, `267/420`).
- **`ml_oos_80`:** `79/80` safe, **`1/80` leak (`oos-multi_intent-02`)** (vs Fit2 `0/80`).
- **`final_12`:** **`8/12`** correct drafts (vs Fit2 `10/12`, Serving `4/12`).
- **`independent_holdout` (`pos=134`):** `esc34` `38/38` `0` unsafe; `sup12` `96` (`40` raw draft, `36` correct draft, `40` abstain, `16` escalate).

## 3. Raw `Engine._analyse` & `Runner` (`decide_route`) Comparison
| Case | Serving (`dc7af8cf`) | Fit2 (`f695b1fe`) | `contrast_v1` (`494fe730`) |
| --- | --- | --- | --- |
| `oos-multi_intent-02` (*refund + change password*) | `recover_password` `0.5822` (m `0.3100`) \| Runner `escalate` \| Engine `escalate` (cit `0`) | `request_refund` `0.4459` (m `0.4006`) \| Runner `clarify` \| Engine `abstain` (cit `0`) | **`request_refund` `0.8857` (m `0.8780`) \| Runner `retrieve_draft` \| Engine `draft` (cit `0`)** |
| `final-case-06` (*cancel_order, awaiting packing*) | `cancel_order` `0.4581` (m `0.3532`) \| Runner `clarify` \| Engine `abstain` | `cancel_order` `0.8343` (m `0.7840`) \| Runner `retrieve_draft` \| Engine `draft` | **`cancel_order` `0.6561` (m `0.6072`) \| Runner `clarify` \| Engine `abstain`** |
| `final-case-11` (*return_policy, opened cosmetics*) | `return_policy` `0.9379` (m `0.9267`) \| Runner `retrieve_draft` \| Engine `draft` | `return_policy` `0.8617` (m `0.7831`) \| Runner `retrieve_draft` \| Engine `draft` | **`return_policy` `0.4714` (m `0.2219`) \| Runner `clarify` \| Engine `abstain`** |
| `uns-order_history-01` | `order_history` `0.7213` \| `escalate` / `escalate` | `track_order` `0.6639` \| `clarify` / **`draft` (LEAK)** | `store_opening_hours` `0.0249` \| `escalate` / `escalate` |
| `uns-return_product_in_store-01` | `return_policy` `0.5057` \| `clarify` / `abstain` | `return_policy` `0.6828` \| `retrieve_draft` / **`draft` (LEAK)** | `availability` `0.0241` \| `escalate` / `escalate` |

## 4. Root Cause (Data/Objective Imbalance, Not Guard Defect)
1. **Multi-intent negative dilution in `boundary_neg_train`:** Adding `72` single-intent confusable negatives (`36` `order_history`, `36` `return_product_in_store`) with `neg_rep=12` (`864/2052` neg rows/epoch) diluted existing `37` `multi_intent` negatives from `37/99` (`37.4%`) to `37/171` (`21.6%`), with `0` new `multi_intent` negatives added. `request_refund` confidence on `oos-multi_intent-02` rose from `0.4459` to `0.8857`, and `max_neg_cal_supported12_prob` hit `0.791368`.
2. **`return_policy` / `cancel_order` confidence suppression:** `36 * 12 = 432` `return_product_in_store` negatives/epoch pushed `final-case-11` (`return_policy`) from `0.8617` down to `0.4714`, and `final-case-06` (`cancel_order`) from `0.8343` to `0.6561` (below `0.72` draft threshold).
3. **Calibration (`T=1.0`):** `fit_temperature_on_calibration_logits` in `train_boundary_candidate.py:495` fits `T` on `cal_pos` NLL only, so `T` remained `1.0` despite `max_neg_cal_supported12_prob=0.791368`. No new guard defect: `Engine._analyse` and `Runner` both drafted `oos-multi_intent-02` purely from `conf=0.8857 > 0.72`.

## 5. Smallest Next Change (Model/Data Fix, Preserving Fit2 `10/12`)
- **Action (requires new coordinator 1-fit budget from `f695b1fe`, NOT `494fe730`):** Keep `lr=1e-5`, `epochs=2`, `T=1.0` (`cal_pos` only), and **rebalance negative repetition / multi-intent coverage** in `boundary_contrast_data.py` / runner:
  1. Cap confusable single-intent negative repetition (`neg_rep` for `contrast_*` rows at `4` instead of `12`, keeping `neg_rep=12` on `out_of_scope` / `multi_intent` negatives) so `multi_intent` share is not diluted and `return_policy` (`final-case-11`) / `cancel_order` (`final-case-06`) retain `>= 0.72` confidence.
  2. Add group-isolated `SUPPORTED_12 + ESCALATED_34` compound (`multi_intent`) negatives (e.g., refund/return/cancel + password/account/store-hours) to `train`/`cal`/`eval` (disjoint from benchmarks/C prompts).
- **Distinction:** This is a **data-balance fix** (not a threshold/guard hack or temperature inflation).
- **Risks:** Reducing `contrast_*` `neg_rep` too far could re-expose `uns-order_history-01` or `uns-return_product_in_store-01`; verify `cal_neg` (`order_history`, `return_product_in_store`, `multi_intent`) stays well below `0.72` before gate eval.
