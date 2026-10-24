# Glossary

> **Status:** Active · **Owner:** team · **Last reviewed:** 2026-10-24

The canonical meaning of every domain term. Code, contracts, docs, and UI use these terms exactly. Add a term here in the same PR that introduces it.

## Terms

| Term | Meaning | Do not use |
|---|---|---|
| Abstention | The AI declines to draft because evidence is insufficient or the message is unclear. The ticket goes to manual handling with a reason code. | — |
| Analysis | The LLM-free part of the AI pipeline: intent distribution, retrieved documents, and routing recommendation. Served by `/v1/analyses` ([ADR-0005](decisions/0005-intent-independent-retrieval.md)). | — |
| `as_of` | The point in time used to decide which KB document versions are in effect. | — |
| Citation | A link from a draft segment to one KB document version, with the supporting snippet. | reference, source link |
| Component | One of `frontend`, `backend`, or `ai-service` ([ADR-0001](decisions/0001-system-architecture.md)). | — |
| Contract | The versioned API or data agreement between components, stored in `contracts/`. | — |
| Customer | A simulated shopper who uses `/shop`. | user (ambiguous) |
| Design token | A named visual value (color role, spacing step, type size) that every UI element must use instead of a literal ([ADR-0008](decisions/0008-ui-design-system.md)). | — |
| Draft | An AI-proposed reply for the customer, made of segments with citations. Never sent automatically. | answer, response |
| Escalation | Moving a ticket to someone with more authority. The AI can only recommend it; staff decide it. | — |
| Grounding | The property that every factual or policy claim in a draft is supported by a cited source. | — |
| Idempotency key | A client-chosen key sent with a write so that a retry does not repeat its effect. | request ID (tracing is separate) |
| In-scope intent | One of the 12 intents the product drafts replies for ([requirements](product/requirements.md#32-in-scope-intents)). | — |
| Intent | One of the 46 Bitext labels for what the customer wants. | category (a different Bitext field) |
| Intent distribution | Calibrated probabilities over all intents for one message. | — |
| Intent override | An intent chosen by staff that replaces the model's prediction for drafting. | — |
| KB document version | One immutable version of a KB document, with an ID, a version, and an effective period (`effective_from`, `effective_to`). | — |
| Knowledge base (KB) | The approved, versioned set of simulated policy and FAQ documents. | policy database |
| Authority required | A ticket property that becomes true once any suggestion for the ticket carries the reason code `requires_authority` (refund decisions, transaction disputes, policy exceptions; FR-06). It is never cleared, and only a supervisor can send the reply. Defined in the [contracts v1 design](design/contracts-v1.md#authority-rule-fr-06). | — |
| Handling mode | Whether a ticket is handled `assisted` (with AI suggestions) or `manual` (without them), used for the product-value study. Defined in the [contracts v1 design](design/contracts-v1.md#ticket-lifecycle). | — |
| Manual handling | Staff handle a ticket without AI help, because `ai-service` is unavailable or because the ticket's handling mode is `manual`. | fallback mode |
| Message | Text written by a customer or staff within a ticket. | — |
| Order context | Minimal simulated order, shipment, and refund data that `backend` passes to `ai-service`. | — |
| Provenance | Everything needed to reconstruct a suggestion: inputs, model version, KB version, prompt version, and outputs. | — |
| Reason code | An enum value that explains an AI recommendation or a staff decision. Never free text. | — |
| Reply | The message staff send to a customer. Only staff can send a reply. | answer, response |
| Reply proposal | A reply prepared by staff and waiting for a supervisor to send it as is or edited; required when authority is required. Defined in the [contracts v1 design](design/contracts-v1.md#ticket-lifecycle). | — |
| Routing recommendation | The proposal from `ai-service` for a ticket: draft, abstain, or escalate. | — |
| Staff | A customer support employee who uses `/console`. | agent, operator (`agent` is reserved for AI agents and the `human_agent` intent) |
| Staff decision | What staff did with a suggestion: approve, edit, reject, or escalate. | — |
| Staff note | AI-written text for staff only, such as why escalation is recommended or what information is missing. Never sent to the customer. | — |
| Suggestion | Everything the AI produced for a ticket in one run, as recorded by `backend`: an analysis and, when available, a draft or a staff note. A new run supersedes the previous suggestion. | — |
| Supervisor | Staff with authority over refunds, transaction disputes, and policy exceptions (FR-06). Exact permissions are defined in the backend contract. | — |
| Warning | A condition that allows a draft but needs staff attention, identified by a `warning_id` and a reason code. Staff must acknowledge every warning before sending a reply based on the draft. | — |
| `synthetic-dev-only` | Label for development data that does not come from the approved source. Never used as policy or in evaluation reports. | — |
| Ticket | A customer request and everything that happens to it until it is closed. | case, request (reserved for HTTP requests), conversation |
| Trace | The end-to-end record of one operation across components, identified by a trace ID and propagated with the W3C `traceparent` header ([ADR-0007](decisions/0007-observability-stack.md)). | — |

## Acronyms

| Acronym | Meaning |
|---|---|
| ADR | Architecture decision record |
| CI | Continuous integration |
| FR | Functional requirement, as numbered in the [requirements](product/requirements.md#4-functional-requirements) |
| LLM | Large language model |
| ML | Machine learning |
| OTLP | OpenTelemetry Protocol |
| p50, p95 | 50th and 95th percentile (of latency) |
| PR | Pull request |
| RAG | Retrieval-augmented generation |
| WCAG | Web Content Accessibility Guidelines |
