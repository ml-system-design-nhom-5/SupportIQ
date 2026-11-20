# Task B Additive Accounting Clarification (`5f3493e` vs BEFORE `0772d09`)

This additive note clarifies three accounting points for commit `5f3493e` on branch `MINHDZVODICH/supportiq-public-contact-fix` against parent merge commit `0772d09`, without modifying the original `REPORT.md`, `summary.json`, or `raw_predictions.jsonl` bytes. Data was generated offline on identical inputs with serving model `F:/Năm 3/SD/project/SupportIQ/artifacts/models/trained/distilbert-supportiq` and zero live LLM calls (`_SpyOfflineLLM.calls == 0`), recorded in `additive_before_after_accounting.json`.

---

## 1. Exact `draft_expected_34` (`exp.get("draft_expected") == True`, N=34) vs Permissive `draft_allowed_88` (N=88)

Previous Task C reports measure supported/answerable draft eligibility over the **34** cases in `data/benchmarks/system/v2/acceptance/cases.jsonl` where `expected["draft_expected"] == True` (`sup-return_policy-01..05`, `sup-refund_policy-01..05`, `ans-return_policy-01..10`, `ans-refund_policy-01..08`, `ans-cancel_order-01..06`).
By contrast, the earlier `88`-case figure (`"retrieve_draft" in expected["actions"] and not must_escalate`) swept in `54` additional cases (e.g., personal order/slot cases and multi-intent/noise cases where `retrieve_draft` is one of several allowed outcomes alongside `clarify`/`escalate`). Those two denominators must not be conflated.

| Subset | Path | BEFORE (`0772d09`) Raw Draft | BEFORE (`0772d09`) Correct-Intent Draft | AFTER (`5f3493e`) Raw Draft | AFTER (`5f3493e`) Correct-Intent Draft |
| --- | --- | ---: | ---: | ---: | ---: |
| **Task C `draft_expected_34` (N=34)** | In-process `Engine` | **21 / 34** | **17 / 34** | **21 / 34** | **17 / 34** |
| **Task C `draft_expected_34` (N=34)** | HTTP `IntentClient -> decide_route` | **21 / 34** | **17 / 34** | **21 / 34** | **17 / 34** |
| Permissive `draft_allowed_88` (N=88) | In-process `Engine` | 51 / 88 | 44 / 88 | 51 / 88 | 44 / 88 |
| Permissive `draft_allowed_88` (N=88) | HTTP `IntentClient -> decide_route` | 39 / 88 | 33 / 88 | 39 / 88 | 33 / 88 |

Note on `draft_expected_34` non-draft counts (`Engine`): BEFORE `0772d09` had `13` `manual_fallback` and `0` `escalate`; AFTER `5f3493e` has `12` `manual_fallback` and `1` `escalate` (1 misclassified outside-scope prediction shifted from `manual_fallback` to `escalate`, zero draft-eligible loss).

---

## 2. Strict Unfaulted Mandatory Compliance (`53 / 60`) vs Uninjected Faults (`3 NOT_EXECUTED`)

Uninjected fault-injection fixtures must never be counted as executed passes. Preserving raw unadjusted `55/63` purely for comparison with historical static `21/63`:

- **Executed unfaulted mandatory subset (`N = 60`):**
  - **Engine BEFORE (`0772d09`):** **19 / 60** exact matches, **41** mismatches (all `manual_fallback`), **0** unsafe `retrieve_draft` leaks.
  - **Engine AFTER (`5f3493e`):** **53 / 60** actual executed matches, **7** mismatches, **0** unsafe `retrieve_draft` leaks.
  - The **7** remaining mismatches are safe `manual_fallback` abstentions (distinct from `escalate`) caused by upstream classifier low-confidence mispredictions (`0.123..0.628`): `uns-return_product_in_store-01`, `uns-technical_issue-01`, `uns-track_delivery-01`, `uns-wrong_item-01`, `una-product_information-01`, `una-refund_policy-01`, `una-sales_period-01`.
- **Uninjected fault cases (`N = 3`, strictly `NOT_EXECUTED`):**
  - `unc-track_order-03` (`fault: ml_timeout`): `NOT_EXECUTED` (static misprediction yielded `manual_fallback` BEFORE / `escalate` AFTER without fault injection).
  - `unc-return_policy-04` (`fault: encoder_failure`): `NOT_EXECUTED` (static prediction yielded `retrieve_draft` in both BEFORE and AFTER because encoder failure was not injected).
  - `unc-track_order-05` (`fault: commerce_unauthorized`): `NOT_EXECUTED` (static misprediction yielded `manual_fallback` BEFORE / `escalate` AFTER without fault injection).
  - Why raw static reads `55/63` (`21/63` BEFORE): `2` of the `3` `NOT_EXECUTED` cases (`unc-track_order-03`, `unc-track_order-05`) coincidentally fell inside `expected["actions"]` (`["escalate", "clarify", "manual_fallback"]`) without fault injection. Only `53/60` reflects executed unfaulted coverage.

---

## 3. HTTP `/predict -> IntentClient -> decide_route` BEFORE (`0772d09`) vs AFTER (`5f3493e`): Pre-existing Limitations, No Global Safety Claim

Running the exact same inputs through HTTP `/predict -> IntentClient -> decide_route` for both `0772d09` and `5f3493e` shows **zero difference** on all benchmark subsets (`5f3493e` only modified Gate 3 for validated staff `intent_override` on low-confidence predictions, which never fires on non-override benchmark inputs):

| Benchmark Metric (`HTTP /predict -> IntentClient -> decide_route`) | BEFORE (`0772d09`) | AFTER (`5f3493e`) | Status |
| --- | ---: | ---: | --- |
| `acceptance_156` exact match | 116 / 156 | 116 / 156 | Unchanged (pre-existing) |
| `mandatory` unfaulted matches / mismatches (`N=60`) | 37 / 23 | 37 / 23 | Unchanged (pre-existing) |
| **`mandatory` unfaulted unsafe `retrieve_draft` leaks (`N=60`)** | **12** | **12** | **Pre-existing limitation (0 regressions)** |
| **`ml_oos_80` unsafe `retrieve_draft` leaks (`N=80`)** | **2** | **2** | **Pre-existing limitation (0 regressions)** |
| `final_acceptance` non-answerable unsafe drafts (`N=11` executed) | 4 | 4 | Unchanged (pre-existing) |
| `draft_expected_34` raw / correct-intent draft | 21 / 17 | 21 / 17 | Unchanged |
| `ml_noise_420` (`retrieve_draft` / `clarify` / `escalate`) | 210 / 140 / 70 | 210 / 140 / 70 | Unchanged |

- **Exact `12` HTTP mandatory unsafe drafts (identical BEFORE & AFTER):**
  `uns-return_product_online-01` (`return_policy` at `0.814`), plus `11` unanswerable KB-scope cases (`una-shipping_costs-01`, `una-return_policy-01`, `una-refund_policy-02`, `una-cancel_order-01`, `una-shipping_costs-02`, `una-request_refund-01`, `una-return_policy-02`, `una-cancel_order-02`, `una-payment_issue-01`, `una-return_policy-03`, `una-refund_policy-03`).
- **Exact `2` HTTP `ml_oos_80` unsafe leaks (identical BEFORE & AFTER):**
  `oos-other_domain-11` (income tax return mispredicted as `return_policy` at `0.695`) and `oos-multi_intent-08` (return policy + account closure mispredicted as `return_policy` at `0.960`).
- **Scope & non-global-safety disclaimer:** `decide_route` intentionally evaluates `(IntentPrediction, RoutingContext, IntentPolicy)` prior to text-level safety checks and knowledge retrieval (`Engine` or `PipelineRunner` Step 5). Standing alone without downstream text/authority/retrieval enforcement (`Engine` blocks all `12 + 2 + 4` above with `0` unsafe drafts), the `IntentClient -> decide_route` stage does **not** prevent high-confidence classifier mispredictions or KB-unanswerable requests from requesting retrieval/drafting and therefore does not provide global end-to-end safety by itself.
