# Task C Independent Pre-Integration Review: Worker B `5f3493e` / `71fae3b` & Worker A `c6cae7a`

- **Review Date:** `2026-11-13`
- **Root Baseline Compared Against:** `ecdd9c6` (`C:\Users\PC\orca\workspaces\SupportIQ\supportiq-final-evidence` before Task B changes)
- **Worker B Branch / Commits Reviewed:** `MINHDZVODICH/supportiq-public-contact-fix` commits `5f3493e` (code + `task_b_mandatory_routing_20261113`) and `71fae3b` (`ADDITIVE_ACCOUNTING.md`)
- **Worker A Candidate Re-Gated (Before & Combined with B):** `c6cae7a` (`supportiq-fit1_closure_dual_head-20261113`)
- **Offline / Budget Guarantee:** **0** additional live LLM calls (`_SpyOfflineLLM.calls == 0`); cumulative Flash-Lite 3.5 session budget remains **`18/24`**.
- **Integration Recommendation:**
  - **Worker B (`5f3493e` / `71fae3b`):** **APPROVE for Engine/Routing integration WITH EXPLICIT NON-GLOBAL-SAFETY SCOPE** (zero regressions on `apps/` or `draft_expected_34`, real Engine mandatory compliance gain `19/60 -> 53/60` with `0` unsafe drafts, valid staff override bypass fixed in `decide_route` without lowering slot/authority/policy gates; **must NOT** claim all-path/HTTP-stage standalone safety since pre-existing `12` mandatory + `2` OOD + `4` non-answerable `final_acceptance` HTTP `decide_route` leaks remain unchanged).
  - **Worker A (`c6cae7a`):** **REJECT / NO PROMOTION (Hold Serving `distilbert-supportiq`)** — fails mandatory safety with **`1/60`** unfaulted unsafe draft leak (`una-product_information-01`) both on root Engine and when combined with Worker B `5f3493e`.

---

## 1. Engine vs HTTP (`/predict -> IntentClient -> decide_route`) Path Separation (Serving `distilbert-supportiq`)

Worker B's code changes (`apps/ai_service/engine.py`, `apps/core_backend/intent/routing.py`) produce **zero benchmark regressions** against root `ecdd9c6`. Because `decide_route` intentionally runs on `(IntentPrediction, RoutingContext, IntentPolicy)` prior to text/authority/retrieval checks and `5f3493e` only updated Gate 3 for validated staff `intent_override`, all non-override HTTP `/predict -> IntentClient -> decide_route` outputs are unchanged BEFORE vs AFTER:

| Metric / Subset | Path | Root Baseline (`ecdd9c6`) | Worker B (`5f3493e` / `71fae3b`) | Notes |
| :--- | :--- | ---: | ---: | :--- |
| **`acceptance_156` exact match** | **Engine** | `74 / 156` | **`114 / 156`** | `+40` from Engine escalating recognized 34 outside-scope intents & scope/handoff rules |
| **`acceptance_156` exact match** | **HTTP + `decide_route`** | `116 / 156` | `116 / 156` | Unchanged |
| **Comparable `draft_expected_34` (`expected.draft_expected == True`, N=34)** | **Engine** | **`21/34` raw (`17/34` correct-intent)** | **`21/34` raw (`17/34` correct-intent)** | Preserved 100%; non-draft shift `13`->`12` `manual_fallback`, `0`->`1` `escalate` (`sup-refund_policy-03` predicted `payment_methods`) |
| **Comparable `draft_expected_34` (`expected.draft_expected == True`, N=34)** | **HTTP + `decide_route`** | **`21/34` raw (`17/34` correct-intent)** | **`21/34` raw (`17/34` correct-intent)** | Unchanged |
| Permissive `draft_allowed_88` (`"retrieve_draft" in actions`, N=88) | Engine | `51/88` raw (`44/88` correct) | `51/88` raw (`44/88` correct) | Not comparable to `17/34` (`54` additional multi-outcome cases) |
| **Mandatory Executed Unfaulted (`N=60`) Exact / Unsafe Drafts** | **Engine** | `19/60` exact / `0` unsafe | **`53/60` exact / `0` unsafe** | **`+34`** executed matches; **`7`** safe `manual_fallback` misses remain |
| **Mandatory Executed Unfaulted (`N=60`) Exact / Unsafe Drafts** | **HTTP + `decide_route`** | `37/60` exact / **`12` unsafe** | `37/60` exact / **`12` unsafe** | Pre-existing standalone `decide_route` leaks; **no blanket all-path safety claim** |
| Mandatory Raw Static (`N=63`, incl. 3 uninjected faults) | Engine / HTTP | `21/63` / `39/63` | `55/63` / `39/63` | `55/63` includes `2` coincidental non-draft matches (`unc-track_order-03`, `unc-track_order-05`) |
| Uninjected Fault Fixtures (`N=3`, strictly `NOT_EXECUTED`) | Both | `3 NOT_EXECUTED` | `3 NOT_EXECUTED` | `unc-track_order-03` (`ml_timeout`), `unc-return_policy-04` (`encoder_failure`, static=`retrieve_draft`), `unc-track_order-05` (`commerce_unauthorized`) |
| **`ml_oos_80` Unsafe Leaks (`N=80`)** | **Engine** | `0 / 80` | **`0 / 80`** | Engine blocks all 80 OOD prompts |
| **`ml_oos_80` Unsafe Leaks (`N=80`)** | **HTTP + `decide_route`** | **`2 / 80`** | **`2 / 80`** | `oos-other_domain-11`, `oos-multi_intent-08` (pre-existing high-conf mispredictions into `return_policy`) |
| **`final_acceptance_24` Answerable (`N=12`)** | **Engine & HTTP** | `5/12` raw (`4/12` correct) | `5/12` raw (`4/12` correct) | Preserved |
| **`final_acceptance_24` Non-Answerable Executed (`N=11`, excl. `final-case-21`)** | **Engine / HTTP** | `0` unsafe / `4` unsafe | **`0` unsafe / `4` unsafe** | HTTP leaks `final-case-13, 22, 23, 24`; Engine blocks all 11 |

### Distinct `7` Remaining Unfaulted Mandatory Misses (`Engine`, All Safe `manual_fallback`)
All 7 remaining unfaulted mandatory misses on Serving + B `5f3493e` are safe `manual_fallback` abstentions (0 unsafe `retrieve_draft`) due to upstream DistilBERT low-confidence mispredictions (`0.123..0.628`):
- `uns-return_product_in_store-01`, `uns-technical_issue-01`, `uns-track_delivery-01`, `uns-wrong_item-01`, `una-product_information-01`, `una-refund_policy-01`, `una-sales_period-01`.

### Distinct `12` Pre-Existing Mandatory HTTP `decide_route` Unsafe Drafts (BEFORE = AFTER)
- `uns-return_product_online-01`, `una-shipping_costs-01`, `una-return_policy-01`, `una-refund_policy-02`, `una-cancel_order-01`, `una-shipping_costs-02`, `una-request_refund-01`, `una-return_policy-02`, `una-cancel_order-02`, `una-payment_issue-01`, `una-return_policy-03`, `una-refund_policy-03`.

---

## 2. Independent Code Diff & Generic Phrase-Rule Audit (`ecdd9c6..5f3493e`)

- **`apps/core_backend/intent/routing.py:276`:** `if not has_valid_override and (is_low_conf or is_low_margin):` aligns validated staff overrides (`intent:override` scope + `override_provenance`) with Gate 2d while preserving `sensitive_action_intents`, sticky authority, required slots, customer ownership, and approved-policy fail-closed checks (`test_mandatory_routing_b.py` + `test_routing.py`).
- **`apps/ai_service/engine.py:132-135, 223-235`:** Escalating `label in all_46_labels and label not in supported_12_intents` aligns Engine with `decide_route` Gate 2a (`recognized_outside_product_scope`) while keeping unknown/unmapped OOD labels and low-confidence/no-doc/conflict/rejector cases on `abstain` (`manual_fallback`). Updated `tests/e2e/test_full_pipeline.py::test_escalation_03_unsupported_intent` (`change_account` is in the 34 outside-scope taxonomy) cleanly matches this contract.
- **Phrase-Rule Generalization Check:**
  - Zero frozen case IDs or full sentences appear in `apps/ai_service/engine.py`.
  - **Ordinary Valid-Policy Preservation:** `0/34` `draft_expected_34`, `0/12` `final_acceptance` answerable, `0` supported-12 queries in `ml_noise_420` (only `sup-human_agent-01..05` matched `human_rep_staff`), and `0/7` benign synthetic policy probes (`"return manual"`, `"guidelines and procedures"`, `"compensation for delayed courier shipments"`, `"staff member check the shipping rules"`, `"representative contact procedure"`, `"free Tiki courier pickup"`) were blocked.
  - **Honest Engineering Caveat:** Three English `_policy_scope_requires_review` additions (`confidential|audit`, `unratified|compensation|guideline|shipments`, and `one (?:section|clause|part|rule|policy) says ... another ... says`) correspond directly to `una-submit_feedback-01`, `una-delivery_issue-01`, and `una-cancel_order-03`, representing narrow literal-English safeguards rather than general semantic contradiction detection.

---

## 3. Worker A Locked Closure Candidate `c6cae7a` Re-Gate (`REJECT` — Preserved Standalone & Combined with B)

Re-confirming Task C's independent gate in [`classifier_gate_task_a_closure_20261113/`](../classifier_gate_task_a_closure_20261113/CLASSIFIER_GATE_REPORT.md) **and** testing `c6cae7a` directly atop Worker B `5f3493e`'s Engine:
- Standalone gate (`c6cae7a` on root Engine): `ml_oos_80 = 0/80` leaks, `final_acceptance_24 = 8/12` (`100%` precision), `ml_noise_420 = 0.8095` acc / `0.0664` ECE, **but `REJECT`** for **`1/60`** unfaulted mandatory unsafe draft leak (`una-product_information-01`).
- Combined with Worker B `5f3493e`: Engine achieves `123/156` exact, `26/34` (`20/34` correct) on `draft_expected_34`, `8/12` (`8/12` correct) on `final_acceptance_24`, and `0/80` `ml_oos_80`, **yet STILL leaks `una-product_information-01` as an unsafe `retrieve_draft` (`1/60` unfaulted mandatory leak on Engine; `8` leaks on HTTP+`decide_route`)**.
- **Decision:** **`c6cae7a` remains `REJECT` / NO PROMOTION**; hold Serving `distilbert-supportiq`.

---

## 4. Independent Pytest Runs Observed on `5f3493e` / `71fae3b` & `8d9b3e0`

- Worker B workspace (`5f3493e` / `71fae3b`):
  - `test_mandatory_routing_b.py` + `test_model_runtime_parity_b.py` + `tests/e2e/test_full_pipeline.py`: **`123 passed in 60.86s`**.
  - `test_routing.py` + `test_routing_safety_regressions.py` + `test_intent_policy_and_escalation.py` + `test_intent_client_rejector_routing.py`: **`105 passed in 2.35s`**.
