# SupportIQ Architecture Compliance Audit

> **Audit Date:** 2026-11-06  
> **Target Document:** [docs/ARCHITECTURE.md](file:///home/guts/P2/SupportIQ/docs/ARCHITECTURE.md)  
> **Repository:** SupportIQ (`feature/architecture-alignment`)  
> **Audit Type:** Deep Application Architecture, Codebase, Data Model, ML/RAG, and Business Logic Compliance  
> **Status:** Completed  

---

## 1. Executive Summary

This audit assesses the actual implementation of the **SupportIQ** codebase against the finalized architecture and requirements defined in [docs/ARCHITECTURE.md](file:///home/guts/P2/SupportIQ/docs/ARCHITECTURE.md). Under strict scoping rules, this audit investigates exclusively **application architecture, source code, data models, business logic, AI/ML implementation, security, and software quality**, completely omitting infrastructure, container orchestration, Redis/caching infrastructure, reverse proxies, and deployment hosting.

### Key Conclusions:
1. **Core Human-in-the-Loop & Safety Architecture is Well-Engineered**: The codebase strictly enforces human oversight ([FR-06](file:///home/guts/P2/SupportIQ/docs/ARCHITECTURE.md#L45), [NFR-05](file:///home/guts/P2/SupportIQ/docs/ARCHITECTURE.md#L60)). There is zero automatic transmission to customers, role-based access control (RBAC) is enforced at the backend for all 4 roles, and suggestion idempotency and ticket state transitions prevent duplicate sends.
2. **Critical Retrieval Defect Discovered (Root Cause for Sub-80% Recall@3)**: In [apps/core_backend/retrieval/adapter.py](file:///home/guts/P2/SupportIQ/apps/core_backend/retrieval/adapter.py#L136-L141), semantic search hard-filters candidate policy documents by the *predicted intent* prior to vector search. This directly violates [ADR-0005](file:///home/guts/P2/SupportIQ/docs/decisions/0005-intent-independent-retrieval.md), which explicitly rejected intent filtering to avoid cascading single-point-of-failure errors and mandated intent-independent content retrieval with post-retrieval reranking.
3. **Drafting Policy Contradiction (FR-03)**: [docs/ARCHITECTURE.md](file:///home/guts/P2/SupportIQ/docs/ARCHITECTURE.md#L42) requires that when evidence is insufficient, the system drafts a clarification or identifies missing information. Instead, [apps/core_backend/llm/gemini.py](file:///home/guts/P2/SupportIQ/apps/core_backend/llm/gemini.py#L32) instructs the LLM to return `answerable=false, answer=""`, and [apps/ai_service/engine.py](file:///home/guts/P2/SupportIQ/apps/ai_service/engine.py#L69-L70) treats this as an unrecoverable failure (`llm_unavailable`, `grounding_failed`), generating no draft whatsoever.
4. **Significant Application Performance Bottlenecks**:
   - `apps/backend/tickets/jobs.py` executes `analyses` and `drafts` in parallel via a thread pool, but `drafts` redundantly invokes `_analyse()` internally, executing both DistilBERT inference and BGE vector retrieval twice for every suggestion.
   - Severe $N+1$ query loops exist in [apps/backend/main.py](file:///home/guts/P2/SupportIQ/apps/backend/main.py#L211) and [tickets/service.py](file:///home/guts/P2/SupportIQ/apps/backend/tickets/service.py#L145-L152): listing tickets queries the entire ticket table, executes 3 database queries per ticket in memory, and then slices pagination in Python.
5. **Revalidation of Historical Findings**:
   - Database-level append-only audit enforcement was investigated and confirmed **ALREADY FIXED** via PostgreSQL PL/pgSQL triggers.
   - Reduced demo shop functionality is an **APPROVED_DEVIATION** under [ADR-0002](file:///home/guts/P2/SupportIQ/docs/decisions/0002-shop-demo-scope.md) and [ADR-0013](file:///home/guts/P2/SupportIQ/docs/decisions/0013-shop-demo-with-read-only-catalog.md).
   - Calibrated confidence, out-of-domain (OOD) detection, semantic conflict detection, benchmark validation, and PII leakage risks remain **STILL VALID** and require remediation.

---

## 2. Scope and Methodology

### 2.1 Scope Boundary
- **Included**: Application code (`apps/backend`, `apps/ai_service`, `apps/core_backend`, `apps/frontend`, `apps/ml_inference`), database models and schemas, API boundaries and serialization, ML inference and routing, RAG pipeline, LLM client and prompts, PII anonymization, RBAC, application tests, and ADR alignment.
- **Excluded**: Docker, Docker Compose, Kubernetes, Nginx/Traefik reverse proxies, Redis cache clusters, TLS termination, CI/CD, cloud hosting, and infrastructure monitoring.

### 2.2 Audit Methodology
- **Static Code Analysis**: Complete tracing of execution paths from HTTP intake through database transactions and AI pipeline execution.
- **Contract Cross-Check**: Verification of data models in [apps/backend/api.py](file:///home/guts/P2/SupportIQ/apps/backend/api.py) and [apps/backend/platform/models.py](file:///home/guts/P2/SupportIQ/apps/backend/platform/models.py) against [contracts/backend.openapi.json](file:///home/guts/P2/SupportIQ/contracts/backend.openapi.json) and [docs/ARCHITECTURE.md](file:///home/guts/P2/SupportIQ/docs/ARCHITECTURE.md).
- **Lineage and Benchmark Audit**: Cross-referencing artifacts in `data/benchmarks/`, `data/knowledge/`, and `pipeline/` with evaluation reports in `docs/system-evaluation-report.md`.
- **ADR Verification**: Classification of every architectural drift against ADR-0001 through ADR-0014.

---

## 3. Architectural Baseline

The source of truth for architectural requirements is [docs/ARCHITECTURE.md](file:///home/guts/P2/SupportIQ/docs/ARCHITECTURE.md). The design is complemented by 14 Architecture Decision Records (ADRs) located in `docs/decisions/` and the specification refinement in [docs/product/requirements.md](file:///home/guts/P2/SupportIQ/docs/product/requirements.md).

```mermaid
flowchart TD
    subgraph Client["Presentation Tier"]
        FE["React Frontend<br/>(Shop, Console, Reports, Admin)"]
    end

    subgraph AppServer["Application Backend Tier"]
        BE["FastAPI Core Backend<br/>(apps/backend)"]
        SESS["Cookie Session & RBAC"]
        PRIV["PII Masking / Privacy"]
        WORKER["PostgreSQL Leased Job Worker<br/>(apps/backend/tickets/jobs.py)"]
        DB[("PostgreSQL Database<br/>(Immutable Audit, Triggers)")]
    end

    subgraph AIService["AI & Intelligence Tier"]
        GW["Stateless AI Gateway<br/>(apps/ai_service)"]
        ML["DistilBERT ModelContainer<br/>(apps/ml_inference)"]
        RET["BGE Semantic Retrieval<br/>(apps/core_backend/retrieval)"]
        LLM_CLIENT["GeminiDraftClient<br/>(apps/core_backend/llm)"]
    end

    FE -->|HTTP / JSON (Cookie Auth)| BE
    BE --> SESS
    BE --> PRIV
    BE --> WORKER
    BE --> DB
    WORKER -->|Internal HTTP| GW
    GW --> ML
    GW --> RET
    GW --> LLM_CLIENT
    LLM_CLIENT -->|HTTPS (Allowlisted Host)| EXT_LLM["Google Gemini API"]
```

---

## 4. Overall Compliance Summary

| Category | Status | Compliance Level | Summary |
|---|:---:|:---:|---|
| **FR-01: Intent Classification** | PARTIALLY_COMPLIANT | 75% | Self-trained DistilBERT classifies 46 intents; staff can override. However, confidence scores are uncalibrated raw softmax. |
| **FR-02: Knowledge Retrieval** | PARTIALLY_COMPLIANT | 65% | Retrieval queries KB v2 and attaches mock order context. However, candidate pre-filtering violates ADR-0005, and semantic conflict detection is missing. |
| **FR-03: Grounded Drafts** | PARTIALLY_COMPLIANT | 70% | Strict inline citations `[S1]` and verification implemented. However, missing evidence causes an abortive failure rather than a clarifying draft. |
| **FR-04: Demo E-Commerce Site** | INTENTIONALLY_CHANGED | 90% | Demo storefront exists with catalog, order history, ticket intake, and cancellation. Checkout and cart were reduced under approved ADR-0013. |
| **FR-05: System Language** | COMPLIANT | 100% | Entire system, datasets, prompts, UI, and errors are in English. |
| **FR-06: Human Review Interface** | COMPLIANT | 100% | Full review console with Approve/Edit/Reject/Escalate/Propose actions. Absolute zero-automatic-send path. |
| **FR-07: Fallback & Escalation** | COMPLIANT | 95% | Comprehensive reason codes, low-confidence abstention, sticky manager authority on refunds and disputes. |
| **FR-08: Audit & Traceability** | COMPLIANT | 100% | Decisions, model/prompt versions, latency, and inputs recorded. Database triggers enforce append-only immutability. |
| **FR-09: Authentication & RBAC** | COMPLIANT | 100% | Customer, Staff, Manager, and Admin roles strictly enforced in backend. Admin cannot access customer data. |
| **FR-10: PII Protection** | PARTIALLY_COMPLIANT | 60% | Known profile values and common regex patterns are masked. However, free-form third-party names, addresses, and cards leak to external LLM. |
| **FR-11: Reports & Monitoring** | COMPLIANT | 95% | Manager dashboard aggregates approval rates, escalations, error rates, p50/p95 latency, and token costs. |
| **NFR-01 to NFR-10 Quality Targets** | PARTIALLY_COMPLIANT | 60% | Historical Recall@3 (61.76%) and Grounding (88.24%) fail targets. Empirical 30-case user study not yet performed. |

---

## 5. Requirement Traceability Matrix

*(For the complete line-by-line item matrix, see companion document [docs/audits/ARCHITECTURE_REQUIREMENT_MATRIX.md](file:///home/guts/P2/SupportIQ/docs/audits/ARCHITECTURE_REQUIREMENT_MATRIX.md)).*

---

## 6. Detailed Findings

### FIND-01: Retrieval Adapter Pre-filters Candidates by Intent, Violating ADR-0005 and Degrading Recall@3
* **Finding ID**: `FIND-01`
* **Requirement**: [FR-02](file:///home/guts/P2/SupportIQ/docs/ARCHITECTURE.md#L41), [NFR-03](file:///home/guts/P2/SupportIQ/docs/ARCHITECTURE.md#L58), [ADR-0005](file:///home/guts/P2/SupportIQ/docs/decisions/0005-intent-independent-retrieval.md)
* **Expected**: Retrieval must search all active policies using customer message content independently of predicted intent, followed by intent-aware reranking (`score + λ * P(doc_intent)`), preventing single-point-of-failure errors when ML classification is mistaken.
* **Actual**: [apps/core_backend/retrieval/adapter.py](file:///home/guts/P2/SupportIQ/apps/core_backend/retrieval/adapter.py#L136-L141) strictly filters `applicable_pv` by `intent in pv.metadata.supported_intents` *before* semantic indexing and ranking. If the predicted intent is wrong or narrow, the correct policy document is completely excluded before vector similarity is evaluated.
* **Evidence**:
  ```python
  # apps/core_backend/retrieval/adapter.py:136-141
  if intent:
      applicable_pv = [
          pv for pv in valid_pv
          if not pv.metadata.supported_intents or intent in pv.metadata.supported_intents
      ]
  else:
      applicable_pv = valid_pv
  ```
* **Execution Path**: `SuggestionWorker.process()` → `HTTP POST /v1/analyses` / `drafts` → `Engine._analyse()` → `RetrievalAdapter.retrieve(query, intent)` → candidate pruning → `search_policies()`.
* **Verification**: In [docs/system-evaluation-report.md](file:///home/guts/P2/SupportIQ/docs/system-evaluation-report.md#L36), historical end-to-end Recall@3 was recorded at **61.76%**, directly caused by intent misclassification cascading into total retrieval failure.
* **Gap**: Hard intent filtering was implemented instead of content retrieval with intent-aware reranking.
* **Impact**: Violates NFR-03 (Recall@3 $\ge 0.80$). Causes unnecessary abstentions and forces manual handling.
* **Root Cause**: Incomplete migration of ADR-0005 in `apps/core_backend/retrieval/adapter.py`.
* **Recommendation**: Refactor `RetrievalAdapter.retrieve()` to execute vector search across all temporally valid documents, then apply additive reranking based on the intent probability distribution as mandated by ADR-0005.
* **Priority**: `P0` | **Effort**: `M` | **Confidence**: `High`

---

### FIND-02: LLM Fails to Generate Clarification Drafts When Evidence is Incomplete
* **Finding ID**: `FIND-02`
* **Requirement**: [FR-03](file:///home/guts/P2/SupportIQ/docs/ARCHITECTURE.md#L42), [NFR-04](file:///home/guts/P2/SupportIQ/docs/ARCHITECTURE.md#L59)
* **Expected**: When evidence is missing or insufficient, the LLM must generate a helpful draft stating what information is missing or proposing clarifying questions, rather than asserting unsupported claims.
* **Actual**: The system prompt explicitly commands the model to return empty strings when evidence is missing: `If evidence is missing, irrelevant, or contradictory, set answerable=false, answer="", citations=[]`. In [apps/core_backend/llm/gemini.py](file:///home/guts/P2/SupportIQ/apps/core_backend/llm/gemini.py#L231-L232), `if not draft.answerable` raises `LLMError("llm_insufficient_evidence")`. In [apps/ai_service/engine.py](file:///home/guts/P2/SupportIQ/apps/ai_service/engine.py#L69-L70), this is converted to `status: "llm_unavailable"`, `reason_codes: ["grounding_failed"]`. No draft is returned.
* **Evidence**:
  ```python
  # apps/core_backend/llm/gemini.py:32-34
  "If evidence is missing, irrelevant, or contradictory, set answerable=false, answer=\"\", citations=[]."
  
  # apps/core_backend/llm/gemini.py:231-232
  if not draft.answerable:
      raise LLMError("llm_insufficient_evidence")
  ```
* **Execution Path**: `Engine.draft()` → `GeminiDraftClient.generate()` → prompt instructs `answerable=false` → exception raised → engine catches error and marks `draft_status = "llm_unavailable"`.
* **Verification**: Unit test in [tests/unit/test_gemini_llm.py](file:///home/guts/P2/SupportIQ/tests/unit/test_gemini_llm.py) verifies that unanswerable queries raise exceptions instead of returning clarifying drafts.
* **Gap**: The application treats a valid requirement (clarification) as an unhandled system failure.
* **Impact**: Staff receive no copilot assistance when customer input is underspecified, increasing handling time and violating FR-03.
* **Root Cause**: Prompt design and Pydantic validation conflated ungrounded hallucinations with legitimate clarifying responses.
* **Recommendation**: Update `SYSTEM_PROMPT` and `RESPONSE_SCHEMA` to allow an `answerable_with_clarification` outcome where the LLM produces a clarifying question with `[S_x]` citations for existing known policies.
* **Priority**: `P1` | **Effort**: `M` | **Confidence**: `High`

---

### FIND-03: Redundant Double Inference and Retrieval in Suggestion Worker
* **Finding ID**: `FIND-03`
* **Requirement**: [Mục 5 & 6](file:///home/guts/P2/SupportIQ/docs/ARCHITECTURE.md#L96), [NFR-08](file:///home/guts/P2/SupportIQ/docs/ARCHITECTURE.md#L63)
* **Expected**: `apps/ai_service` and `apps/backend` should coordinate analysis and drafting efficiently without repeating computationally heavy model inference.
* **Actual**: In [apps/backend/tickets/jobs.py](file:///home/guts/P2/SupportIQ/apps/backend/tickets/jobs.py#L118-L120), the worker fires `analyses` and `drafts` concurrently in two threads. In [apps/ai_service/engine.py](file:///home/guts/P2/SupportIQ/apps/ai_service/engine.py#L55-L56), `draft()` internally executes `self._analyse(request)`, which executes the exact same DistilBERT inference and BGE vector retrieval a second time on CPU.
* **Evidence**:
  ```python
  # apps/backend/tickets/jobs.py:118-120
  with ThreadPoolExecutor(max_workers=2) as pool:
      for future in as_completed([pool.submit(fetch, part) for part in ("analysis", "draft")]):
          self.store(identifier, token, *future.result())

  # apps/ai_service/engine.py:55-56
  def draft(self, request):
      analysis, evidence = self._analyse(request)
  ```
* **Execution Path**: Incoming ticket → `SuggestionWorker.process()` → 2 concurrent HTTP requests → `ai_service` runs 2 full DistilBERT forward passes and 2 BGE vector search queries in parallel on 2 PyTorch threads.
* **Verification**: Code trace in `apps/ai_service/main.py` lines 103-116.
* **Gap**: No pipeline caching or intermediate state sharing between the two endpoints.
* **Impact**: Doubles CPU load and inference memory allocation during ticket processing, threatening the 12s p95 latency budget under concurrent load.
* **Root Cause**: `apps/ai_service` was designed to be strictly stateless, but `backend` called both endpoints concurrently without passing analysis results into the drafting request.
* **Recommendation**: Allow `POST /v1/drafts` to accept an optional precomputed `analysis` payload from the caller, or let the worker invoke `drafts` sequentially/composite when drafting is required.
* **Priority**: `P2` | **Effort**: `S` | **Confidence**: `High`

---

### FIND-04: Severe N+1 Database Query and Memory Pagination Vulnerability
* **Finding ID**: `FIND-04`
* **Requirement**: [FR-11](file:///home/guts/P2/SupportIQ/docs/ARCHITECTURE.md#L50), [NFR-08](file:///home/guts/P2/SupportIQ/docs/ARCHITECTURE.md#L63)
* **Expected**: Database queries for ticket and order listings must use SQL-level `LIMIT`, `OFFSET`, or cursor pagination and eager load foreign relationships (`selectinload` or `joinedload`).
* **Actual**: In [apps/backend/main.py](file:///home/guts/P2/SupportIQ/apps/backend/main.py#L205-L212), `listConsoleTickets` queries *all* tickets in the database without SQL pagination. It iterates over the entire result set, calling [summary()](file:///home/guts/P2/SupportIQ/apps/backend/tickets/service.py#L145-L152) for each row. Inside `summary()`, 3 separate database queries are executed for each ticket (`Account`, `Suggestion`, `CustomerMessage`). Finally, Python in-memory slicing `page()` truncates the list.
* **Evidence**:
  ```python
  # apps/backend/main.py:211
  return page([summary(session, ticket) for ticket in session.scalars(select(Ticket).where(Ticket.status == status).order_by(Ticket.created_at, Ticket.ticket_id))], limit, cursor)

  # apps/backend/tickets/service.py:146-151
  account = session.scalar(select(Account).where(Account.customer_id == ticket.customer_id))
  suggestion = session.get(Suggestion, ticket.current_suggestion_id) if ticket.current_suggestion_id else None
  excerpt = session.get(CustomerMessage, ticket.ticket_id).body[:150]
  ```
* **Execution Path**: `GET /v1/console/tickets?status=open` → executes 1 query for $N$ tickets + $3N$ secondary queries + serializes $N$ items in RAM → returns 20 items.
* **Verification**: Inspection of `apps/backend/main.py` lines 167, 197, and 211.
* **Gap**: Complete absence of SQL-level pagination and relationship joining.
* **Impact**: Latency scales linearly ($O(N)$) with total tickets. At 1,000 tickets, a single request triggers 3,001 SQL roundtrips and exhausts the 5s statement timeout.
* **Root Cause**: Developer prioritized rapid delivery with list comprehensions over SQL query optimization.
* **Recommendation**: Push cursor pagination into SQL using `.limit(limit + 1)` and execute a single joined query joining `tickets`, `accounts`, `suggestions`, and `customer_messages`.
* **Priority**: `P1` | **Effort**: `M` | **Confidence**: `High`

---

### FIND-05: PII Pseudonymization Leaks Free-Form Customer Names, Addresses, and Cards
* **Finding ID**: `FIND-05`
* **Requirement**: [FR-10](file:///home/guts/P2/SupportIQ/docs/ARCHITECTURE.md#L49), [NFR-06](file:///home/guts/P2/SupportIQ/docs/ARCHITECTURE.md#L61)
* **Expected**: 100% of payloads sent to the external LLM must be pseudonymized (0 raw PII), covering names, addresses, phone numbers, order IDs, and payment card details.
* **Actual**: In [apps/backend/tickets/privacy.py](file:///home/guts/P2/SupportIQ/apps/backend/tickets/privacy.py#L28-L36), the pseudonymizer only checks known profile strings of the authenticated customer (`actor.name`, `actor.phone`, `actor.address`) and rigid regexes for `EMAIL`, `ORDER_ID`, `TRACKING_ID`, `TRANSACTION_ID`, and `PHONE`.
  - Any name not matching the logged-in user (e.g., recipient or spouse) is not masked.
  - Any address not identical to the profile address is not masked.
  - Credit card numbers have no regex in `patterns`, despite `CARD` being defined in `PLACEHOLDER`.
* **Evidence**:
  ```python
  # apps/backend/tickets/privacy.py:31-36
  patterns = {"EMAIL": r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}",
              "ORDER_ID": r"\bORD-[A-Za-z0-9]+\b", "TRACKING_ID": r"\b(?:TRK-|GIAO|TIKI|VIET|VNPOST)\w+\b",
              "TRANSACTION_ID": r"\b(?:TXN-|TIKI-TXN-)\w+\b",
              "PHONE": r"(?<!\w)(?:\+?\d[ .()-]?){9,15}(?!\w)"}
  ```
* **Execution Path**: Customer writes: *"Please send to my friend Jane Doe at 456 Elm St, card 4111222233334444"* → `pseudonymize()` does not detect these entities → raw text sent directly to Google Gemini in `prepare_llm_input()`.
* **Verification**: In [tests/application/test_application.py](file:///home/guts/P2/SupportIQ/tests/application/test_application.py#L273), test only verifies masking of the user's *own* seed order IDs and exact profile values.
* **Gap**: Regex heuristic fails on arbitrary named entities, unstructured addresses, and credit card numbers.
* **Impact**: Violates NFR-06 (0% personal data leakage). PII is transmitted to an external LLM provider.
* **Root Cause**: Heuristic approach without a lightweight local NER (Named Entity Recognition) model or comprehensive pattern suite.
* **Recommendation**: Add credit card Luhn regex patterns, address regexes, and integrate a fast offline Spacy/Flair/regex NER pipeline for capitalized personal name detection.
* **Priority**: `P0` | **Effort**: `M` | **Confidence**: `High`

---

### FIND-06: Uncalibrated Softmax Scores and Absence of Open-Set Out-of-Domain Detection
* **Finding ID**: `FIND-06`
* **Requirement**: [FR-01](file:///home/guts/P2/SupportIQ/docs/ARCHITECTURE.md#L40), [NFR-01](file:///home/guts/P2/SupportIQ/docs/ARCHITECTURE.md#L56), [NFR-02](file:///home/guts/P2/SupportIQ/docs/ARCHITECTURE.md#L57)
* **Expected**: The ML model must provide calibrated confidence scores; $\ge 90\%$ of out-of-scope or ambiguous messages must be flagged as low confidence or rejected.
* **Actual**:
  - [apps/ml_inference/app.py](file:///home/guts/P2/SupportIQ/apps/ml_inference/app.py) directly returns raw softmax probabilities, explicitly setting `score_kind = "uncalibrated_softmax"`.
  - [apps/ai_service/engine.py](file:///home/guts/P2/SupportIQ/apps/ai_service/engine.py#L25-L26) identifies out-of-scope queries solely by checking `label not in supported_12_intents`. Because the 46-class Bitext model is a closed-set classifier, arbitrary irrelevant queries (e.g., medical, political, or weather queries) are forced into one of the 46 intents, often with high softmax overconfidence, bypassing the threshold.
* **Evidence**:
  ```python
  # apps/ai_service/engine.py:20-26
  low = not override and (probability < threshold or prediction.get("margin", 0) < self.policy.get("margin_thresholds", {}).get(label, self.policy.get("default_margin_threshold", .1)))
  if low:
      codes.append("low_confidence")
  if label not in self.policy["supported_12_intents"]:
      codes.append("out_of_scope_intent")
  ```
* **Execution Path**: Irrelevant user input → `ModelContainer.predict()` → Softmax peak overconfidence on unrelated label → `probability > threshold` → system routes ticket to draft instead of abstaining.
* **Verification**: [docs/guides/application-verification.md](file:///home/guts/P2/SupportIQ/docs/guides/application-verification.md#L38) confirms: *"Raw scores stay labeled Raw score; no calibrator was invented"*.
* **Gap**: Lack of temperature scaling / Platt calibration, and lack of an OOD detection mechanism (e.g., maximum logit, energy score, or semantic distance).
* **Impact**: Violates NFR-02 robustness requirements. The copilot attempts to answer nonsensical or malicious out-of-domain requests.
* **Root Cause**: Team prioritized Macro-F1 optimization on the closed-set Bitext dataset and deferred calibration to post-v1.
* **Recommendation**: Fit temperature scaling parameters on the validation split and implement an embedding distance or entropy threshold to reject open-set OOD inputs.
* **Priority**: `P1` | **Effort**: `M` | **Confidence**: `High`

---

### FIND-07: Semantic Policy Conflict Detection is Completely Missing
* **Finding ID**: `FIND-07`
* **Requirement**: [FR-02](file:///home/guts/P2/SupportIQ/docs/ARCHITECTURE.md#L41), [NFR-03](file:///home/guts/P2/SupportIQ/docs/ARCHITECTURE.md#L58)
* **Expected**: 100% of expired, missing, or contradictory documents in the test set must be detected and flagged with warnings (`conflicting_sources`).
* **Actual**: While expired policies are filtered via `valid_to` and missing documents trigger `no_valid_document`, there is no logic anywhere in [apps/core_backend/retrieval/](file:///home/guts/P2/SupportIQ/apps/core_backend/retrieval/) or [apps/ai_service/engine.py](file:///home/guts/P2/SupportIQ/apps/ai_service/engine.py) that compares multiple retrieved policies to detect mutually inconsistent terms.
* **Evidence**:
  ```python
  # apps/ai_service/engine.py:34-44
  evidence = retrieved.get("evidence", [])
  if not evidence:
      codes.append("no_valid_document")
  # No pairwise conflict checking between evidence items
  ```
* **Execution Path**: Two valid documents with conflicting return windows (e.g., 14 days vs 30 days) are retrieved → both marked `validity: "valid"` → passed directly to LLM → prompt instructs model to fail answerability, resulting in `llm_unavailable`.
* **Verification**: Grepping `conflicting_sources` across the codebase reveals it is only defined in enum constants in `jobs.py` and never emitted by the retrieval adapter.
* **Gap**: Zero implementation of policy conflict detection.
* **Impact**: Violates FR-02 and NFR-03. Conflicting policy versions cannot be audited or surfaced to staff.
* **Root Cause**: Detection of semantic contradiction requires Natural Language Inference (NLI) or rule-based capability matching, which was not built.
* **Recommendation**: Implement rule-based conflict checking comparing `answer_capabilities` and policy keys among retrieved documents, emitting `conflicting_sources` when contradictory policies match the same query.
* **Priority**: `P2` | **Effort**: `M` | **Confidence**: `High`

---

### FIND-08: Database Relational Integrity and Constraint Deficiencies
* **Finding ID**: `FIND-08`
* **Requirement**: [Mục 5 & 6](file:///home/guts/P2/SupportIQ/docs/ARCHITECTURE.md#L95), [FR-08](file:///home/guts/P2/SupportIQ/docs/ARCHITECTURE.md#L47), [FR-09](file:///home/guts/P2/SupportIQ/docs/ARCHITECTURE.md#L48)
* **Expected**: Relational models must enforce referential integrity with foreign keys, unique constraints, and structured column schemas.
* **Actual**: In [apps/backend/platform/models.py](file:///home/guts/P2/SupportIQ/apps/backend/platform/models.py):
  - `Account.customer_id` is an unindexed, unconstrained string without a relationship to `orders`.
  - `Order.customer_id` has no foreign key to `accounts`.
  - `Ticket.current_suggestion_id` is a plain string without a foreign key to `suggestions.suggestion_id`.
  - `AuditEntry.actor_account_id` and `ticket_id` are unconstrained strings.
  - Critical business entities (`Product.payload`, `Order.payload`, `Suggestion.payload`, `Ticket.proposal`, `Ticket.escalation`, `Ticket.reply`) are stored entirely as unstructured JSON columns without database-level schema validation.
* **Evidence**:
  ```python
  # apps/backend/platform/models.py:20, 54, 69, 114-115
  customer_id: Mapped[str | None] = mapped_column(String) # No FK
  current_suggestion_id: Mapped[str | None] = mapped_column(String) # No FK
  payload: Mapped[dict] = mapped_column(JSON) # Unvalidated JSON
  ```
* **Execution Path**: Application insertion → database accepts corrupted or orphan foreign keys silently.
* **Verification**: [apps/backend/migrations/versions/0001_application.py](file:///home/guts/P2/SupportIQ/apps/backend/migrations/versions/0001_application.py) creates tables with JSON fields and omitted foreign keys.
* **Gap**: Database integrity relies 100% on application code correctness; database engine cannot enforce consistency.
* **Impact**: Risk of orphaned records, referential anomalies during deletions, and unindexed joins.
* **Root Cause**: Fast schema iteration during prototype development using JSON documents.
* **Recommendation**: Add explicit `ForeignKey` constraints on `current_suggestion_id` and `customer_id`, add compound indexes, and define check constraints for status enums.
* **Priority**: `P2` | **Effort**: `M` | **Confidence**: `High`

---

### FIND-09: Unhandled AI Service Error Protocol Inconsistency
* **Finding ID**: `FIND-09`
* **Requirement**: [FR-07](file:///home/guts/P2/SupportIQ/docs/ARCHITECTURE.md#L46), [NFR-07](file:///home/guts/P2/SupportIQ/docs/ARCHITECTURE.md#L62)
* **Expected**: Inter-service errors between `backend` and `ai_service` must adhere to RFC 9457 Problem Details with granular failure codes (`timeout`, `auth_error`, `rate_limit`, `validation`).
* **Actual**: In [apps/ai_service/main.py](file:///home/guts/P2/SupportIQ/apps/ai_service/main.py#L107-L115), errors raise standard FastAPI `HTTPException(503, "...")`, returning `{"detail": "..."}`. In [apps/backend/tickets/jobs.py](file:///home/guts/P2/SupportIQ/apps/backend/tickets/jobs.py#L116), the worker catches all exceptions indiscriminately:
  ```python
  except (httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError):
      return part, None, round((time.perf_counter() - started) * 1000)
  ```
  This causes all distinct errors (rate limits, prompt rejections, internal bugs) to collapse into `ai_service_unavailable`.
* **Evidence**: `apps/ai_service/main.py` lines 107-115 and `apps/backend/tickets/jobs.py` line 116.
* **Execution Path**: Google Gemini returns HTTP 429 → `GeminiDraftClient` raises `LLMError("llm_rate_limited")` → `ai_service` catches and returns 503 → `jobs.py` swallows specific code and logs generic `ai_service_unavailable`.
* **Verification**: Inspecting `jobs.py` lines 136-137.
* **Gap**: Loss of error fidelity and failure lineage across the service boundary.
* **Impact**: Obscures telemetry and causes incorrect reporting in manager dashboards.
* **Root Cause**: Overly broad `except` block in `jobs.py`.
* **Recommendation**: Standardize RFC 9457 Problem Details across `ai_service` and parse structured failure codes in `jobs.py`.
* **Priority**: `P2` | **Effort**: `S` | **Confidence**: `High`

---

### FIND-10: Test Environment Fragility Due to Unconditional Model Monkeypatching
* **Finding ID**: `FIND-10`
* **Requirement**: Testing and Code Quality, Constraint CST-04
* **Expected**: Non-ML unit tests (backend API, database triggers, privacy logic) should run cleanly in lightweight Python environments without requiring heavy machine learning packages.
* **Actual**: In [tests/conftest.py](file:///home/guts/P2/SupportIQ/tests/conftest.py#L111-L112), `offline_resources` unconditionally imports and monkeypatches `transformers.AutoTokenizer` and `_BaseAutoModelClass` at the root setup of *every* test.
* **Evidence**:
  ```python
  # tests/conftest.py:111-112
  if not request.node.get_closest_marker("real_model"):
      def no_weights(*args, **kwargs):
          raise RuntimeError("loading weights/tokenizer requires explicit real_model profile")
      monkeypatch.setattr("transformers.AutoTokenizer.from_pretrained", no_weights)
      monkeypatch.setattr("transformers.models.auto.auto_factory._BaseAutoModelClass.from_pretrained", no_weights)
  ```
* **Execution Path**: Running `pytest tests/application/test_application.py` without `transformers` installed causes `ModuleNotFoundError: No module named 'transformers'` during fixture setup.
* **Verification**: Running `pytest` in any standard Python environment failed with 24 collection errors.
* **Gap**: Missing conditional import guard (`importlib.util.find_spec("transformers")`).
* **Impact**: Prevents testing backend, security, and database features in standard CI or developer environments without the full ML toolchain.
* **Root Cause**: Conftest assumed a single monolithic virtual environment.
* **Recommendation**: Wrap transformers monkeypatching in `try: import transformers ... except ImportError: pass`.
* **Priority**: `P3` | **Effort**: `S` | **Confidence**: `High`

---

## 7. Revalidation of Previously Reported Findings

The 11 issues highlighted in earlier reviews were independently audited against the latest codebase, database migrations, tests, and ADRs:

| # | Previously Reported Issue | Revalidated Status | Direct Code Evidence & Technical Rationale |
|---|---|:---:|---|
| **1** | **Calibrated confidence score** | **STILL VALID** | [apps/ai_service/engine.py](file:///home/guts/P2/SupportIQ/apps/ai_service/engine.py#L19), [apps/ml_inference/app.py](file:///home/guts/P2/SupportIQ/apps/ml_inference/app.py#L85). Scores are explicitly labeled `uncalibrated_softmax` with no calibration layer implemented. |
| **2** | **Out-of-domain (OOD) detection** | **STILL VALID** | [apps/ai_service/engine.py](file:///home/guts/P2/SupportIQ/apps/ai_service/engine.py#L25). OOD is evaluated solely by checking if the predicted label is in the 12 product intents. Open-domain queries still trigger false-positive predictions. |
| **3** | **Benchmark v3 independent approval** | **STILL VALID** | [docs/system-evaluation-report.md](file:///home/guts/P2/SupportIQ/docs/system-evaluation-report.md#L27). Acceptance v3 contains 156 cases whose gold labels and coverage matrix are uncertified by external review. |
| **4** | **Recall@3 below 80%** | **STILL VALID** | [docs/system-evaluation-report.md](file:///home/guts/P2/SupportIQ/docs/system-evaluation-report.md#L36) reports historical 61.76%. **Root cause identified in this audit**: [adapter.py](file:///home/guts/P2/SupportIQ/apps/core_backend/retrieval/adapter.py#L136-L141) pre-filters documents by predicted intent prior to vector search. |
| **5** | **Semantic policy conflict detection** | **STILL VALID** | [apps/core_backend/retrieval/adapter.py](file:///home/guts/P2/SupportIQ/apps/core_backend/retrieval/adapter.py). Zero pairwise contradiction detection logic exists in the codebase. |
| **6** | **Grounding below 90%** | **STILL VALID** | [docs/system-evaluation-report.md](file:///home/guts/P2/SupportIQ/docs/system-evaluation-report.md#L45) records 88.24% (15/17 claims supported, 2 unknown). Needs certified live evaluation. |
| **7** | **Abstention vs. clarification behavior** | **STILL VALID** | [apps/core_backend/llm/gemini.py](file:///home/guts/P2/SupportIQ/apps/core_backend/llm/gemini.py#L32) and [engine.py](file:///home/guts/P2/SupportIQ/apps/ai_service/engine.py#L69). Insufficient evidence causes `llm_unavailable` exception rather than generating a clarifying draft. |
| **8** | **Incomplete PII pseudonymization** | **STILL VALID** | [apps/backend/tickets/privacy.py](file:///home/guts/P2/SupportIQ/apps/backend/tickets/privacy.py#L28-L36). Regex-only masking leaks arbitrary third-party names, custom addresses, and payment cards. |
| **9** | **Database-level append-only audit enforcement** | **ALREADY FIXED** | [apps/backend/platform/database.py](file:///home/guts/P2/SupportIQ/apps/backend/platform/database.py#L35-L41). PostgreSQL trigger `immutable_record` strictly blocks `UPDATE` and `DELETE` on `audit_log_entries` and `customer_messages`. Verified by [tests/application/test_application.py:225-232](file:///home/guts/P2/SupportIQ/tests/application/test_application.py#L225-L232). |
| **10** | **Reduced Shop functionality** | **APPROVED_DEVIATION** | [ADR-0002](file:///home/guts/P2/SupportIQ/docs/decisions/0002-shop-demo-scope.md) and [ADR-0013](file:///home/guts/P2/SupportIQ/docs/decisions/0013-shop-demo-with-read-only-catalog.md). Read-only catalog with single-order demo was formally accepted by team to keep payments out of scope. |
| **11** | **Missing user study for handling-time reduction** | **STILL VALID** | [apps/backend/tickets/reports.py](file:///home/guts/P2/SupportIQ/apps/backend/tickets/reports.py#L34). Telemetry instrumentation is present, but the empirical 30-case study required by NFR-10 has not been executed. |

---

## 8. Newly Discovered Issues Summary

Beyond the 11 known issues, this audit identified 5 new structural gaps:
1. **FIND-01**: Intent pre-filtering in retrieval directly contradicts ADR-0005.
2. **FIND-03**: Redundant duplicate inference and vector retrieval in `apps/backend/tickets/jobs.py`.
3. **FIND-04**: $O(N)$ query explosion and in-memory pagination in `apps/backend/main.py`.
4. **FIND-08**: Missing relational foreign keys on `current_suggestion_id` and over-reliance on unstructured JSON blobs.
5. **FIND-10**: Fragile test harness crashing on non-ML test suites when transformers is absent.

---

## 9. ADR Compliance Analysis

| ADR | Title | Classification | Analysis & Impact |
|---|---|:---:|---|
| **ADR-0001** | System architecture and component boundaries | **COMPLIANT** | Three components (`frontend`, `backend`, `ai-service`) interact strictly via versioned HTTP APIs. |
| **ADR-0002** | Shop demo scope | **COMPLIANT** | Catalog and order viewing with simulated support requests. |
| **ADR-0003** | Tech stack | **COMPLIANT** | React, FastAPI, SQLAlchemy, PostgreSQL, and Gemini LLM match specifications. |
| **ADR-0004** | API conventions | **COMPLIANT** | RFC 9457 Problem Details and Idempotency-Key headers implemented across backend. |
| **ADR-0005** | Intent-independent retrieval | **UNAPPROVED_DEVIATION** | Code in `adapter.py` lines 136-141 pre-filters documents by predicted intent, violating the core decision of ADR-0005. |
| **ADR-0006** | Staff feedback and reason codes | **COMPLIANT** | Standard staff reason codes (`wrong_intent`, `unsupported_claim`, etc.) implemented in console. |
| **ADR-0007** | Observability stack | **COMPLIANT** | OpenTelemetry trace IDs propagated across HTTP boundaries and audit entries. |
| **ADR-0008** | UI design system | **COMPLIANT** | Framed sheet UI tokens and clean accessibility components match approved mockups. |
| **ADR-0009** | Demo accounts & cookie sessions | **COMPLIANT** | Server-side cookie sessions in PostgreSQL replace stateless JWTs. |
| **ADR-0010** | Pseudonymization & egress control | **PARTIALLY_COMPLIANT** | Egress transport restriction implemented in Python; however, pseudonymizer leaks unlisted PII entities. |
| **ADR-0011** | Deployment & runtime topology | **DOCUMENTATION_DRIFT** | ADR-0011 proposed deferring Redis caching and multi-replica topology, but `ARCHITECTURE.md` was never updated to reflect this deferral. |
| **ADR-0012** | Roles v1 | **COMPLIANT** | Role hierarchy (`customer`, `staff`, `manager`, `admin`) strictly separated. |
| **ADR-0013** | Shop demo with read-only catalog | **APPROVED_DEVIATION** | Approved removal of shopping cart, payment gateway, and complex checkout. |
| **ADR-0014** | Citations to order context | **COMPLIANT** | Distinct order context citations (`[S_order]`) separated from policy citations. |

---

## 10. Cross-Module Integration Problems

1. **Tight Coupling between `apps/ai_service` and Legacy `apps/core_backend`**:
   - `apps/ai_service/main.py` directly imports internal classes from `apps.core_backend.retrieval.adapter`, `apps.core_backend.llm.gemini`, and reads hardcoded filesystem paths `../../data/knowledge/approved_kb.v2.json`.
   - `apps/core_backend` still contains legacy offline orchestration stores (`orchestration/store.py`), causing architectural ambiguity over which code belongs to production serving versus offline evaluation.
2. **Redundant Schema Definitions**:
   - Intent enum lists are duplicated across `apps/backend/tickets/service.py` (`INTENTS`), `apps/frontend/src/features/console.tsx` (`intents`), and `apps/core_backend/config/policies/intent_policy.v2.json`. A new intent requires synchronized changes in 3 different files.

---

## 11. Security and Privacy Assessment

* **Authentication & Session Security**: Excellent. Argon2 password hashing with dummy hashing prevents timing attacks ([apps/backend/main.py:36](file:///home/guts/P2/SupportIQ/apps/backend/main.py#L36)). Session cookies are `HttpOnly`, `SameSite=Lax`, with secure flag support.
* **Access Control (RBAC)**: Robust. Verified that `execute(request, roles, ...)` enforces role constraints on all routes. Customer cannot access internal tickets; staff cannot approve manager-required actions; admin cannot access customer messages or orders.
* **Audit Trail Security**: Hardened. Database triggers prevent any tampering or deletion of `audit_log_entries` and `customer_messages`.
* **PII & Egress Vulnerability**: Moderate Risk. `AllowListedTransport` prevents egress calls to unauthorized hosts, but regex-based pseudonymization allows unindexed customer names, secondary addresses, and credit cards to leak into Gemini API payloads.

---

## 12. ML & RAG Assessment

* **DistilBERT Classification**: High quality on in-domain Bitext (Macro-F1 0.995 on CV), but lacks calibration and open-set OOD rejection.
* **BGE Retrieval**: Embeddings and Cosine similarity are technically sound, but crippled by intent pre-filtering in `adapter.py`.
* **LLM Grounding & Prompt Quality**: System prompt enforces strict grounding and verifiable citations (`[S1]`, `[S2]`). Hallucination risk is low, but refusal behavior is over-aggressive (fails entirely when input is ambiguous instead of clarifying).

---

## 13. Business Logic Assessment

* **Ticket Lifecycle**: State machine transitions (`open` → `awaiting_approval` → `escalated` → `closed`) are rock solid.
* **Manager Authority Rule (FR-06)**: Sensitive intents (`request_refund`, dispute keywords) trigger sticky `is_authority_required = True`. Staff can only submit proposals; only managers can send final replies.
* **Storefront Logic**: Simple, functional, and aligns with ADR-0013.

---

## 14. Testing and Code Quality

* **Test Coverage**: High coverage across business workflows, idempotency, concurrent sends, and role protection.
* **Test Isolation**: Heavy reliance on mocks in integration suites; end-to-end tests require live Edge browser.
* **Code Smells**:
  - Extensive list comprehensions doing in-memory pagination and $N+1$ querying.
  - Large single-file UI components (`apps/frontend/src/features/console.tsx` has 98 lines of dense, compressed JSX).
  - Unconditional transformers import in root `conftest.py`.

---

## 15. Documentation Drift

1. **`docs/ARCHITECTURE.md` vs. ADR-0011**:
   - `docs/ARCHITECTURE.md` specifies an edge Load Balancer, internal ML Load Balancer, and 5 Redis caches.
   - ADR-0011 formally deferred Redis and mapped multi-replica routing onto Compose/Nginx.
   - `ARCHITECTURE.md` was never revised to note these accepted deferrals.
2. **`docs/api/core-backend.openapi.yaml` vs. Actual API**:
   - `docs/api/core-backend.openapi.yaml` defines a legacy JWT/Bearer token specification with `/api/v1/sessions/refresh`.
   - The actual implementation uses cookie sessions documented in `contracts/backend.openapi.json`. The yaml file is obsolete.

---

## 16. Prioritized Recommendations

### P0 (Must Fix Before Submission / Critical Correctness & Privacy)
1. **Fix Retrieval Intent Pre-filtering (`FIND-01`)**: Remove lines 136-141 in `apps/core_backend/retrieval/adapter.py`. Implement content-first retrieval followed by intent-aware reranking to restore Recall@3 $\ge 80\%$.
2. **Harden PII Pseudonymizer (`FIND-05`)**: Add credit card detection and capitalized name detection heuristics in `apps/backend/tickets/privacy.py` to prevent data leakage to external LLM.

### P1 (High Priority / Architectural & Contract Compliance)
3. **Implement Clarification Drafts (`FIND-02`)**: Update LLM prompt and schema to generate missing-information drafts rather than throwing exceptions when evidence is incomplete.
4. **Resolve N+1 Queries & Memory Pagination (`FIND-04`)**: Push SQL `LIMIT`/`OFFSET` and eager joins into `apps/backend/main.py`.
5. **Implement Softmax Calibration (`FIND-06`)**: Implement temperature scaling on validation logits to expose true calibrated probabilities.

### P2 (Medium Priority / Optimization & Cleanliness)
6. **Eliminate Redundant Double Inference (`FIND-03`)**: Refactor suggestion job worker to share analysis outputs with drafting.
7. **Add Database Foreign Keys (`FIND-08`)**: Enforce FK constraints on `current_suggestion_id` and status columns.
8. **Add Semantic Conflict Checking (`FIND-07`)**: Add pairwise rule-based capability checking in retrieval to flag conflicting documents.

### P3 (Low Priority / Tech Debt & Documentation)
9. **Fix Conftest Monkeypatching (`FIND-10`)**: Make transformers import conditional in `tests/conftest.py`.
10. **Synchronize Documentation Drift**: Archive obsolete `docs/api/core-backend.openapi.yaml` and add an appendix note to `docs/ARCHITECTURE.md` referencing ADR-0011.

---

## 17. Unknowns and Verification Requirements

1. **Live Gemini Grounding Rate**: While local unit tests pass with mocks, a certified live run on the 156-case Acceptance v3 suite with external grading is required to prove $\ge 90\%$ grounding under real API conditions.
2. **Empirical User Study**: Proving the $\ge 20\%$ reduction in handling time requires executing the comparative 30-case evaluation with human support agents.
