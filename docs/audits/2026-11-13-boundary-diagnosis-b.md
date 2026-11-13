# Worker B: supported/unsupported boundary diagnosis and live-draft review (Ponytail ULTRA)

Base `e4adafd`. Scope: analysis + tests only. No production routing/threshold change, no model/holdout/plan edits, 0 new LLM calls (shared budget 21/24 stays).
Tests: `tests/unit/test_supported_unsupported_boundary_b.py` (24 pass, 1 strict xfail).

> Limit: the Fit2 checkpoint (`f695b1fe`, workspace `supportiq-final-routing`) is no longer on disk, so Fit2 was **not re-run**. Fit2 numbers below are copied from the committed audit (`closure-round-acceptance.md`, `three_model_comparison.json`). Fit2 top-k/margin for the two leak cases is not recorded; any "neighbour probability" claim for Fit2 is therefore unverified.

## 1. Boundary diagnosis

Case texts (`data/benchmarks/system/v2/acceptance/cases.jsonl`): *"Where can I view the complete list of all my past orders from last year?"* (order_history) and *"Can I drop off my online return at a local physical shop branch?"* (return_product_in_store).

| Layer | order_history -> track_order (conf 0.664, thr 0.65) | return_product_in_store -> return_policy (conf 0.683, thr 0.65) |
|---|---|---|
| Model | Wrong closed-set neighbour; 0.014 above threshold | Wrong neighbour; 0.033 above threshold |
| Calibration | Fit2 `T=1.0`, uncalibrated for the 34-intent tail; thresholds (0.65) were set for older, less sharp models | same |
| Selective rejection | `selective_rejector.enabled=false` for Fit2 (old closure had it on and rejected both) | same |
| Slot guard (`decide_route` Gate 6) | stops it (`missing_order_id`) in bare route and Runner; **absent in `Engine._analyse`** -> `draft` | no slot exists -> nothing stops it |
| Text safety (`evaluate_text_safety`) | no pattern | no pattern (only postal-pickup/account-closure/tax) |
| Engine entropy/top_k check | not triggered (Fit2 peaked) | same |

Bare route vs exposed surface:
- order_history: bare `decide_route` = `clarify` (not a draft leak), Runner = `clarify`; **Engine = `draft`** (exposed via `apps/backend` -> `ai_service`). The leak exists only because Engine lacks the slot gate that `decide_route` has. Confirmed by tests (`test_engine_has_no_slot_guard_parity_with_decide_route`).
- return_product_in_store: leaks at **all three** layers (bare `retrieve_draft`, Engine `draft`, Runner `retrieve_draft`) because nothing but confidence guards it. Pure model/calibration error.

Generalizable pattern (not two strings): the supported intent has an unsupported *sibling that shares vocabulary* (track_order~order_history, return_policy~return_product_in_store/online/exchange_*). Sharper models (Fit2 acc 0.86 vs 0.65 noise suite) concentrate probability on the sibling-confusable supported label, so a flat 0.65 confidence floor no longer separates them. This is not Fit2-specific: `supportpilot-distilbert` predicted return_policy at **0.931** and drafted on the same in-store case; Serving leaks `sh-esc-01` (return_product -> return_policy 0.73, bare/Engine/Runner draft) on the sealed set. The sealed holdout (`sealed_holdout_predictions.jsonl`) has no recognised-unsupported-neighbour slice (slices: supported_answerable, novel_ood, mandatory_escalation_compound), so it could not have caught this; Fit2 shows 0 leaks there.

## 2. Recommendations (ranked)

1. **Model/data (A, not a guard effect):** train/calibrate with hard-negative neighbours for each supported intent (order_history, return_product_in_store/online, exchange_*), and report per-pair confusion with confidence histograms; calibrate the 34-intent tail jointly (T=1.0 is the reason confident wrong siblings survive). Re-set per-intent thresholds on a neighbour-inclusive calibration set.
2. **Shared guard, justified for order_history only:** make `Engine._analyse` apply the same order-id slot gate as `decide_route` Gate 6 (single shared helper, derived from `PERSONAL_ORDER_REQUIRED`). Genuinely justified: it is an existing contract the exposed surface violates (Engine/bare disagree on identical input). It would turn `uns-order_history-01` Engine `draft` -> non-draft. It would **not** fix return_product_in_store and must not be credited for any model improvement.
3. **Do not add lexical in-store/order-history regexes** as the fix: that is benchmark-shaped (cf. postal-pickup pattern, which is the only such precedent), brittle against paraphrase. Prefer a neighbour-aware rule if a guard is wanted: abstain when top_k contains a 34-intent sibling of the predicted label above a probability floor. Needs Fit2 top_k to size; not verifiable now.
4. Add a recognised-unsupported-neighbour slice with paraphrases to C's holdout (C owns it).
5. Gate acceptance should keep reporting bare/Engine/Runner separately (as the closure report already does); the Fit2 REJECT stands.

Tests added (synthetic predictions, no benchmark strings): slot guard sweep above threshold; no-barrier characterization for return_policy; negative control that every recognised-unsupported neighbour never drafts at any confidence in bare and Engine; supported paraphrases not blocked by text safety; text safety covers only postal pickup; Engine slot-parity as strict xfail (flips to a failure, prompting removal of the marker, once the guard exists).

## 3. Live-draft review (coordinator-delegated AI review, 0 human participants, not a user study)

Source: commit `2e3ff4d4`, files recovered under `artifacts/evaluation/classifier_vs_serving_live_20261113/` (no other branch content). Transport confirms 3 HTTPS 200 calls to `gemini-3.5-flash-lite`, BGE index `bge-small-en-v1.5`, `max_attempts=1`. Limitation: `raw_records.json` stores the sanitized post-pipeline draft (segments + citations), **not** the unvalidated raw model string; thoughts tokens not recorded. Source-ID validation (citation S1 in retrieved set) proves provenance only; entailment below was judged by reading text vs snippet.

Reported counts reproduced from the data: intent correct Serving 1/3 (case-10) vs Fit2 3/3; drafts with correct intent Serving 0/3 (its only draft, case-02, has wrong label return_policy vs expected return_product) vs Fit2 2/3. Caveat: Serving's case-02 draft is content-correct (right doc POL-RET-002); Fit2 abstained there (return_product 0.13, `requires_authority`). Useful drafts: Serving 1, Fit2 2. n=3, not a rate.

| Arm / case | Claim (draft) | Source (cited) | Verdict |
|---|---|---|---|
| Serving 02 (Q: submit return, schedule free pickup) | App path Account > Order Management > Delivered > Request Return/Exchange | POL-RET-002 S1 same path | Supported |
| | Reason + 3-5 photos/video of defect | same | Supported |
| | Courier picks up from your address free in 1-2 business days | same | Supported |
| | Or drop off at partner post office | same | Supported |
| | Omission/authority | Question asks to *schedule* pickup; source describes none, draft does not say so. Return is sensitive (`return_product`), but wrong label `return_policy` skipped `requires_authority` and manager queue. Privacy: none (no order id/PII) | Minor omission; authority-routing gap from the misclassification |
| Fit2 03 (Q: refund approval requirements; shipping fee on preference return) | Processed once canceled before dispatch or after warehouse inspects return | POL-REFUND-001 "**only** processed once..." | Supported but drops "only" (requirement becomes weaker than source) |
| | Decisions need reconciliation by authorized staff; AI cannot approve money | same | Supported; no approval promised. Exposes internal AI-governance wording to customer |
| | Original shipping fee non-refundable if personal preference | same | Supported, answers 2nd part |
| Fit2 10 (Q: shows delivered, never received) | Contact support in 24-48h via hotline 1900 6035 | POL-SHIP-004 | Supported; hotline present (no `[PHONE_OR_NUMBER]` here). "24-48h" start point ambiguous in source and draft |
| | Team verifies courier GPS logs, coordinates hub, resolves | same | Supported ("then" adds sequencing, benign) |
| | If **confirmed** lost: replacement or 100% refund | source: "If an order is lost" | Supported; "confirmed" is an added qualifier (conservative). Monetary commitment: staff must verify authority; intent `delivery_issue` not flagged sensitive |

Other findings: all 3 drafts have no unsupported claim and single citation S1 matching the top retrieved doc; `executed_order_context` differs from benchmark `order_context` (e.g. case-10 executed `shipped/delayed` vs case `delivered`; case-03 `delivered/under_review` vs `returned/pending_inspection`) because tickets use demo orders; drafts did not use order data, so no effect here, but it weakens order-aware claims. Fit2 draft gain here comes from the model (confidence 0.90/0.89 vs Serving 0.44/0.26), not from guards.

Overall: all 3 live drafts (10 claims) are supported by their cited source, with 3 wording/omission caveats; the headline gap is classifier confidence/labelling, and this 3-case sample cannot offset the Fit2 mandatory leaks. Candidate REJECT stands.

> Evidence labels (coordinator update): all Fit2 (f695b1fe) numbers and the live Fit2 drafts are HISTORICAL reports, not re-run; Fit2 and its 95a940b6 init checkpoint are unavailable. The reproducible paired comparison is Serving dc7af8cf vs A's new candidate (from unchanged Serving). Archive verification (main artifacts/models/candidates, hashes, reload) is pending A and not done here.
