# SupportIQ — Current System Limitations & Operational Boundaries

> **Document Version:** 1.1.0  
> **Target Audience:** Engineering Team, System Architects, Quality Assurance, and Academic Evaluators  
> **Scope:** Runtime constraints, architectural boundaries, edge cases, and post-deployment roadmap items  
> **Last Updated:** 2026-11-12  

---

## 1. Executive Summary

SupportIQ is a prototype AI copilot designed to assist e-commerce customer support staff. The system operates strictly under human-in-the-loop oversight: customer service representatives review, edit, approve, reject, or escalate every proposed response. The system never executes automatic replies and never performs automated financial or order modifications.

This document catalogs current operational boundaries, runtime constraints, and known limitations across architecture, machine learning, retrieval, privacy, infrastructure, and empirical validation. Historical measurements (such as test runs on specific sample sets) represent observed local observations rather than universal production-grade guarantees.

---

## 2. Storage Engine & Immutability Invariants (PostgreSQL Application vs. Demo/Eval SQLite)

### 2.1 Native PostgreSQL Application Runtime
The primary native application (`apps/backend`) uses **PostgreSQL** with dedicated database roles (`supportiq_owner` and `supportiq_app`), explicit schema migrations, and relational schema constraints.

* **Audit Log Immutability & Sticky Authority:** Enforced through database-level constraints and transactional application service rules (`apps/backend/tickets/service.py`). Audit log entries and customer messages reject `UPDATE` and `DELETE` operations, and tickets with `is_authority_required = True` remain locked to manager-only replies even across intent corrections.
* **Driver & Environment Boundaries:** On Windows systems governed by Windows Application Control policies (WDAC / AppLocker), binary C extensions (`psycopg_binary` `.pyd`) may be blocked. The application configures `PSYCOPG_IMPL=python` and uses ctypes with an allowed native PostgreSQL `libpq.dll` installation.
* **Test Fixture Role Scope:** The test harness fixture in `tests/application/test_application.py` utilizes the database owner connection to dynamically create and drop ephemeral isolated schemas (`test_<uuid>`). Consequently, while application-level checks, transactions, and relational schema constraints are exercised, this harness does not constitute proof of restricted runtime-role (`supportiq_app`) DDL/DML permissions or Alembic production trigger invariants. Those must be evaluated separately under production role contexts.

### 2.2 Legacy Demo & Evaluation SQLite Footprint
* **Scope Separation:** Standalone demonstrations (`apps/demo`) and offline evaluation pipelines operate over local SQLite databases to maintain an isolated, zero-infrastructure footprint runnable without background services.
* **Limitation:** SQLite runs in those tools are intended solely for offline benchmark execution and isolated evaluation passes; they do not serve as proof of multi-role database integrity for the primary application.

---

## 3. Machine Learning Model Artifacts & Fallback Mechanics

### 3.1 Pinned Checkpoint Distribution
The intent classification model (`supportiq_distilbert`, fine-tuned on the 46-intent Bitext Retail E-commerce taxonomy) has its trained weights packaged in PyTorch `model.safetensors` (~260 MB).

* **Limitation:** Large binary weight files are gitignored and not stored directly in the Git commit history.
* **Local Fallback Mode:** When the repository is cloned into a fresh environment without running the model download pipeline, the system may activate `SUPPORTIQ_DEV_FALLBACK_MODEL=true`. This mode uses regex and semantic keyword heuristics to simulate intent predictions across common support queries.
* **Operational Impact:** Fallback mode enables offline UI and API development without requiring GPU resources or 260 MB weights. However, heuristic fallback outputs MUST NOT be attributed to verified model checksums or calibrated confidence scores. Full 46-intent evaluation requires loading the verified weights artifact from release storage into `artifacts/models/trained/distilbert-supportiq/`.

### 3.2 Expected Calibration Error (ECE) Borderline Performance
* **Historical Observation:** On historical benchmark runs (e.g., recorded on 2026-11-05), DistilBERT achieved $\text{ECE} \approx 0.1063$, against an evaluation target of $\text{ECE} \le 0.1000$.
* **Root Cause & Impact:** While Temperature Scaling ($T=1.25$) smoothed raw overconfident logits, DistilBERT exhibited slight overconfidence on high-frequency majority classes (e.g., standard returns).
* **Roadmap Mitigation:** Investigating non-parametric Isotonic Regression or vector scaling on an expanded hold-out validation set.

---

## 4. Knowledge Base & Domain Scope Boundaries

### 4.1 12 In-Scope Product Support Intents vs. Full Bitext Taxonomy
SupportIQ is designed as an **after-sales customer support copilot**. While the underlying intent model is evaluated across all 46 Bitext taxonomy intents, the product application implements 12 core customer support intents:

1. `track_order` (Order tracking, shipment status, delivery tracking links)
2. `cancel_order` (Order cancellation before dispatch, cancellation window checks)
3. `delivery_time` (Estimated delivery timeframe inquiries)
4. `delivery_issue` (Delayed shipment, carrier issues, transit exceptions)
5. `shipping_costs` (Shipping fee inquiries, free shipping thresholds)
6. `return_policy` (Return eligibility, return timeframe, item conditions)
7. `return_product` (Initiating a product return, return label instructions)
8. `refund_policy` (Refund eligibility criteria, refund methods)
9. `request_refund` (Submitting refund request; requires manager authority)
10. `refund_status` (Inquiries on pending refund progress)
11. `payment_issue` (Failed transactions, double charges, payment gateway issues)
12. `human_agent` (Customer explicitly requests a human agent)

* **Behavior on `human_agent`:** When classified as `human_agent`, the system does NOT generate an automated draft; it recommends staff escalation for manual handling.
* **Behavior on Remaining 34 Bitext Intents:** Queries mapping to the other 34 Bitext intents (or out-of-scope pre-sales shopping queries such as product recommendations or stock availability) trigger fallback or abstention (`unsupported_intent`, `out_of_scope_intent`), leaving the ticket open for manual handling without generating ungrounded policy claims.

---

## 5. Privacy & PII Redaction Boundaries

### 5.1 Pre-Egress Sanitization & Order Context Allowlist
SupportIQ enforces pre-egress sanitization before any text or context reaches external LLMs or third-party APIs:
* Credit card numbers are validated and masked using the Luhn algorithm checksum.
* Phone numbers and email addresses are pseudonymized.
* Order IDs (`ORD-\w+`), tracking IDs (`TRK-\w+`), and transaction IDs (`TXN-\w+`) are replaced with deterministic placeholders (`[ORDER_ID_1]`).
* Customer-authored placeholders like `[NAME_1]` are preserved as literal text.
* Order context passed to the AI gateway is strictly allowlisted to non-identifying operational summary fields (`order_status`, `order_total`, `shipping_cost`, `shipment_status`, `refund_status`, `refund_amount`); customer names, shipping addresses, phone numbers, and full credit card details are excluded from AI context.

### 5.2 Unstructured Slang & Vernacular Recall Limitation
* **Limitation:** When a customer writes personal or address information using obscure colloquial vernacular, street slang, or non-standard directions (e.g. directions without standard street, ward, or city keywords), pattern-matching heuristics and spaCy NER may not capture every entity.
* **Mitigation:** Sensitive customer data remains masked by known database values where available; human review remains mandatory before dispatching any reply.

---

## 6. External LLM Provider & Infrastructure Quota

### 6.1 Provider Rate Limits & Failure Handling
SupportIQ optionally integrates with Google Gemini API for draft generation when enabled:
* **Rate Limits:** Developer-tier API keys are subject to requests-per-minute and daily quota ceilings.
* **Transient Recovery vs. Retry Policy:** The system provides bounded timeout recovery for transient connection errors during draft generation. If the quota or budget is exhausted, the ticket transitions to `llm_unavailable`, allowing the support agent to type a manual reply. The UI only permits retrying suggestions that experienced transient failures; ready drafts do not offer an automatic regenerate action.

---

## 7. Empirical Human User Study & Evaluation Boundaries (NFR-11)

### 7.1 Objective Requirement
Non-Functional Requirement NFR-11 specifies:
> *"Handling time is at least 20% shorter than the manual process, measured on at least 30 requests."*

### 7.2 Current Evaluation Scope & Boundaries
* **Distinction between Simulation and Human Study:** Benchmark evaluations and timed comparisons may be conducted via synthetic agent simulation or automated source-based AI grading. However, automated simulations and AI grading MUST NOT be represented as real human graders or live customer support staff trials.
* **Empirical Status:** A controlled paired-user study with counterbalanced order across actual human customer service staff has not yet been executed in production. SupportIQ does NOT make any claim of measured human productivity improvement. Any projected handling time savings represent engineering design targets rather than empirically signed-off human trial results.

---

## 8. Summary Matrix of Limitations & Mitigations

| Dimension | Limitation Description | Current Handling / Impact | Future Direction |
|---|---|---|---|
| **Database** | Dual engine modes: PostgreSQL for application, SQLite for offline demo/eval | PostgreSQL enforces real roles, constraints, and migrations; SQLite is isolated to offline tooling | Maintain clear boundary between application PostgreSQL and evaluation runners |
| **Model Weights** | Binary weights (260 MB) excluded from git tracking | Verified model loaded when artifact present; heuristic fallback clearly segregated and cannot simulate trained provenance | Automated asset download script with sha256 checksum verification |
| **Calibration** | Historical ECE slightly above target ($\approx 0.106$) on single benchmark | Temperature scaling active; raw softmax scores preserved and displayed as uncalibrated | Explore isotonic regression on expanded holdout split |
| **Domain Scope** | 12 customer support intents supported in application; 34 intents abstain | Automated drafts restricted to 11 support intents; `human_agent` escalates; others manual | Expand knowledge base documents with verified policies |
| **PII Protection** | Colloquial slang addresses without standard markers may evade regex | Known account fields masked; strict order context allowlist; human review mandatory | Evaluate localized token-classification NER |
| **LLM Quota** | Provider quota limits on external API calls | Bounded retries for transient errors; graceful degradation to manual staff reply | Provisioned quota or local small-LLM inference |
| **User Study** | 20% handling time reduction target pending human trial | Timing telemetry and audit instrumentation active | Conduct paired human-in-the-loop trial with counterbalancing |
