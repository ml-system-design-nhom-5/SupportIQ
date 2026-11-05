# Requirements

> **Status:** Active · **Owner:** team · **Last reviewed:** 2026-11-04

The scope, functional and quality requirements, assumptions, and constraints of SupportIQ. Read it before designing any feature. Reviewers check designs, contracts, and evaluation results against it.

## Sources

| Source | Role |
|---|---|
| Course brief "Topic 1: AI Customer Support Copilot for E-commerce" (Machine Learning in Production, VNU-UET), shared by Groups 2 and 5 | The highest authority. If this file disagrees with the brief, the brief wins and this file is fixed |
| Group 5 specification "SupportIQ: requirements, assumptions, constraints, architecture, and design rationale" (in Vietnamese, submitted on 2026-10-25) | The team's refinement of the brief. It is kept outside the repository because it contains students' personal data |
| This file | The English source of truth inside the repository |

This team is Group 5. This file uses the identifiers of the specification (`FR-`, `NFR-`, `ESC-`, `ASM-`), so both documents can be traced to each other. The specification's constraints are numbered `CST-` here, because `CON-` is the prefix of the [contract rules](../rules/contracts.md).

Where this file clarifies the submitted specification, the clarification is listed in the [appendix](#appendix-clarifications-of-the-submitted-specification), so the next revision of the specification can include it.

Documents written before 2026-10-28 use the brief's numbering, in which FR-08 covers both access control and data protection. In this file, access control is FR-08 and data protection is FR-09. The brief's three assumptions are ASM-01, ASM-02, and ASM-04 here.

## 1. Product

SupportIQ is an AI copilot for customer support staff in e-commerce. It combines:

- **Non-generative ML:** intent classification with a model the team trains.
- **LLM and retrieval:** finds approved policies, FAQ, and simulated business data, and drafts a reply with verifiable citations.
- **Human oversight:** staff check, edit, approve, reject, or escalate every draft. The system never sends a reply and never performs a transaction on its own.

Intended value: shorter handling time, more accurate and consistent information, and less risk from wrong AI output.

### Stakeholders

| Group | Stakeholder | System role | Role in the system |
|---|---|---|---|
| Primary user | Support staff (Tier 1) | `staff` | View the intent, sources, warnings, and draft; send, edit, reject, or escalate |
| Beneficiary | E-commerce customer | `customer` | Submit requests through the demo shop; see only replies that staff sent |
| Other | Support manager (Tier 2) | `manager` | Handle escalated tickets and tickets where authority is required, make business decisions, view reports, approve improvements |
| Other | Administrator | `admin` | Manage internal accounts (staff, managers, admins) and their roles; view the model, KB, and prompt versions in use. Never sees customer accounts or tickets |
| Other | Data and policy owner | None | Provide and approve KB versions |

System roles are defined in [ADR-0012](../decisions/0012-roles-v1.md).

## 2. Scope

### In scope

- Receive and classify requests written in natural language. The model is evaluated on all 46 intents.
- Look up policies, FAQ, and simulated business data, and draft replies with source references.
- Help staff approve, edit, reject, or escalate.
- Record feedback, an audit trail, and data for evaluation and monitoring.
- A demo shop without AI, where simulated customers browse a read-only catalog, see their orders, and submit requests ([ADR-0013](../decisions/0013-shop-demo-with-read-only-catalog.md)).

### Out of scope

- A chatbot that replies to customers without staff.
- Automatic approval of refunds, order changes, or any transaction.
- A complete sales, payment, or delivery system. The demo shop has no cart, checkout, or payment ([ADR-0013](../decisions/0013-shop-demo-with-read-only-catalog.md)).
- Integration with a real e-commerce system.
- Real personal or transaction data.

## 3. Data and AI tasks

### 3.1 Intent classification

- **Task:** single-label intent classification.
- **Dataset:** Bitext Retail E-commerce, shared by both groups.
- **Input:** `instruction`, the customer's message.
- **Target:** `intent`, 46 labels.
- **Output:** the predicted intent with a calibrated confidence and the next most likely intents.
- **Split:** made once, before any experiment, with a fixed seed: a hold-out test set, and a train and validation part on which 10-fold cross-validation runs (NFR-01). Both groups use the same procedure ([open questions](#8-open-questions)).
- **Required:** at least one traditional baseline (for example TF-IDF with logistic regression or SVM) and one ML solution of the team's choice (CST-01).
- Multi-label classification is not required. Multi-intent and out-of-scope messages are evaluated with a separate scenario test set.

Dataset facts from the [dataset card](https://huggingface.co/datasets/bitext/Bitext-retail-ecommerce-llm-chatbot-training-dataset), checked on 2026-10-23:

- 44,884 rows with columns `instruction`, `intent`, `category`, `tags`, `response`.
- 46 intents in 13 categories.
- `tags` holds language-variation codes, including `Z` (errors and typos), `Q` (colloquial), `C` (coordinated: several clauses or tasks), `K` (keyword style), `E` (abbreviations), and `W` (offensive language).

### 3.2 In-scope intents

The product handles 12 intents:

| Business area | Intents |
|---|---|
| Orders | `track_order`, `cancel_order` |
| Delivery | `delivery_time`, `delivery_issue`, `shipping_costs` |
| Returns and refunds | `return_policy`, `return_product`, `refund_policy`, `request_refund`, `refund_status` |
| Payment | `payment_issue` |
| Human support | `human_agent` |

The product drafts replies for the first 11. A `human_agent` request never receives a draft: the AI recommends escalation and staff decide ([ESC-03](#41-escalation-and-fallback-rules)). Intents outside this set receive no detailed draft and go to manual handling (ESC-02).

### 3.3 LLM and knowledge base

The LLM is used to:

- synthesize information from retrieved documents;
- draft a reply that fits the customer's request;
- clarify missing or conflicting information;
- help staff understand why a ticket is escalated.

Data sources:

- **Shared knowledge base:** one set of simulated e-commerce FAQ and policy documents approved by the lecturer, covering delivery, returns, refunds, and order handling.
- **Simulated business data:** order, shipment, and refund status.
- Both groups use the same data version in the joint evaluation (CST-02).
- The `response` column in Bitext is **not** validated business policy (ASM-03).
- English is the language of data, KB, prompts, and UI (CST-06).

## 4. Functional requirements

Priorities use MoSCoW (Must, Should, Could, Won't). The **Brief** column names the requirement of the brief that each one refines. Each group decides how to implement the requirements.

| ID | Requirement | Priority | Brief |
|---|---|---|---|
| FR-01 | **Intent classification.** Receive a request written in natural language and predict its intent (46 labels) with the self-trained non-generative ML model. Show the intent with its calibrated confidence and the top three candidates. Staff can correct the intent, and the correction is recorded as feedback. | Must | FR-01 |
| FR-02 | **Knowledge retrieval and validity checks.** From the intent and the request content, retrieve policies and FAQ (top-k) and simulated business data (order, shipment, and refund status). Check the validity period and version of every document. Detect and flag information that is missing, expired, or conflicting. | Must | FR-02 |
| FR-03 | **Grounded drafts.** Use the LLM to draft a reply from the retrieved information. Every policy claim cites a specific document and version, and every fact about the customer's order cites the order data it comes from. Without enough evidence, the draft states what is missing or proposes a clarifying question, and makes no firm conclusion. | Must | FR-03 |
| FR-04 | **Review interface.** Staff see the request, intent, confidence, citations, warnings, and draft, and can approve, edit, reject, or escalate. Only replies that staff approved are sent. There is no automatic send path. | Must | FR-04 |
| FR-05 | **Abstention, fallback, and escalation.** Trigger fallback or escalation when confidence is below the threshold, the intent is outside the 12 in-scope intents, the request is sensitive, no valid document is found, or the ML, retrieval, or LLM component fails or exceeds its time budget. Each case carries a reason code shown to staff. The rules are in [§4.1](#41-escalation-and-fallback-rules). | Must | FR-05 |
| FR-06 | **Limits on business decisions.** For refunds, transaction disputes, and policy exceptions, the system provides supporting information only: the applicable policy, the status, and the conditions. The decision belongs to a manager. A draft never commits the business to anything. | Must | FR-06 |
| FR-07 | **Recording and traceability.** Record the staff decision (approve, edit, reject, escalate), the predicted and final intent, the confidence, the versions of sources, model, and prompt, the escalation reason, the edits and staff feedback, who decided, and when. | Must | FR-07 |
| FR-08 | **Authentication and authorization.** Sign-in and role-based access for `customer`, `staff`, `manager`, and `admin`. Each role reaches only the functions and data it is allowed. `backend` enforces every check. | Must | FR-08 (access control) |
| FR-09 | **Data protection with external services.** Detect personal data (name, address, phone number, email, order ID) and replace it with pseudonyms before any text is sent to the LLM or another external service, and before it is logged. API keys are managed centrally. Outbound calls go only through an egress allow-list. | Must | FR-08 (data protection) |
| FR-10 | **Reports and monitoring.** Give managers: the share of drafts approved, edited, and rejected; escalations by reason; latency p50 and p95; error rate; and average cost per request. | Should | FR-07; latency and cost |
| FR-11 | **Demo shop and support channel.** A simple e-commerce website without AI, on simulated data, where customers submit support requests. Replies appear only after staff send them. Its scope is fixed in [ADR-0013](../decisions/0013-shop-demo-with-read-only-catalog.md). | Should | Supports the test scenarios |

The brief's "basic error handling" (its FR-08) is covered by FR-05 and NFR-07.

### 4.1 Escalation and fallback rules

These rules detail FR-05. The **Reason category** column holds the labels of the specification. The contract reason codes refine them; the mapping is in the [contracts v1 design](../design/contracts-v1.md#reason-codes).

| ID | Trigger | System behavior | Reason category |
|---|---|---|---|
| ESC-01 | The top-1 probability is below τ, or the gap between the top-1 and top-2 probabilities is below δ | Flag low confidence and create no draft. Staff confirm or correct the intent, and only then is a draft created | `LOW_CONFIDENCE` |
| ESC-02 | The intent is outside the 12 in-scope intents | No detailed draft; manual handling | `OUT_OF_SCOPE` |
| ESC-03 | A sensitive request: (a) a refund decision or exception, a transaction dispute, a policy exception, a legal claim, or suspected fraud; (b) the intent `human_agent` | (a) Retrieval still runs. Any draft contains supporting information only. Authority is required, so a manager decides and sends the reply. (b) No draft. The AI recommends escalation, and staff decide whether to escalate to a manager. A `human_agent` case counts as handled correctly (NFR-05) when escalation is recommended with its reason | `SENSITIVE` |
| ESC-04 | No valid document; documents are expired or conflicting | Abstain, or draft a reply that states the missing information. Show a warning | `NO_EVIDENCE`, `STALE`, `CONFLICT` |
| ESC-05 | The ML, retrieval, or LLM component fails, or the LLM time budget (NFR-07) runs out | Manual handling. The console keeps ticket viewing and manual replies working. The suggestion runs again when staff open the ticket or ask for a retry | `COMPONENT_FAILURE` |

τ (the minimum top-1 probability) and δ (the minimum gap between the top two probabilities) are tuned on validation data, never on test data ([DATA-25](../rules/data-and-ml.md#leakage)). They are recorded in the release manifest with the model version ([DATA-56](../rules/data-and-ml.md#models-and-artifacts)). Refund decisions and transaction disputes are detected from the intent distribution: a sensitive intent, such as `request_refund`, with a significant probability counts even when it is not first ([ADR-0005](../decisions/0005-intent-independent-retrieval.md), statement 5). A message that only asks about a refund policy or a refund status needs no authority. No Bitext intent covers legal claims or suspected fraud, so they are detected with a versioned sensitive-term list. Both lists are in the routing configuration ([DATA-58](../rules/data-and-ml.md#models-and-artifacts)). Policy exceptions have no signal of their own: they are covered by the sensitive intents and by staff judgment, and staff can always route a ticket to a manager. Each signal can only add the authority requirement, never remove it. The `ai-service` pipeline design decides from measurements whether the LLM adds a third signal.

## 5. Quality requirements

These are evaluation targets for the prototype under the shared test conditions, not commitments for a production system. Targets marked **(team)** were added by the team: they are not in the brief and may be adjusted after the first measurement. All other targets come from the brief.

| ID | Attribute | Target | Verification | Brief dimension |
|---|---|---|---|---|
| NFR-01 | ML quality | Macro-F1 ≥ 0.85 over 46 intents with 10-fold cross-validation, above the TF-IDF with logistic regression or SVM baseline. Report per-class F1 and the confusion matrix | Hold-out test set and seed fixed before any experiment; 10-fold cross-validation on the train and validation part; the same split procedure as Group 2 | ML quality |
| NFR-02 | ML robustness | Macro-F1 on noisy data (typos, unusual phrasing) at most 10 percentage points below clean data **(team)**. At least 90% of ambiguous, multi-intent, or out-of-scope messages are flagged as low confidence or routed away from drafting **(team)** | The shared scenario set; a noisy set generated from the hold-out test set by controlled transformations | ML robustness |
| NFR-03 | Retrieval quality | Recall@3 ≥ 0.80 on questions that have a supporting document; every document used is in effect. 100% of the expired, missing, or conflicting documents in the test set are detected and flagged **(team)** | A question set labeled with the correct documents; planted cases with expired and conflicting documents | Retrieval quality |
| NFR-04 | LLM grounding | At least 90% of factual and policy statements in drafts are supported by retrieved sources. 100% of drafts have verifiable citations **(team)**. No firm conclusion without a supporting document | Manual grading of the test set with a shared rubric; at least two graders per sample **(team)** | LLM quality |
| NFR-05 | Safety and human oversight | 100% of replies pass through staff approval. No reply sent automatically. No automatic transaction. 100% of mandatory escalation cases in the test set are handled correctly, with the reason recorded | End-to-end flow tests; comparison of the audit log with the list of mandatory escalation cases | Safety and oversight |
| NFR-06 | Security and privacy | 100% of role-based access tests pass, with checks in `backend`. 100% of payloads sent to the external LLM are pseudonymized: no raw personal data. Outbound calls go only through the egress allow-list. Attack success rate at most 5% on the prompt-injection and unauthorized-access scenarios **(team)**; leakage of secrets or personal data is 0% | Role-based access test suite; personal-data scans of payloads and logs; attack scenario suite | Brief FR-08 |
| NFR-07 | Reliability and availability | 100% of ML uncertainty, missing-document, and LLM or API failure cases are handled safely: abstention or manual handling, and the UI never hangs. The LLM time budget is at most 10 s per draft, including at most 2 retries **(team)**. When the LLM or retrieval fails, sign-in, ticket viewing, and manual replies keep working | Fault injection: stop the ML, LLM, or retrieval component; simulate timeouts and `5xx` errors | System reliability |
| NFR-08 | Performance and capacity | End-to-end latency p50 ≤ 4 s **(team)** and p95 ≤ 12 s. At least 5 concurrent sessions **(team)** with an error rate of at most 1% **(team)**, and p95 at that load at most twice the single-user p95 **(team)**. The whole demo stack uses at most about 5 GB of RAM on an 8 GB machine **(team)** | Load-test script under the shared test conditions; RAM measured with `docker stats` | Latency and cost |
| NFR-09 | Traceability and auditability | 100% of decisions are recorded with the trace ID, intent and confidence, source, model, and prompt versions, escalation reason, reviewer, and time. The audit log is insert-only. Any suggestion can be reconstructed from the audit log and suggestion records | Reconstruction of randomly sampled suggestions; `UPDATE` and `DELETE` on the audit log are rejected | Traceability (priority order) |
| NFR-10 | Cost | Measure and report the average cost per request (LLM tokens and infrastructure). Total AWS deployment and operation cost over the project is at most 200 USD in credits | Token counts per suggestion in `backend` records; AWS budget alerts at 50% and 80% | Latency and cost |
| NFR-11 | Usability and product value | The console shows the intent with confidence, citations, warnings, and escalation reasons. Staff edit or reject a draft in at most 3 actions **(team)**, not counting the acknowledgements that guardrails require. Handling time is at least 20% shorter than the manual process **(team)**, measured on at least 30 requests **(team)**. Report the approve, edit, and reject rates | Comparison of both processes on the same requests by the same staff, with the order counterbalanced | Product value |

End-to-end latency is measured from ticket creation until the draft part of the suggestion is no longer pending ([contracts v1 design](../design/contracts-v1.md#suggestion-lifecycle)).

**Priority:** correctness and safety → traceability and human control → reliability and latency → cost.

**Guardrail:** no metric may be improved by violating a mandatory guardrail. For example, do not skip staff approval or the validity check of documents to cut latency, do not skip pseudonymization, and do not drop citations to save tokens.

## 6. Assumptions and constraints

### Assumptions

| ID | Assumption | Check, or consequence if it is wrong |
|---|---|---|
| ASM-01 | The Bitext Retail E-commerce dataset has enough data and coverage to classify 46 intents | Synthetic phrasing may differ from real customers. Checked with the noisy set and the scenario set (NFR-02) |
| ASM-02 | The KB and the simulated business data approved by the lecturer have clear sources, versions, and validity periods, and both groups use the same version | Without validity metadata, NFR-03 cannot be verified. The missing metadata is requested from the policy owner before evaluation; the team never invents it |
| ASM-03 | The `response` column in Bitext is not validated business policy | Only `instruction` and `intent` are used to train the classifier. Policy comes only from the KB |
| ASM-04 | Staff have the expertise to review, edit, and decide the cases that need human review, and they actually read drafts | The risk of over-trusting the AI is reduced by showing sources, warnings, and confidence (NFR-11) |
| ASM-05 | The external LLM service is available during development and testing, with enough rate limit and budget for the tests | If it is not, the system falls back to manual handling (NFR-07), and LLM measurements are repeated when the service returns |
| ASM-06 | One 8 GB machine (an EC2 instance or a personal machine) runs the whole demo stack with Docker Compose under the shared test conditions | Checked by RAM measurement and the load test (NFR-08). If the stack does not fit, `ai-service` runs one replica ([ADR-0011](../decisions/0011-deployment-and-runtime-topology.md)) |

### Constraints

| ID | Constraint | Source |
|---|---|---|
| CST-01 | A self-trained non-generative ML model (at least one traditional baseline and one model of the team's choice) and an LLM are both required | Brief |
| CST-02 | Use the dataset, KB, scenario set, and evaluation procedure shared with the other group | Brief |
| CST-03 | Simulated data only. No real personal or transaction data. Production integration is not required | Brief |
| CST-04 | The product must be deployable, runnable, and able to record test results | Brief |
| CST-05 | The AWS budget for deployment and operation is 200 USD in credits | Team |
| CST-06 | English is the language of the data, KB, prompts, and UI, because the Bitext dataset and the KB are in English | Team |
| CST-07 | The demo stack runs on one machine with 8 GB of RAM | Team |

## 7. Risks and required controls

| Failure mode | Consequence | Required control | Requirements |
|---|---|---|---|
| ML predicts the wrong intent | Wrong documents are retrieved and the reply does not fit | Calibrated confidence with τ and δ (ESC-01); the top three candidates are shown; staff correct the intent | FR-01, NFR-01, NFR-02 |
| Retrieval returns outdated or irrelevant documents | The LLM writes a plausible reply that contradicts policy | Validity and version checks at `as_of`; abstain without evidence (ESC-04) | FR-02, NFR-03 |
| The LLM adds information not in the sources | Staff give customers wrong information | Grounded prompts, mandatory citations, citation and grounding checks, human review | FR-03, NFR-04, NFR-05 |
| Staff over-trust the AI | AI errors pass review | The console shows sources, warnings, and confidence; staff edit or reject; feedback is collected | FR-04, NFR-11 |
| The LLM or an API is unavailable | Support work is interrupted | Time budget, bounded retries, fallback to manual handling (ESC-05) | NFR-07 |
| Data leaks through APIs or logs | Security and privacy risk | Simulated data, pseudonymization in `backend`, egress allow-list, managed secrets, sanitized logs | FR-09, NFR-06 |

## 8. Open questions

- Group 2 has not yet confirmed the split procedure: a hold-out test set plus 10-fold cross-validation on the train and validation part (NFR-01, CST-02).
- Knowledge base: Groups 2 and 5 agreed on one shared policy file. Its origin and the lecturer's approval are not yet confirmed, and its documents have no effective dates, policy keys, sources, or owners. The file is not yet in the repository. When it is added, its location, version, and checksums are recorded in `contracts/kb-contract.md`.
- Simulated business data: Groups 2 and 5 agreed on one shared order file. Its origin and approval are not yet confirmed, and it does not yet match the commerce model ([contracts v1 design](../design/contracts-v1.md#open-questions)).
- English versions of the shared files: who translates them, and whether both groups use one translation (CST-02, CST-06).
- The shared scenario test set: who provides it, and in what format.
- Deadlines and reporting milestones.

## Appendix: clarifications of the submitted specification

Each row is a point where this file deliberately differs from the specification submitted on 2026-10-25. The next revision of the specification should include these clarifications.

| # | Specification | Clarification in this file | Reason |
|---|---|---|---|
| 1 | ESC-05 and NFR-07: LLM timeout of 10 s with up to 2 retries | The 10 s budget covers the whole LLM step, retries included. A retry happens only for a retryable failure and only while budget remains | Three attempts of 10 s each (30 s) would break p95 ≤ 12 s ([ERR-10, ERR-13](../rules/errors-and-reliability.md#timeouts-and-latency-budget)) |
| 2 | ESC-01 says staff choose the intent before drafting; Figure 2 sends low confidence to manual handling | No draft until staff confirm or correct the intent. The top-1/top-2 gap is named δ | The table and the figure disagree |
| 3 | Figure 2 checks for sensitive requests before retrieval | Retrieval still runs for sensitive requests, and any draft holds supporting information only | Without retrieval, the manager gets no supporting information, which FR-06 requires |
| 4 | ESC-03 sends `human_agent` to the manager | The AI recommends escalation; staff decide. Authority is not required. For NFR-05, a recommended escalation with its reason counts as correct handling | The staff member is already the human the customer asked for, and FR-06 does not cover this case. The team chose this on 2026-10-28 |
| 5 | ESC-03 lists legal claims and fraud without a detection method | Detected with a versioned sensitive-term list; handled as requiring authority | No Bitext intent covers them |
| 6 | Figure 1 places the PII scanner only before drafting | Pseudonymization happens in `backend` before any text leaves it ([ADR-0010](../decisions/0010-pseudonymization-and-egress-control.md)) | Sections 5.2 and 5.3 of the specification place it at the entry of the pipeline |
| 7 | FR-09 "tokenization" and "Token Vault" | Named pseudonymization and pseudonym map | "Token" already means LLM tokens and session tokens in this project |
| 8 | NFR-11: at most 3 actions | Acknowledgements required by guardrails are not counted | Safety ranks above speed in the quality priority |
| 9 | NFR-09: reconstruct a request from logs | Reconstructed from the audit log and suggestion records | Telemetry is disposable and never the source of evaluation data ([LOG-33](../rules/logging-and-observability.md#alerts-and-retention)) |
| 10 | NFR-06: access tests with a warm and a cold cache | No permission cache exists in v1; access tests run against database-backed sessions | [ADR-0011](../decisions/0011-deployment-and-runtime-topology.md) defers caching |
| 11 | Section 1.2: the administrator manages configuration and model and KB versions | The administrator views versions. Versions change only through the release process | Changing a version from a screen would bypass the offline evaluation gate ([ADR-0012](../decisions/0012-roles-v1.md)) |
| 12 | FR-11: demo payment and delivery | A read-only catalog; no cart, checkout, or payment | No operation creates or changes orders, which keeps transactions out of scope ([ADR-0013](../decisions/0013-shop-demo-with-read-only-catalog.md)) |
| 13 | Sections 5 and 6: API gateway, Redis, WebSocket, separate AI services, message queue | Mapped onto three components, with each deviation recorded | [ADR-0011](../decisions/0011-deployment-and-runtime-topology.md) |
| 14 | ASM-02: the team adds missing KB metadata | The missing metadata is requested from the policy owner | Values missing from the source are never invented ([DATA-13](../rules/data-and-ml.md#validation-at-every-boundary)) |
| 15 | NFR-08: "end-to-end latency" is not defined | From ticket creation until the draft part of the suggestion is no longer pending | A target needs a measurable definition |
| 16 | Constraints CON-01 to CON-07 | Numbered CST-01 to CST-07 | `CON-` is the prefix of the contract rules |
| 17 | NFR-09: decisions recorded with a "request ID" | Recorded with the trace ID, plus the ticket and suggestion IDs | The trace ID already identifies one operation across components ([ADR-0007](../decisions/0007-observability-stack.md)), and "request ID" is not a term of this project |
| 18 | FR-09: detect names and addresses | `backend` detects known values, patterns, and unknown names and addresses. No detector is complete, so the NFR-06 suite includes third persons, and every miss counts against the target | A target of 0% is measured, not guaranteed ([ADR-0010](../decisions/0010-pseudonymization-and-egress-control.md#detection)) |
| 19 | NFR-10: token counts per request in the logs | Token counts per suggestion in `backend` records | Telemetry is disposable and never the source of evaluation data ([LOG-33](../rules/logging-and-observability.md#alerts-and-retention)) |
| 20 | FR-06 says "refunds"; ESC-03 says "refund exception" | A customer who asks for a refund requires authority; a message that only asks for information does not | The two texts differ, and the system can detect a request but not an exception |
| 21 | ESC-05 does not say what happens after a failure ends | The suggestion runs again when staff open the ticket or ask for a retry | A ticket should not stay without AI help, or without an authority flag, after `ai-service` recovers |
| 22 | FR-03 and NFR-04: every claim cites a specific document and version | Policy claims cite a KB document version. Facts about the customer's order cite a field of the order context, and such a fact counts as supported for NFR-04 when its citation is valid. Order data is never evidence for a policy or for routing | An order fact is not in the KB, so the original wording would keep a draft from stating it ([ADR-0014](../decisions/0014-citations-to-order-context.md)) |
