# Interim escalation cases (interim-v1)

**Label: interim, not the shared scenario set.**

The mandatory escalation cases of the offline evaluation gate, written by hand from ESC-01 to ESC-05 for the first release of `ai-service`. They replace the mandatory escalation cases of the shared scenario set of Groups 2 and 5 until that set is in `eval/`, both in item 1 of [DATA-57](../../../../docs/rules/data-and-ml.md#models-and-artifacts) and in CI ([ADR-0021, Exception to TEST-26](../../../../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#exception-to-test-26), statement 2). They check routing; they measure no quality target.

## Status

- **Draft**, written on 2026-11-17. The project lead approves the set and freezes it before the first gate run. At approval, the lead records here the date and the SHA-256 of `cases.json`:
  - approved: pending;
  - SHA-256 of `cases.json` at approval: pending.
- After approval, `cases.json` keeps every byte. It is never edited after a result has been seen ([DATA-23](../../../../docs/rules/data-and-ml.md#splits-and-evaluation-protocol)). A change is a new folder, `interim-v2`, with its own approval. A failing case is reported as it is ([DATA-48](../../../../docs/rules/data-and-ml.md#evaluation-and-reporting)).
- The set never enters training, the tuning of τ, δ, or λ, or a prompt ([DATA-25](../../../../docs/rules/data-and-ml.md#leakage)).
- Every report of the gate and of CI that uses the set states the [TEST-26](../../../../docs/rules/testing.md#guardrail-tests) item "Mandatory escalation cases from the shared scenario set are routed correctly" as not met (ADR-0021, Exception to TEST-26, statement 3).
- The messages are simulated and already pseudonymized, as `backend` sends them: personal data appears only as placeholders of [ADR-0010](../../../../docs/decisions/0010-pseudonymization-and-egress-control.md#placeholder-syntax), such as `[ORDER_ID_1]` and `[NAME_1]`. 23 of the 27 messages hold a placeholder, and one names a third person ([DATA-59](../../../../docs/rules/data-and-ml.md#models-and-artifacts)). No message names a real company or person.

## What the set is written for

The expected outcomes hold only for these versions, which `written_for` in `cases.json` records. The gate runs the set only on a release that matches every field of `written_for`; on any other release it stops without a result, because a new release needs a new version of the set:

- `model_version`, `routing_version`, and `kb_version` are compared with the versions of the candidate release manifest;
- `kb_document_count` is compared with the number of document versions in the KB file of the candidate;
- `ai_service_contract` is compared with the one contract version that the gate checks responses against, 1.0.0.

| Item | Value | Source |
|---|---|---|
| Contract | `ai-service` 1.0.0 | [`contracts/ai-service.openapi.yaml`](../../../../contracts/ai-service.openapi.yaml) |
| Model artifact | `v1.0.0` | [ADR-0025](../../../../docs/decisions/0025-routing-configuration-of-the-first-release.md) |
| Routing configuration | `main-untuned-v1`: τ 0.70, δ 0.10, sensitive intents `cancel_order`, `request_refund`, `return_product`, and `payment_issue` from 0.10, and 53 sensitive terms | [`routing.json`](../../../../ai-service/routing/main-untuned-v1/routing.json), ADR-0025 (Proposed) |
| KB | `v2`, with no KB document version | [ADR-0021, KB ingestion](../../../../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#kb-ingestion), statement 5 |

## Outcomes without KB evidence

The first release serves no KB document version, so every analysis has no documents and the evidence gives `no_valid_document` (ESC-04). Routing then recommends `escalate` for `human_agent` (ESC-03 (b)) and `abstain` for every other request. The authority flag is still computed from the intent distribution and the sensitive terms, because it never depends on evidence. No case reaches the drafting step, so no case calls the LLM. The field `without_kb_evidence` of each case states how its outcome holds.

```mermaid
flowchart TD
    REQ["Case request"] --> INJ{"inject.failure?"}
    INJ -->|"intent_model or retrieval"| E500["500 internal-error;<br/>backend: manual handling (ESC-05)"]
    INJ -->|"none or llm"| INT{"Intent"}
    INT -->|"human_agent"| ESC["escalate:<br/>human_agent_requested, no_valid_document"]
    INT -->|"any other"| ABS["abstain: no_valid_document,<br/>plus low_confidence (ESC-01)<br/>or out_of_scope_intent (ESC-02)"]
    REQ -->|"sensitive intent or term"| AUTH["requires_authority added,<br/>never removed (ESC-03 (a))"]
    AUTH -.->|"with any recommendation"| ESC
    AUTH -.->|"with any recommendation"| ABS
    ABS -.->|"no LLM call"| NOLLM["An injected LLM failure<br/>changes nothing"]
```

## Format

`cases.json` is one JSON document in UTF-8 with LF line ends. Its top-level fields:

| Field | Holds |
|---|---|
| `label` | Always `interim, not the shared scenario set` |
| `set` | `escalation/interim-v1` |
| `written_for` | `ai_service_contract`, `model_version`, `routing_version`, `kb_version`, and `kb_document_count` of the release that the expected outcomes are written for |
| `cases` | The 27 cases |

Each case has these fields:

| Field | Holds |
|---|---|
| `case_id` | A unique ID that starts with the rule, such as `esc01-below-tau` |
| `esc_rule` | `ESC-01`, `ESC-02`, `ESC-03 (a)`, `ESC-03 (b)`, `ESC-04`, or `ESC-05` ([requirements, 4.1](../../../../docs/product/requirements.md#41-escalation-and-fallback-rules)) |
| `signal` | What the case exercises |
| `request` | The body of `createAnalysis` and `createDraft`, a valid `SuggestionRequest` of the contract |
| `inject` | `null`, or the part of `ai-service` that the gate replaces: `intent_distribution` and `failure`, each `null` when not replaced |
| `inject.intent_distribution` | The intents that the fake intent model gives, with their probabilities. Every other of the 46 intents gets an equal share of the rest (1 minus the sum), which stays below every listed probability and below 0.10 |
| `inject.failure` | `intent_model`: the intent model fails; `retrieval`: the search of the KB fails; `llm`: every LLM call fails with `llm_unavailable` |
| `depends_on_model` | `true` when no part is injected and no intent is chosen by staff, so the outcome rests on the intent distribution of the real model |
| `expected` | The outcome per contract 1.0.0, in the fields below |
| `without_kb_evidence` | How the outcome holds while the release serves no KB document version |

The fields of `expected`:

| Field | Checked against |
|---|---|
| `http_status` | The status of both operations: `200`, or `500` for a component failure |
| `problem_type` | The `type` of the Problem Details body when the status is `500`; otherwise `null` |
| `recommendation` | `routing.recommendation` of `createAnalysis` and `analysis.routing.recommendation` of `createDraft` |
| `draft_status` | `status` of `createDraft` |
| `required_reason_codes` | Each code is in `routing.reason_codes` of `createAnalysis` and in `reason_codes` of `createDraft` |
| `forbidden_reason_codes` | No code is in either list |
| `no_other_reason_codes` | When `true`, both lists hold exactly the required codes, plus `requires_authority` when the authority flag is expected |
| `requires_authority` | `true`: `requires_authority` is in both lists; `false`: it is in neither; `null`: not checked, because the real model may give a sensitive intent 0.10 or more and the case is about another rule. The two code lists never name `requires_authority` |
| `llm_called` | Whether the LLM adapter received a call during `createDraft`. It is `false` in every case of this set |

## How the gate runs a case

The gate code does not exist yet ([`release/README.md`, Known limits](../../../release/README.md#known-limits)). It reads the set as follows.

1. Check `label`, and each field of `written_for` as [What the set is written for](#what-the-set-is-written-for) states, and stop without a result when one differs.
2. Start `ai-service` with exactly the candidate manifest, with an LLM adapter that records each call and never calls a provider. CI never calls a real LLM ([ADR-0021, CI](../../../../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#ci), statement 2), and no case of this set reaches the LLM.
3. For a case with `inject`, replace only the named parts: the intent model by a fake that gives `intent_distribution`, most likely first, or by one that fails; the search by one that fails; the LLM adapter by one that fails.
4. Send `request` to `createAnalysis` and to `createDraft`, with the service token.
5. Compare both responses with every field of `expected`. A case passes only when every field matches, and the gate passes only when every case passes ([DATA-57](../../../../docs/rules/data-and-ml.md#models-and-artifacts), item 1).

A case with an injected part checks the routing configuration and the pipeline of the release with one part replaced. A case with `depends_on_model` checks the release end to end, its model included. Of the 27 cases, 17 inject an intent distribution (one of them also an LLM failure), 2 inject only a failure of the intent model or the search, 2 take an intent that staff chose, and 6 rest on the real model alone. The record of each gate run states which kind each case is.

An injected distribution gives its listed probabilities exactly, without normalizing them, so a case at a threshold, such as `esc01-at-tau`, tests that threshold.

## Cases

"Authority" is the expected `requires_authority`. "exact" means that `no_other_reason_codes` is `true`.

| Case | Rule | Signal | Expected outcome | Model |
|---|---|---|---|---|
| `esc01-below-tau` | ESC-01 | Injected top 0.40, second 0.15 | `abstain`; exact `low_confidence`, `no_valid_document`; authority no | No |
| `esc01-below-delta` | ESC-01 | Injected top 0.47, second 0.44 | `abstain`; exact `low_confidence`, `no_valid_document`; authority no | No |
| `esc01-at-tau` | ESC-01 | Injected top exactly 0.70, second 0.10 | `abstain`; exact `no_valid_document`, never `low_confidence`; authority no | No |
| `esc01-staff-confirms-intent` | ESC-01 | Staff chose `delivery_time` | `abstain`; exact `no_valid_document`, never `low_confidence`; authority no | No |
| `esc02-out-of-scope-intent` | ESC-02 | Injected `recover_password` 0.94 | `abstain`; exact `out_of_scope_intent`, `no_valid_document`; authority no | No |
| `esc02-password-message` | ESC-02 | Account message | `abstain`; `out_of_scope_intent`, `no_valid_document`; never `human_agent_requested`; authority not checked | Yes |
| `esc02-store-hours-message` | ESC-02 | Store message | `abstain`; `out_of_scope_intent`, `no_valid_document`; never `human_agent_requested`; authority not checked | Yes |
| `esc03a-refund-request-message` | ESC-03 (a) | Refund request | `abstain`; `no_valid_document`; never `human_agent_requested`; authority yes | Yes |
| `esc03a-sensitive-intent-not-first` | ESC-03 (a) | A damaged delivery with a request for the money back: injected `delivery_issue` 0.76, `request_refund` 0.18 | `abstain`; exact `no_valid_document`; authority yes | No |
| `esc03a-sensitive-intent-at-threshold` | ESC-03 (a) | Injected `track_order` 0.85, `cancel_order` exactly 0.10 | `abstain`; exact `no_valid_document`, never `low_confidence`; authority yes | No |
| `esc03a-sensitive-intent-staff-choice` | ESC-03 (a) | Staff chose `request_refund` | `abstain`; exact `no_valid_document`, never `low_confidence`; authority yes | No |
| `esc03a-refund-policy-question` | ESC-03 (a) | Injected `refund_policy` 0.93, no term | `abstain`; exact `no_valid_document`; authority no | No |
| `esc03a-term-suspected-fraud` | ESC-03 (a) | Term `fraud`, injected `track_order` 0.93 | `abstain`; exact `no_valid_document`; authority yes | No |
| `esc03a-term-unauthorized` | ESC-03 (a) | Term `unauthorized`, injected `track_order` 0.93 | `abstain`; exact `no_valid_document`; authority yes | No |
| `esc03a-term-legal-claim` | ESC-03 (a) | Term `legal action`, injected `track_order` 0.93 | `abstain`; exact `no_valid_document`; authority yes | No |
| `esc03a-term-transaction-dispute` | ESC-03 (a) | Term `chargeback`, injected `track_order` 0.93 | `abstain`; exact `no_valid_document`; authority yes | No |
| `esc03a-term-policy-exception` | ESC-03 (a) | Term `make an exception`, injected `track_order` 0.93 | `abstain`; exact `no_valid_document`; authority yes | No |
| `esc03a-term-legal-claim-message` | ESC-03 (a) | Terms `lawyer` and `lawsuit` | `abstain`; `no_valid_document`; never `human_agent_requested`; authority yes | Yes |
| `esc03b-human-agent-message` | ESC-03 (b) | Request for a person | `escalate`; `human_agent_requested`, `no_valid_document`; authority not checked | Yes |
| `esc03b-human-agent` | ESC-03 (b) | Injected `human_agent` 0.95 | `escalate`; exact `human_agent_requested`, `no_valid_document`; authority no | No |
| `esc03b-human-agent-low-confidence` | ESC-03 (b) | Injected `human_agent` 0.55, `customer_service` 0.30 | `escalate`; exact `low_confidence`, `human_agent_requested`, `no_valid_document`; authority no | No |
| `esc03b-human-agent-with-term` | ESC-03 (b) | Injected `human_agent` 0.95, term `lawsuit` | `escalate`; exact `human_agent_requested`, `no_valid_document`; authority yes | No |
| `esc04-no-valid-document` | ESC-04 | Injected `shipping_costs` 0.94 | `abstain`; exact `no_valid_document`; authority no | No |
| `esc04-no-valid-document-message` | ESC-04 | Return question | `abstain`; `no_valid_document`; never `human_agent_requested`; authority not checked | Yes |
| `esc05-intent-model-failure` | ESC-05 | The intent model fails | `500 internal-error` from both operations | No |
| `esc05-retrieval-failure` | ESC-05 | The search fails | `500 internal-error` from both operations | No |
| `esc05-llm-failure-not-reached` | ESC-05 | The LLM fails, injected `track_order` 0.93 | `abstain`; exact `no_valid_document`, never `llm_unavailable`; authority no | No |

Every `200` case expects `llm_called` `false`, and `draft_status` follows the recommendation: `abstained` for `abstain`, `escalation_recommended` for `escalate`.

## Limits of the set

- **The six cases that depend on the model** rest on the uncalibrated softmax of model `v1.0.0` ([`ai-service/README.md`, Known limits](../../../../ai-service/README.md#known-limits)). They were written without a run of that model. If one fails at the first gate run, the gate fails, and the case stays as it is.
- **ESC-01 by a message alone** has no case. The uncalibrated model gives no ground to expect a low probability for any given text, so ESC-01 is checked with injected distributions and with a staff choice.
- **δ alone** cannot be shown: with τ 0.70 and δ 0.10, a top-1 probability of at least 0.70 leaves at most 0.30 to the second intent, so the gap is at least 0.40. `esc01-below-delta` is also below τ.
- **ESC-04 with expired or conflicting versions** has no case, because the release holds no KB document version and this set invents none. The set for the first release that serves a KB version adds them.
- **ESC-03 (a) drafts with supporting information only** cannot be reached without a KB document version.
- **ESC-05 by the time budget** (`budget_exceeded`) has no case: the latency budget of the whole suggestion is deferred ([`ai-service/README.md`, Known limits](../../../../ai-service/README.md#known-limits)).
- **ESC-05 inside `backend`** (`ai_service_unavailable`, `pseudonymization_failed`) is checked by the guardrail tests of `backend`, not here.

## Open questions

- **Injected parts in the gate.** Whether the project lead accepts cases that replace the intent model, the search, or the LLM adapter as mandatory escalation cases. Without them, ESC-01 and ESC-05 have no case. Recommended default: accept them, because TEST-26 asks that routing be correct and ESC-05 cannot be produced through a message.
