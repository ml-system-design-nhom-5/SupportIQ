# Design: Return-channel routing guard

- **Status:** Draft
- **Owner:** ML engineer
- **Reviewers:** team
- **Last reviewed:** 2026-11-17
- **Related:** ESC-02, ESC-04, NFR-05; [label definitions D2](intent-label-definitions.md#d2-a-named-return-channel-selects-the-channel-intent), [multi-request detection](multi-request-detection.md), [evaluation protocol](intent-evaluation-protocol.md), [ADR-0026](../decisions/0026-frozen-intent-scenario-set.md); [DATA-25](../rules/data-and-ml.md), [DATA-28](../rules/data-and-ml.md#leakage), [DATA-58](../rules/data-and-ml.md)

## Summary

Under [D2](intent-label-definitions.md#d2-a-named-return-channel-selects-the-channel-intent), a return request that names a channel (a store or branch, the post, a courier pickup) belongs to `return_product_in_store` or `return_product_online`. Both intents are outside the 12 supported intents, so these requests must escalate (ESC-02). The candidate model `v1.1.0` often labels them `return_product` or `return_policy` with high confidence, and routing then sends them to drafting. This design adds a deterministic guard: when the routed intent is `return_product` or `return_policy` and the message names a return channel, the message is escalated to `returns_support` instead of drafted. The model, its labels, and its training data do not change.

## Goals and non-goals

### Goals

- No message that names a return channel reaches drafting as `return_product` or `return_policy`.
- Keep drafting for return requests and return-policy questions that name no channel.

### Non-goals

- Changing D2, the 46 labels, or the frozen scenario set.
- Fixing the classifier's weak `product_issue` recognition (see [Background](#background)); it is reported, not solved here.

## Background

The gate run of 2026-11-13 (`v1.1.0` with policy `v3`, [multi-request detection](multi-request-detection.md#gate-run-on-the-frozen-set-2026-11-13)) failed only because two must-not-draft messages reached drafting. The report names them by case ID: `unsupported-product_issue-02` and `unsupported-return_product_in_store-01`. Their texts were not read (ADR-0026). Only the intents in those IDs directed this work, and this is recorded as test feedback (DATA-28).

To work without the frozen set, a new dev file `data/intent/dev_escalation/v1/cases.synthetic-dev-only.psv` (52 rows) was written. It has 20 `product_issue` messages, 10 of each channel-return intent, and contrast rows for `return_product`, `return_policy`, `request_refund` and `delivery_issue`. Two rows were removed as near-duplicates of benchmark or training text. Measured with `v1.1.0` and policy `v3`:

| Dev data | Must-escalate messages drafted |
|---|---|
| `product_issue` (20) | 0: the model rarely predicts `product_issue` (1/20) but gives the other labels low confidence, so routing escalates or clarifies |
| `return_product_in_store` (10) | 2, labelled `return_policy` with confidence 0.80–0.92 |
| `return_product_online` (10) | 2, labelled `return_product` / `return_policy` with confidence 0.85–0.99 |
| `dev/v1` channel-return rows | 2, labelled `return_product` with confidence 0.92–0.93 |

Channel returns therefore leak with high confidence, which thresholds cannot catch. `product_issue` does not leak on dev, so no change is proposed for it.

## Design

### Components

| Component | Change |
|---|---|
| `apps/core_backend/intent/channels.py` (new) | `names_return_channel(text) -> bool`: a pure function with a fixed cue list. |
| `apps/core_backend/intent/schemas.py` | `RoutingContext.return_channel_named: bool = False`; `IntentPolicy.return_channel_guard: bool = False`. |
| `apps/core_backend/orchestration/pipeline_runner.py` | Sets `return_channel_named` from the pseudonymized message before routing. |
| `apps/core_backend/intent/routing.py` | New gate 2e, after gate 2d and before the confidence gate. |
| `apps/core_backend/config/policies/intent_policy.v3.json` | `"return_channel_guard": true`. |
| `pipeline/evaluation/autoeval/ml_suite.py`, `pipeline/evaluation/tune_routing.py` | Set the context flag with the same function, so evaluation measures what serving does. |

### Cue list

A message names a return channel when it contains, as whole words and case-insensitively:

- **in store:** `store` (but not `store credit` or `app store`), `shop`, `branch`, `outlet`, `counter`, `mall`, `in person`, `walk in`;
- **remote:** `post office`, `by post`, `post … back`, `mail`, `courier`, `pickup` / `pick up`, `collect`, `website`, `online return`, `return … online`.

### Gate 2e: return channel named

If `return_channel_guard` is on, `return_channel_named` is true, and the routed intent is `return_product` or `return_policy`, the decision is `escalate` to `returns_support` with reason `return_channel_named`. `predicted_intent` and `final_intent` stay unchanged. A staff override skips the gate. Earlier gates (human request, invalid output, escalated intents, multiple requests) keep their outcome.

### Contracts

`return_channel_named` is a new routing reason. It refines ESC-02 like `multiple_requests` does, and needs the same contract-owner decision ([multi-request detection, open questions](multi-request-detection.md#open-questions)).

## Errors and guardrails

| Failure | Behavior | Test |
|---|---|---|
| A return-policy question names a channel ("is there a fee to return by post?") | Escalated instead of drafted. A draft is never sent without staff anyway; the cost is a manual answer | Dev measurement below; unit test |
| A cue word appears in another sense ("I bought it at the mall") | Escalated only if the intent is in the return family; otherwise unaffected | Unit tests |
| The guard is off or absent from the policy | Behavior equals policy `v3` without the guard | Unit test |

The guard only adds escalations; it never turns an escalation or a clarification into a draft.

## Alternatives considered

- **Retrain with more channel-return rows.** Possible later; it takes a 40-minute training run and still leaves confident errors. The guard enforces D2 directly.
- **Raise the confidence thresholds of `return_product` and `return_policy`.** The leaks have confidence 0.80–0.99, so this would block most correct drafts as well.
- **Guard only in-store cues.** The gate failure was an in-store case, but dev shows remote-channel leaks too, and D2 treats both channels the same.

## Testing and evaluation

- Unit tests: the cue list (positive and negative examples, `store credit`), gate 2e for each intent family, off without the policy flag, override skip.
- Dev (prototype, policy `v3`, all dev files): must-escalate messages drafted 6 → 0. Supported messages escalated by the guard: 2, both `return_policy` questions about a channel's rules. The cue list was written by the author of the dev rows, so these numbers are optimistic.
- Gate: one more ML run on the frozen set with `v1.1.0` and policy `v3` plus the guard. That will be the **third** decision based on the frozen set. ADR-0026 says to revisit the set once it has been used for more than three, so any later decision triggers that revisit.

### Results (2026-11-13)

**Dev.** `tune_routing` was rerun with the guard on and `dev_escalation` counted as dev data. The selected settings are unchanged (see [multi-request detection](multi-request-detection.md#dev-tuning-result-2026-11-13)). Must-escalate dev messages drafted: 6 with policy `v2`, 0 with `v3` and the guard. Every dev target is met (multi-request flag rate 0.90, false flags 0, clarify rate 0.118, out-of-domain flag rate 1.0). `intent_policy.v3.json` now has `"return_channel_guard": true`.

**Gate run** (`artifacts/evaluation/autoeval/20261113-002948-intent-v1-candidate-v1.1.0-policy-v3-guard/`, evaluation-only approved copy of `v3` as before):

| Metric | `v1.0.0` + `v2` (release) | `v1.1.0` + `v3` | `v1.1.0` + `v3` + guard | Target |
|---|---|---|---|---|
| Must-not-draft cases drafted | 4 | 2 | **1** (`unsupported-product_issue-02`) | 0 |
| Out-of-scope, vague, multi-intent flagged | 0.931 | 0.931 | 0.931 | ≥ 0.90 |
| Draftable messages reaching a draft | 0.489 | 0.898 | 0.886 | — |
| Clarify rate on draftable messages | 0.398 | 0.091 | 0.091 | ≤ 0.15 |
| Drafts with a wrong intent | 12 | 5 | 4 | — |
| Escalation team accuracy | 0.747 | 0.861 | 0.865 | — |
| Macro-F1 drop on noisy text | 0.160 | 0.107 | 0.107 | ≤ 0.10 |

The guard fired on two frozen-set messages: it closed `unsupported-return_product_in_store-01` and escalated one draftable message (draft rate −0.012, within the 0.02 tolerance).

**Verdict: the gate still fails** (rules 1 and 2): one `product_issue` message reaches drafting. The dev `product_issue` rows did not reproduce this leak, so no routing change is supported by dev evidence. `v1.0.0` stays in service.

This was the **third** decision based on `data/benchmarks/intent/v1`. [ADR-0026](../decisions/0026-frozen-intent-scenario-set.md) says to revisit the set once it has been used for more than three release decisions, so the next decision triggers that revisit. Three rounds of gate feedback have steered this work: the multi-intent slice, then the two failing case IDs. Further gate runs on this set would weaken it as evidence.

## Rollout

1. This design approved.
2. PR: cue function, gate 2e behind `return_channel_guard`, context flag in the runner and evaluation, tests, policy `v3` flag.
3. Gate run, then the ADR-0026 review.

Rollback: set `return_channel_guard` to false.

## Open questions

- **D2's rationale conflicts with the KB.** D2 says the KB documents only the in-app return process. The approved KB document "Return and Exchange Request Process and Steps on Tiki App" describes courier pickup and drop-off at partner post offices as part of that process. Remote-channel requests are still outside the 12 supported intents (requirements §3.2), so the guard follows D2. The team should decide whether D2's rationale needs correcting. The frozen set's labels must not change because of this (DATA-23).
- `product_issue` is recognised in only 1 of 20 dev messages, although none reaches drafting. More training rows are a candidate for the next training run.
