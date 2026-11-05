# Glossary

> **Status:** Active · **Owner:** team · **Last reviewed:** 2026-11-05

The canonical meaning of every domain term. Code, contracts, docs, and UI use these terms exactly. Add a term here in the same PR that introduces it.

## Terms

| Term | Meaning | Do not use |
|---|---|---|
| Abstention | The AI declines to draft because evidence is insufficient or the message is unclear. The ticket goes to manual handling with a reason code. | — |
| Admin | The role that manages internal accounts (`staff`, `manager`, `admin`) and views the versions in use. An admin never sees customer accounts, tickets, messages, drafts, orders, or reports ([ADR-0012](decisions/0012-roles-v1.md)). | administrator (in identifiers), superuser |
| Analysis | The LLM-free part of the AI pipeline: intent distribution, retrieved documents, and routing recommendation. Served by `/v1/analyses` ([ADR-0005](decisions/0005-intent-independent-retrieval.md)). | — |
| `as_of` | The point in time used to decide which KB document versions are in effect. | — |
| Audit log | The insert-only record in `backend` of every pseudonymization outcome, suggestion outcome, staff decision, reply, proposal, escalation, and admin change, with who, what, and when. The source for reports and for reconstructing a suggestion (NFR-09). | audit store, logs (telemetry is separate) |
| Authority flag | The field `is_authority_required`, which holds the ticket property Authority required. | — |
| Authority required | A ticket property that becomes true once any suggestion for the ticket carries the reason code `requires_authority` (refund decisions, transaction disputes, policy exceptions, legal claims, suspected fraud; FR-06, ESC-03). It is never cleared, and only a manager can send the reply. Defined in the [contracts v1 design](design/contracts-v1.md#authority-rule-fr-06). | — |
| Citation | A link from a draft segment to its source: one KB document version with the supporting snippet, or one field of the order context, called an order citation ([ADR-0014](decisions/0014-citations-to-order-context.md)). | reference, source link |
| Component | One of `frontend`, `backend`, or `ai-service` ([ADR-0001](decisions/0001-system-architecture.md)). | — |
| Contract | The versioned API or data agreement between components, stored in `contracts/`. | — |
| Customer | A simulated shopper who uses `/shop`. | user (ambiguous) |
| Design token | A named visual value (color role, spacing step, type size) that every UI element must use instead of a literal ([ADR-0008](decisions/0008-ui-design-system.md)). | — |
| Draft | An AI-proposed reply for the customer, made of segments with citations. Never sent automatically. | answer, response |
| Egress proxy | The forward proxy that is the only route from `ai-service` to the internet. It allows only the LLM provider hosts on its allow-list and tunnels TLS, so it never sees request bodies or API keys ([ADR-0010](decisions/0010-pseudonymization-and-egress-control.md#egress-control)). | — |
| Escalation | Moving a ticket to a manager. The AI can only recommend it; staff decide it. | — |
| Grounding | The property that every factual or policy claim in a draft is supported by a cited source. | — |
| Handling mode | Whether a ticket is handled `assisted` (with AI suggestions) or `manual` (without them), used for the product-value study. Defined in the [contracts v1 design](design/contracts-v1.md#ticket-lifecycle). | — |
| Idempotency key | A client-chosen key sent with a write so that a retry does not repeat its effect. | request ID (tracing is separate) |
| In-scope intent | One of the 12 intents the product handles ([requirements](product/requirements.md#32-in-scope-intents)). | — |
| Intent | One of the 46 Bitext labels for what the customer wants. | category (a different Bitext field) |
| Intent distribution | Calibrated probabilities over all intents for one message. | — |
| Intent override | An intent chosen by staff that replaces the model's prediction for drafting. Choosing the predicted intent itself confirms it (ESC-01). | — |
| KB document version | One immutable version of a KB document, with an ID, a version, and an effective period (`effective_from`, `effective_to`). | — |
| Knowledge base (KB) | The approved, versioned set of simulated policy and FAQ documents. | policy database, knowledge store |
| Manager | The role of support managers (Tier 2): they handle escalated tickets and tickets where authority is required, send any reply, and view reports ([ADR-0012](decisions/0012-roles-v1.md)). | supervisor |
| Manual handling | Staff handle a ticket without AI help, because the AI could not run (`ai-service` unavailable, pseudonymization failed) or because the ticket's handling mode is `manual`. | fallback mode |
| Mask | A placeholder without a number, such as `[EMAIL]`, that `ai-service` writes over a personal-data pattern before an LLM call. It cannot be restored ([ADR-0010](decisions/0010-pseudonymization-and-egress-control.md)). | redaction (reserved for removing data from telemetry) |
| Message | Text written by a customer or staff within a ticket. | — |
| Offline evaluation gate | The check that a candidate release manifest meets the quality targets on the frozen test and scenario sets before it is published. If it fails, the previous release stays ([DATA-57](rules/data-and-ml.md#models-and-artifacts)). | — |
| Order context | Minimal simulated order, shipment, and refund data that `backend` passes to `ai-service`. It contains no identifiers. | — |
| Placeholder | Text that stands in for a personal-data value: a pseudonym or a mask. Every placeholder matches one regular expression defined in [ADR-0010](decisions/0010-pseudonymization-and-egress-control.md#placeholder-syntax). The word keeps its ordinary meaning only for dummy values in settings files such as `.env.example`; anywhere else, use it only in this sense. | token |
| Product | A simulated item in the read-only shop catalog ([ADR-0013](decisions/0013-shop-demo-with-read-only-catalog.md)). | item |
| Provenance | Everything needed to reconstruct a suggestion: inputs, release and asset versions, and outputs. | — |
| Pseudonym | A numbered placeholder, such as `[ORDER_ID_1]`, that `backend` writes over a personal-data value. Only `backend` can restore it ([ADR-0010](decisions/0010-pseudonymization-and-egress-control.md)). | token |
| Pseudonym map | The per-ticket mapping from each pseudonym to its original value, stored only in `backend` and read only by its pseudonymization module. | token vault |
| Pseudonymization | Replacing personal data in a customer message with pseudonyms before the text leaves `backend` (FR-09). It is reversible by `backend` and is not anonymization: pseudonymized text stays Confidential. | tokenization, anonymization, masking |
| Reason code | An enum value that explains an AI recommendation or a staff decision. Never free text. | — |
| Release manifest | The versioned file that names every asset version `ai-service` serves together: model artifact, KB, document-to-intent mapping, prompts, routing configuration, and retrieval index. Identified by its `release_id` ([DATA-56](rules/data-and-ml.md#models-and-artifacts)). | model registry |
| Reply | The message staff send to a customer. Only staff and managers can send a reply. | answer, response |
| Reply proposal | A reply prepared by staff and waiting for a manager to send it as is or edited; required when authority is required. Defined in the [contracts v1 design](design/contracts-v1.md#ticket-lifecycle). | — |
| Report | The figures that managers see for a period (FR-10), computed by `backend` from its own records, never from telemetry. Defined in the [contracts v1 design](design/contracts-v1.md#reports-fr-10). | dashboard (dashboards are telemetry views for developers) |
| Routing configuration | The versioned thresholds and lists that turn the intent distribution and evidence into a routing recommendation: τ, δ, the rerank weight λ, the list of sensitive intents, and the sensitive-term list. Part of the release manifest. | routing table (older wording) |
| Routing recommendation | The proposal from `ai-service` for a ticket: draft, abstain, or escalate. | — |
| Sensitive intent | An intent, such as `request_refund`, that sets the authority requirement when it has a significant probability, even if it is not first ([ADR-0005](decisions/0005-intent-independent-retrieval.md), statement 5). Listed in the routing configuration. | — |
| Staff | Support employees who use `/console`. As a role, `staff` means Tier 1 support staff; managers are staff with more authority. | agent, operator (`agent` is reserved for AI agents and the `human_agent` intent) |
| Staff decision | What staff or a manager did with a suggestion: approve, edit, reject, or escalate. | — |
| Staff note | AI-written text for staff only, such as why escalation is recommended or what information is missing. Never sent to the customer. | — |
| Suggestion | Everything the AI produced for a ticket in one run, as recorded by `backend`: an analysis and, when available, a draft or a staff note. A new run supersedes the previous suggestion. | — |
| Suggestion job | The queued unit of work in `backend` that runs one suggestion, claimed by one worker at a time under a lease ([ADR-0011](decisions/0011-deployment-and-runtime-topology.md#suggestion-job-queue)). | task |
| Warning | A condition that allows a draft but needs staff attention, identified by a `warning_id` and a reason code. Staff must acknowledge every warning before sending a reply based on the draft. | — |
| `synthetic-dev-only` | Label for development data that does not come from the approved source. Never used as policy or in evaluation reports. | — |
| Ticket | A customer request and everything that happens to it until it is closed. | case, request (reserved for HTTP requests), conversation |
| Trace | The end-to-end record of one operation across components, identified by a trace ID and propagated with the W3C `traceparent` header ([ADR-0007](decisions/0007-observability-stack.md)). | — |

## Acronyms

| Acronym | Meaning |
|---|---|
| ADR | Architecture decision record |
| AWS | Amazon Web Services |
| CI | Continuous integration |
| FR | Functional requirement, as numbered in the [requirements](product/requirements.md#4-functional-requirements) |
| JWT | JSON Web Token |
| LLM | Large language model |
| ML | Machine learning |
| MoSCoW | The priority scale Must, Should, Could, Won't |
| NFR | Non-functional (quality) requirement, as numbered in the [requirements](product/requirements.md#5-quality-requirements) |
| OTLP | OpenTelemetry Protocol |
| p50, p95 | 50th and 95th percentile (of latency) |
| PII | Personally identifiable information: data that identifies a person, such as a name, email, phone number, address, or order ID |
| PR | Pull request |
| RAG | Retrieval-augmented generation |
| RBAC | Role-based access control |
| SQL | Structured Query Language |
| TLS | Transport Layer Security |
| WAF | Web application firewall |
| WCAG | Web Content Accessibility Guidelines |
