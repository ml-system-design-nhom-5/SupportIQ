# Requirements

> **Status:** Active · **Owner:** team · **Last reviewed:** 2026-10-23

The scope, functional requirements, and quality targets for SupportIQ. Source: the course brief "Topic 1: AI Customer Support Copilot for E-commerce" (Machine Learning in Production, VNU-UET), shared by Groups 2 and 5. This file is the English source of truth inside the repository. If it disagrees with the brief, the brief wins and this file is fixed.

## 1. Product

SupportIQ is an AI copilot for customer support staff in e-commerce. It combines:

- **Non-generative ML:** intent classification of customer messages.
- **LLM and retrieval:** finds relevant information and proposes grounded replies.
- **Human oversight:** staff check, edit, or reject AI output before it is used.

Intended value: shorter handling time, more accurate and consistent information, and less risk from wrong AI output.

### Stakeholders

| Role | Who |
|---|---|
| Primary user | Customer support staff |
| Beneficiary | E-commerce customers |
| Other | Support managers, administrators, and the unit that owns data and policies |

## 2. Scope

### In scope

- Receive and classify requests written in natural language.
- Look up policies, FAQ, and simulated business data.
- Propose replies with source references.
- Help staff approve, edit, reject, or escalate.
- Record feedback and data for evaluation and monitoring.

### Out of scope

- A chatbot that replies to customers without staff.
- Automatic approval of refunds, order changes, or any transaction.
- A complete sales, payment, or delivery system. The minimal shop demo in [ADR-0002](../decisions/0002-shop-demo-scope.md) is not a sales system.
- Required integration with a real e-commerce system.
- Real personal or transaction data.

## 3. Data and AI tasks

### 3.1 Intent classification

- **Task:** single-label intent classification.
- **Dataset:** Bitext Retail E-commerce, shared by both groups.
- **Input:** `instruction`, the customer's message.
- **Target:** `intent`, 46 labels.
- **Output:** the predicted intent and information that helps judge its reliability.
- The dataset is split into train, validation, and test sets by one procedure, fixed before any experiment.
- **Required:** each group trains and evaluates at least one traditional baseline (for example TF-IDF with logistic regression or SVM) and one ML solution of its own choice.
- Multi-label classification is not required. Multi-intent and out-of-scope messages are evaluated with a separate scenario test set.
- The model is evaluated on all 46 intents.

Dataset facts from the [dataset card](https://huggingface.co/datasets/bitext/Bitext-retail-ecommerce-llm-chatbot-training-dataset), checked on 2026-10-23:

- 44,884 rows with columns `instruction`, `intent`, `category`, `tags`, `response`.
- 46 intents in 13 categories.
- `tags` holds language-variation codes, including `Z` (errors and typos), `Q` (colloquial), `C` (coordinated: several clauses or tasks), `K` (keyword style), `E` (abbreviations), and `W` (offensive language).

### 3.2 In-scope intents

The product drafts replies for 12 intents:

| Business area | Intents |
|---|---|
| Orders | `track_order`, `cancel_order` |
| Delivery | `delivery_time`, `delivery_issue`, `shipping_costs` |
| Returns and refunds | `return_policy`, `return_product`, `refund_policy`, `request_refund`, `refund_status` |
| Payment | `payment_issue` |
| Human support | `human_agent` |

Intents outside this set do not need detailed replies, but the system MUST route them to a suitable fallback or escalation.

### 3.3 LLM and knowledge base

The LLM is used to:

- synthesize information from retrieved documents;
- draft a reply that fits the customer's request;
- clarify missing or conflicting information;
- help staff understand why a ticket is escalated.

Data sources:

- **Shared knowledge base:** one set of simulated e-commerce FAQ and policy documents approved by the lecturer, covering delivery, returns, refunds, and order handling.
- **Simulated business data** may provide order, delivery, and refund status.
- Both groups use the same data version in the joint evaluation.
- The `response` column in Bitext is **not** validated business policy.

## 4. Functional requirements

| ID | Requirement |
|---|---|
| FR-01 | Receive a customer request and predict its intent with the self-trained ML model. Show the predicted intent and suitable reliability information to staff. |
| FR-02 | Based on the intent and the request content, retrieve relevant documents, policies, or business data. Detect information that is missing, no longer valid, or conflicting. |
| FR-03 | Use an LLM to draft a reply from the retrieved information, with verifiable source references. Do not state firm conclusions without evidence. |
| FR-04 | Provide an interface for staff to view, edit, approve, or reject drafts. The system MUST NOT send replies to customers automatically. |
| FR-05 | Support abstention, fallback, and escalation when the AI is not reliable enough, information is missing, the request is sensitive, or a component fails. Record the reason. |
| FR-06 | For refunds, transaction disputes, and policy exceptions, provide supporting information only. The business decision belongs to authorized staff. |
| FR-07 | Record staff decisions (approve, edit, reject, escalate), the versions of referenced sources, and feedback for testing, monitoring, and improvement. |
| FR-08 | Provide basic error handling, suitable role-based access, and data protection when using LLMs or external services. |

Each group decides how to implement these requirements.

## 5. Quality requirements

These are shared evaluation targets for the prototype, not performance commitments for a production system.

| Dimension | Target |
|---|---|
| ML quality | Macro-F1 ≥ 0.85 (10-fold cross-validation). Report per-class F1, the confusion matrix, and a comparison with the baseline. |
| ML robustness | Separate evaluation on typos, unusual phrasing, ambiguous questions, and out-of-scope messages. |
| Retrieval quality | Retrieve relevant documents that are still valid. Recall@3 ≥ 0.80 on questions that have a supporting document. |
| LLM quality | At least 90% of factual and policy statements in drafts are supported by retrieved sources, on a manually graded test set. |
| Safety and oversight | 100% of replies go through staff approval. No automatic transactions. Mandatory escalation cases in the test set are handled correctly. |
| System reliability | Handle ML uncertainty, missing documents, and LLM or API failures without producing firm answers that lack evidence. |
| Latency and cost | Measure and report end-to-end p50 and p95 latency, error rate, and average cost per request. Target: p95 ≤ 12 s under the shared test conditions. |
| Product value | Compare handling time for the same set of requests with and without SupportIQ. Report the share of drafts accepted, edited, and rejected. |

**Priority:** correctness and safety → traceability and human control → reliability and latency → cost.

**Guardrail:** no metric may be improved by violating a mandatory guardrail. For example, do not skip staff approval to cut latency, and do not drop citations to save tokens.

## 6. Assumptions and constraints

### Assumptions

- **ASM-01:** The dataset has enough data for intent classification. Differences between the synthetic data and real situations must be checked.
- **ASM-02:** The KB and simulated business data carry reliable source, version, and validity information.
- **ASM-03:** Support staff are able to review and decide the cases that need human review.

### Constraints

- A self-trained non-generative ML model and an LLM are both required.
- Use the shared dataset, scenario set, and evaluation procedure.
- Prefer simulated data. Production integration is not required.
- The product must be deployable, runnable, and able to record test results.

## 7. Risks and required controls

| Failure mode | Consequence | Required control |
|---|---|---|
| ML predicts the wrong intent | Wrong documents are retrieved and the reply does not fit | Evaluation, uncertainty handling, staff can correct the intent |
| Retrieval returns outdated or irrelevant documents | The LLM writes a plausible reply that contradicts policy | Check sources, versions, and validity; abstain without evidence |
| The LLM adds information not in the sources | Staff give customers wrong information | Grounding, citations, output checks, human review |
| Staff over-trust the AI | AI errors pass review | UI shows sources; staff can edit and reject; feedback |
| LLM or API unavailable | Support work is interrupted | Timeout and error handling; fallback to the manual process |
| Data leaks through APIs or logs | Security and privacy risk | Simulated data, data minimization, protected API keys and logs |

## 8. Open questions

- Which group the team is: 2 or 5.
- Knowledge base: the approved KB files are not yet in the repository. When they are added, their location, version, and checksums are recorded in `contracts/kb-contract.md`.
- Simulated business data and the shared scenario test set: who provides them, and in what format.
- How 10-fold cross-validation combines with the fixed train/validation/test split. Both groups must use the same procedure.
- Deadlines and reporting milestones.
