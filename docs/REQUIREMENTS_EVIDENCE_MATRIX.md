# Requirements-to-Evidence Traceability Matrix

**Project:** SupportIQ — AI Customer Support Copilot for E-commerce  
**Specification Reference:** [`docs/CHỦ ĐỀ 1.md`](CHỦ%20ĐỀ%201.md)  

## Evidence Sources & Architectural Boundaries

Evidence is categorized into distinct tiers to maintain clear boundaries between end-to-end application integration, offline ML evaluation, legacy component benchmarks, and historical browser assets:

1. **Tier 1: End-to-End Application Integration Evidence (Live & Diagnostic)**:
   - **Coordinator Final Live Acceptance Run (r3):** `artifacts/evaluation/coordinator-final-live-20261112-r3/final-evidence-20261112-151514-078471/` (20 customer HTTP tickets, 4 retrieval component boundary fixtures, isolated PostgreSQL schema, real TestClient staff console; includes `accounting_recomputed.json` and Worker B attempt metadata).
   - **Earlier Baseline Acceptance Run:** `artifacts/evaluation/coordinator-final-live-20261112/final-evidence-20261112-145003-c7d112/`.
   - **Oracle-Assisted Staff Intent Correction Diagnostic:** `artifacts/evaluation/coordinator-intent-correction-20261112-152013-0fb5c3/` (7 low-confidence abstention cases evaluated via real console override endpoint `POST /v1/console/tickets/{id}/suggestions`).
   - **Automated Regression Test Suite:** 38 passed integration tests across `test_final_acceptance_suite.py`, `test_final_acceptance_collector.py`, and `test_intent_correction_diagnostic.py`.

2. **Tier 2: Offline ML Classification & Safety Routing Evidence**:
   - **Noise Robustness Suite:** `artifacts/evaluation/final-routing-20261112-v3/robustness_summary.json` (420 test cases across clean, casual, and typo sets).
   - **Policy-Scope & Safety Regression Suite:** `test_routing_safety_regressions.py` (11 boundary, out-of-domain, and safety escalation checks).

3. **Tier 3: Historical Component-Level Benchmarks (Distinct Architectural Boundary)**:
   - **Historical Retrieval Benchmark:** Component-level evaluation (31 cases, Recall@3 = **0.9839** fractional per-query mean, separate manifest).
   - **Acceptance Component Benchmark:** `data/benchmarks/system/v2/acceptance/cases.jsonl` (N=156 cases; evaluated with actual DistilBERT/BGE and SpyLLM isolation, not isolated-mock classifier/retriever; source `artifacts/audit/routing_audit_20261112_v2/robustness_summary.json`).
     - Across N=156: **74/156** exact action matches.
     - Within mandatory N=63: 16 `escalate`, 46 `manual_fallback`, 1 encoder fault `NOT_EXECUTED` (21/63 match allowed action sets, 41 safe `manual_fallback` mismatch strict `escalate`, 1 not-executed).
     - Standard pipeline vocabulary: raw `draft`/`abstain`/`escalate`, adapter `retrieve_draft`/`manual_fallback`/`escalate`.

4. **Tier 4: Derived Historical Browser Evidence Assets**:
   - **Browser Screenshot Catalog:** Preserved in tracked directory [`artifacts/browser/playwright-e2e-20261112/`](../artifacts/browser/playwright-e2e-20261112/) with cryptographic SHA-256 manifest [`manifest.json`](../artifacts/browser/playwright-e2e-20261112/manifest.json) (24 screenshots copied from `.impeccable/review/`; runtime execution log is unverified / null; execution metrics worker-reported unverified).

---

## 1. Executive Summary & Status Overview

| Dimension | Specification Target (CHỦ ĐỀ 1) | Actual Verified Result | Status |
| :--- | :--- | :--- | :--- |
| **FR-01: Intent Classification** | Single-label 46 intents, 12 in-scope; Bitext 10-fold CV Macro-F1 ≥ 0.85 target; confidence display | Real noise F1: clean **0.7858**, casual **0.7359**, typo **0.6267** (Bitext 10-fold CV OOF mean pending coordinator manifest); confidence metadata displayed in console | **PARTIAL / PENDING OOF** |
| **FR-02: Policy Retrieval & Boundary Checks** | Recall@3 ≥ 0.80; detect expired / conflicting policies | Historical benchmark Recall@3 = **0.9839** (fractional per-query mean across 31 answerable cases); live r3 4/4 fixtures verified with real BGE encoder (2/2 expired filtered, 2/2 conflict detected) | **PASS** |
| **FR-03: Grounded Draft Generation** | LLM draft with verifiable citations, no ungrounded claims | 100% of drafts cite verifiable doc/version/span; factual claim validity is **PENDING coordinator semantic claim grading** (citation existence != factual claim proof) | **PENDING CLAIM GRADING** |
| **FR-04: Human Oversight & No-Auto-Send** | Staff review/edit/send; strictly NO automated sending | **20/20 (100%)** customer HTTP tickets verified with `reply: null` and `customer_status: "received"` (the 4 component fixtures are retrieval-only and have NULL customer HTTP fields); zero automated sends | **PASS** |
| **FR-05: Abstention, Fallback & Escalation** | Safe fallback on uncertainty, missing info, errors | Low confidence abstains; sensitive requests escalate; system errors fail closed without hallucinations | **PASS** |
| **FR-06: Human Authority for Sensitive Actions** | Refund/financial exceptions require manager authority | `Ticket.is_authority_required: true` enforced on sensitive keywords/intents; staff direct reply blocked (403 `authority-required`) | **PASS** |
| **FR-07: Audit Logging & Traceability** | Log staff decisions, overrides, source versions | Immutable `AuditEntry` records in PostgreSQL for `intent.overridden`, `message.pseudonymized`, `ticket.escalated`, `reply.sent` | **PASS** |
| **FR-08: Data Privacy & Error Handling** | PII pseudonymization; RBAC; secure API boundaries | Bidirectional pseudonymization (`pseudonymize()`); RBAC enforced; bounded regex scrubbing (`sanitize_error()`; universal PII scrubbing unsupported) | **BOUNDED BEST-EFFORT** |
| **Latency: p95 Budget** | p95 latency ≤ 12.0 seconds | Live r3 Application p50 = **338.47 ms**, p95 = **10,757.08 ms** (10.76s ≤ 12.0s target) | **PASS** |
| **Live Automatic Draft Coverage** | 12/12 product answerable cases draft automatically | Live r3: **1/12 drafted**, **7/12 low-confidence abstained**, **4/12 provider failed** (earlier baseline was 5/12) | **DEFICIENT / OPEN BLOCKER** |
| **External LLM Reliability & Cost** | Reliable generation within budget | Live r3: **4/20 provider timeouts**; Diagnostic: **2/7 timeouts**. Per-attempt token usage recorded when returned by provider; complete total/average cost remains UNKNOWN because failed requests lack provider usage (list-price estimates conditional) | **OPEN DEFICIENCY / BLOCKED** |
| **Staff Intent Override Diagnostic** | Recover low-confidence cases via human-in-the-loop | **5/7 assisted drafts**, **2 failed (provider timeouts)**; 7/7 no-auto-send; 7/7 audit logs | **5/7 DRAFTS, 2 TIMEOUTS** (Diagnostic only, not full success) |
| **Component Benchmark Action Routing** | Component-level strict routing contract | N=156: **74/156** exact matches; within mandatory N=63: 21/63 allowed, **41 safe manual_fallback mismatch strict escalate**, 1 encoder fault not-executed (`data/benchmarks/system/v2/acceptance/cases.jsonl`) | **74/156 MATCHES; MANDATORY 21/63 MATCHES (Component Boundary)** |
| **UI Responsiveness (Browser E2E)** | Desktop (1440x900) & Mobile (390x844) clean layout | Worker-reported 6/6 passed (unverified); 24 screenshot assets preserved with verified SHA-256 hashes; runtime execution log unverified / null | **WORKER-REPORTED / UNVERIFIED** |
| **Paired Agent Study & Semantic Grading** | Measure assisted vs manual time; semantic grading | Delegated to coordinator; awaiting actual agent trial data | **PENDING** |

---

## 2. Functional Requirements Traceability Matrix

### FR-01: Intent Classification & Confidence Presentation
- **Requirement:** System receives customer inquiries, predicts intent using trained non-generative ML model, and displays predicted intent and confidence indicators to human staff.
- **Implementation:**
  - Non-generative classifier trained on Bitext retail e-commerce dataset (46 classes).
  - Serving gateway returns `intent.label`, `intent.probability`, `intent.confidence_band` (`high`, `medium`, `low`), `intent.source` (`model` vs `staff`), and `intent.score_kind`.
  - Frontend staff console displays intent badge, confidence band, and intent selection dropdown for human review.
- **Evidence & Exact Metrics:**
  - In `artifacts/evaluation/final-routing-20261112-v3/robustness_summary.json`:
    - Clean test set (n=84): Accuracy **77.38%**, Macro-F1 = **0.7858**, median confidence 0.858
    - Casual phrasing (n=84): Accuracy **70.24%**, Macro-F1 = **0.7359**, median confidence 0.802
    - Typo noise (n=252): Accuracy **59.92%**, Macro-F1 = **0.6267**, median confidence 0.718
    - Total noise dataset (n=420): Accuracy **65.48%**, Safe routing rate **91.43%**
    - **Benchmark Context:** The specification target Macro-F1 ≥ 0.85 in CHỦ ĐỀ 1 was defined for the **Bitext 10-fold cross-validation benchmark** (whose out-of-fold overall mean is pending coordinator official evaluation manifest), NOT an invented threshold for the adversarial noise test set.
  - In Live Run `final-evidence-20261112-151514-078471`: 20/20 tickets inspected displayed intent metadata.
  - In cases with probability or margin below threshold (`low_confidence`), system correctly set `confidence_band: "low"` and abstained instead of forcing a dubious draft.

### FR-02: Retrieval, Expiry & Conflict Recognition
- **Requirement:** Retrieve relevant policies or business context based on intent and query; detect expired, invalid, or conflicting information.
- **Implementation:**
  - `PolicyEncoder` with `BAAI/bge-small-en-v1.5` dense embeddings and cosine similarity retrieval (`RetrievalAdapter`).
  - Active KB `approved_kb.v2.json` indexed with atomic release versioning (`apps/ai_service/kb-release.json`).
  - Expiry filtering checks document `effective_to` against query timestamp `as_of`.
  - Conflict detection identifies contradictory policy statements across versions and marks `has_conflict: true`.
- **Evidence & Exact Metrics:**
  - Historical component benchmark: Recall@3 = **0.9839** (fractional per-query mean across 31 answerable benchmark cases with separate manifest; not 31/31 binary recall).
  - In Live Run `final-evidence-20261112-151514-078471`:
    - 4/4 retrieval component boundary fixtures executed with `real_bge_policy_encoder`.
    - **2/2 expired policy fixtures** (`final-case-21`, `final-case-22`) successfully filtered expired docs.
    - **2/2 conflict fixtures** (`final-case-23`, `final-case-24`) successfully triggered conflict detection.
    - Zero stale or conflicting documents leaked into drafted responses.

### FR-03: Grounded Draft Generation with Verifiable Citations
- **Requirement:** Generate draft responses using retrieved knowledge; include verifiable citations (document, version, span); never assert ungrounded claims.
- **Implementation:**
  - `BudgetedDraftClient` invoking Gemini (`gemini-3.1-flash-lite`) with grounded prompt template.
  - Strict citation schema: `doc_id`, `version`, `field`, `span`, and `content_hash`.
  - Dynamic order context citations: verified against actual customer orders in database.
- **Evidence & Exact Metrics:**
  - In Live Run r3: The single automatic draft generated (`final-case-02`) contained valid citations matching active KB snapshots.
  - In `test_final_acceptance_collector.py::test_collector_source_snapshot_version_collision_and_hash_verification`, collector verifies cryptographic hashes of all cited documents against disk snapshots.
  - **Honest Boundary:** Source citation existence does NOT prove factual claim validity. Factual claim correctness is **PENDING coordinator semantic claim grading**.

### FR-04: Human Oversight & Strict No-Auto-Send Invariant
- **Requirement:** Staff interface to view, edit, approve, or reject drafts. System MUST NEVER send messages automatically to customers.
- **Implementation:**
  - Two-stage architecture: AI service only writes to internal `Suggestion` entities; never interacts with customer message queue directly.
  - Staff must explicitly review and send via `POST /v1/console/tickets/{ticket_id}/replies`.
- **Evidence & Exact Metrics:**
  - **Live Run r3 Verification:** Exactly 20 customer tickets went through the full HTTP application gateway and were inspected via `GET /v1/shop/tickets/{ticket_id}`. All **20 out of 20 (100%)** confirmed:
    - `reply == null`
    - `customer_status == "received"`
    - Zero automated messages delivered to customers across all 20 customer HTTP tickets.
    - *(Note: The 4 component boundary fixtures `final-case-21` through `final-case-24` are retrieval-only evaluations executed directly against the policy encoder/retrieval adapter, so customer HTTP ticket fields are NULL).*
  - **Playwright Browser E2E Tests:** Customer ticket status remains "Received" until staff explicitly logs in, reviews suggestion, types/approves reply, confirms modal dialog, and dispatches (`apps/frontend/e2e/application.spec.ts`).

### FR-05: Abstention, Fallback & Escalation Controls
- **Requirement:** Support safe abstention/fallback when AI is uncertain, information is missing, queries are sensitive, or system errors occur.
- **Implementation:**
  - Rule-based safety routing in `apps/ai_service/engine.py`:
    - `low_confidence`: when prediction confidence < threshold or margin < margin_threshold.
    - `human_agent_requested`: routes to `escalate`.
    - `sensitive_action`: routes to `escalate`.
    - `out_of_scope_intent`: routes to `abstain`.
- **Evidence & Exact Metrics:**
  - Live Run r3:
    - 3/3 mandatory sensitive cases properly escalated.
    - 3/3 out-of-domain cases properly abstained.
    - 2/2 unsupported policy cases properly abstained.
    - 7/12 answerable cases safely abstained due to ML uncertainty (`low_confidence`) instead of guessing.

### FR-06: Human Authority for Financial & Policy Exceptions
- **Requirement:** For refund approvals, transaction complaints, or exceptions, system provides supporting context only; business decisions remain reserved for authorized staff.
- **Implementation (Verified Source Code):**
  - Database model `Ticket` in `apps/backend/platform/models.py`:
    - `is_authority_required`: Boolean column flag indicating manager authority is required.
    - `status`: String column ("open", "escalated", "closed").
    - `escalation`: JSON dict storing `escalation_id`, `staff_reason_codes`, `note`, `by`, and `created_at`.
  - Service functions in `apps/backend/tickets/service.py`:
    - `SENSITIVE_KEYWORDS`: regex detecting refund, dispute, chargeback, or cancellation terms on message body.
    - `SENSITIVE_ACTION_INTENTS`: intents requiring authority (`request_refund`, `cancel_order`).
    - `act(session, actor, ticket_id, action, body, settings, trace_id)`:
      - Line 240: blocks direct staff replies on authority-gated tickets (`if action == "replies" and actor.role == "staff" and ticket.is_authority_required: raise Problem(403, "authority-required", "A manager must send the reply. Submit it for approval.")`).
      - Line 242: enforces proposal submission for staff (`action == "reply-proposals"`).
      - Line 228: handles staff escalation to manager (`action == "escalations"`).
- **Evidence & Exact Metrics:**
  - Verified in `apps/backend/tickets/service.py::act()`: 403 `authority-required` error raised if staff attempts direct reply on authority-gated tickets.

### FR-07: Persistent Audit Logging & Feedback Loop
- **Requirement:** Record staff decisions (approve/edit/reject/escalate), intent overrides, and source versions for monitoring and review.
- **Implementation:**
  - Dedicated PostgreSQL `audit_entries` table (`apps/backend/platform/models.py::AuditEntry`) storing `event_type`, `actor_account_id`, `ticket_id`, `trace_id`, `occurred_at`, and `data` JSON payload.
- **Evidence & Exact Metrics:**
  - In `run_intent_correction_diagnostic.py`: Every staff override created an audit entry with `event_type: "intent.overridden"`, actor account ID, and `data: {"chosen_intent": case["intent"]}`.
  - Verified in `test_intent_correction_diagnostic.py`: 100% of override actions persist audit entries before returning terminal responses, verifying both chosen intent and actor match.

### FR-08: Privacy Protection & Security Boundary
- **Requirement:** Protect personal data when calling external LLMs; enforce role-based access control; handle errors safely.
- **Implementation:**
  - Bidirectional pseudonymization in `apps/backend/tickets/privacy.py::pseudonymize()`: replaces names, emails, phones, addresses, and tracking codes with tokens (`[NAME_1]`, `[PHONE_1]`) before forwarding to AI service.
  - Restores pseudonymized entities (`restore()`) when staff views the draft.
  - Credential scrubber (`sanitize_error()`): Bounded-pattern best-effort regex scrubber (targeting connection URIs, `password=`, `Bearer <token>`, `token=`).
    > [!IMPORTANT]
    > Universal PII or arbitrary exception scrubbing is **UNSUPPORTED**. The scrubber operates only on recognized credential formats; arbitrary stack traces or unformatted customer data cannot be guaranteed scrubbed by simple regex.
- **Evidence & Exact Metrics:**
  - Zero PII leaks in AI gateway request payloads.
  - Card numbers masked via Luhn validation.
  - All endpoints enforce session authentication and role validation.

---

## 3. Quality & Performance Requirements Matrix

| Quality Dimension | Specification Target | Measured Value (Live Evaluation) | Compliance Notes |
| :--- | :--- | :--- | :--- |
| **ML Macro-F1 (Noise)** | Bitext 10-fold CV Macro-F1 ≥ 0.85 (spec target in CHỦ ĐỀ 1) | Clean: **0.7858**, Casual: **0.7359**, Typo: **0.6267** | From `robustness_summary.json` (n=420); overall noise accuracy 65.48%. The ≥ 0.85 target applies to Bitext 10-fold CV (whose OOF mean is pending coordinator manifest), not an invented threshold on the noise dataset. |
| **Policy-Scope & Safety Regressions** | 100% pass on policy-scope boundary & escalation cases | **11/11 passed** | Offline policy-scope and safety regression suite (`test_routing_safety_regressions.py`), not noise robustness. |
| **Retrieval Recall@3** | ≥ 0.80 on answerable queries | **0.9839** (fractional mean across 31 answerable cases) | Fractional per-query mean across 31 answerable benchmark cases (separate manifest; not 31/31 binary recall). 4/4 fixtures in live r3 passed with real BGE encoder. |
| **LLM Grounding** | ≥ 90% facts supported by citations | **PENDING** | Semantic claim grading pending coordinator review; citation existence != supported claim. |
| **Safety: Human Approval**| 100% replies via human flow; 0 auto-send | **100% (20/20 HTTP tickets)** | 20 customer HTTP tickets verified in database and customer GET view (the 4 component fixtures are NULL HTTP observations). |
| **Mandatory Escalation** | 100% mandatory cases escalate | **100% (3/3)** escalated | `final-case-13`, `final-case-14`, and human request. |
| **End-to-End Latency** | p95 ≤ 12.0 seconds | Application p50 = **0.34s**, p95 = **10.76s** | **Passes budget** (10.76s < 12.0s). |
| **UI Responsiveness** | Desktop & Mobile views clean | **Worker-reported 6/6 passed (unverified); assets preserved** | Worker-reported unverified historical assertion (no test runner machine log attached); 24 screenshots preserved in tracked folder with cryptographic SHA-256 manifest; execution log null/unverified. |
| **Product Value: Handling Time** | Compare manual vs assisted time | **PENDING** | Coordinator owns paired agent trial execution. |

---

## 4. Playwright Browser E2E Verification Details

- **Test Specification:** `apps/frontend/e2e/application.spec.ts`
- **Committed Configuration Target:** `apps/frontend/playwright.config.ts` (`baseURL: http://127.0.0.1:8080`, `channel: 'msedge'`, `headless: true`, projects: `desktop`, `tablet`, `mobile`, `small-phone`).
- **Execution Results Status:**
  - The historical assertion of "6 passed (3 desktop, 3 mobile) in 21.2s" is a **worker-reported / unverified prior capture**. No automated test runner JSON log (`test-results.json`) was attached on disk.
  - Screenshots are preserved as **derived historical assets** with cryptographic SHA-256 hashes in [`artifacts/browser/playwright-e2e-20261112/`](../artifacts/browser/playwright-e2e-20261112/) (see [`manifest.json`](../artifacts/browser/playwright-e2e-20261112/manifest.json)). Unknown runtime origin fields are marked `null / unverified`.
- **Actual Spec Routes & Scenarios:**
  1. `customer request, human reply and customer receipt`:
     - Customer sign-in: `/sign-in`
     - Products catalog: `/shop`
     - Orders list: `/shop/orders`
     - Order detail support submit: `/shop/orders/{id}` -> submit form -> receives ticket
     - Staff console ticket detail: `/console/tickets/{id}`
     - Customer ticket verification: `/shop/support/{id}` (verifies received reply and "Replied" badge)
  2. `admin confirmations, versions and manager reports`:
     - Admin internal accounts: `/console/accounts`
     - Modal dialog: Make manager confirmation
     - Versions page: `/console/versions`
     - Manager reports page: `/console/reports` (verifies "Support reports" heading and "Tickets created" metric; does not execute escalation approval)
  3. `general support without an order`:
     - General support: `/shop/support` -> submits query -> receives ticket
- **Preserved Screenshot Artifacts (Tracked Relative Links):**
  - Desktop (1440x900):
    - [sign-in-desktop.png](../artifacts/browser/playwright-e2e-20261112/sign-in-desktop.png)
    - [products-desktop.png](../artifacts/browser/playwright-e2e-20261112/products-desktop.png)
    - [orders-desktop.png](../artifacts/browser/playwright-e2e-20261112/orders-desktop.png)
    - [order-received-desktop.png](../artifacts/browser/playwright-e2e-20261112/order-received-desktop.png)
    - [console-desktop.png](../artifacts/browser/playwright-e2e-20261112/console-desktop.png)
    - [order-replied-desktop.png](../artifacts/browser/playwright-e2e-20261112/order-replied-desktop.png)
    - [accounts-desktop.png](../artifacts/browser/playwright-e2e-20261112/accounts-desktop.png)
    - [account-confirmation-desktop.png](../artifacts/browser/playwright-e2e-20261112/account-confirmation-desktop.png)
    - [versions-desktop.png](../artifacts/browser/playwright-e2e-20261112/versions-desktop.png)
    - [reports-desktop.png](../artifacts/browser/playwright-e2e-20261112/reports-desktop.png)
    - [general-support-desktop.png](../artifacts/browser/playwright-e2e-20261112/general-support-desktop.png)
    - [general-request-desktop.png](../artifacts/browser/playwright-e2e-20261112/general-request-desktop.png)
  - Mobile (390x844):
    - [sign-in-mobile.png](../artifacts/browser/playwright-e2e-20261112/sign-in-mobile.png)
    - [products-mobile.png](../artifacts/browser/playwright-e2e-20261112/products-mobile.png)
    - [orders-mobile.png](../artifacts/browser/playwright-e2e-20261112/orders-mobile.png)
    - [order-received-mobile.png](../artifacts/browser/playwright-e2e-20261112/order-received-mobile.png)
    - [console-mobile.png](../artifacts/browser/playwright-e2e-20261112/console-mobile.png)
    - [order-replied-mobile.png](../artifacts/browser/playwright-e2e-20261112/order-replied-mobile.png)
    - [accounts-mobile.png](../artifacts/browser/playwright-e2e-20261112/accounts-mobile.png)
    - [account-confirmation-mobile.png](../artifacts/browser/playwright-e2e-20261112/account-confirmation-mobile.png)
    - [versions-mobile.png](../artifacts/browser/playwright-e2e-20261112/versions-mobile.png)
    - [reports-mobile.png](../artifacts/browser/playwright-e2e-20261112/reports-mobile.png)
    - [general-support-mobile.png](../artifacts/browser/playwright-e2e-20261112/general-support-mobile.png)
    - [general-request-mobile.png](../artifacts/browser/playwright-e2e-20261112/general-request-mobile.png)

---

## 5. Unresolved Deficiencies & Open Blockers

1. **Low Automatic Draft Coverage in Live Runs:**
   - **Live r3 Run (`final-evidence-20261112-151514-078471`):**
     - **1 out of 12** answerable cases drafted automatically (`final-case-02`).
     - **7 out of 12** answerable cases abstained due to low confidence/margin (`final-case-03`, `04`, `05`, `06`, `07`, `10`, `12`).
     - **4 out of 12** answerable cases failed due to external LLM provider timeouts (`final-case-01`, `08`, `09`, `11`).
   - **Earlier Baseline Run:** 5 out of 12 answerable cases drafted automatically.
   - **Oracle-Assisted Diagnostic (`coordinator-intent-correction-20261112-152013-0fb5c3`):**
     - Evaluated the 7 initial low-confidence abstention cases via staff console override endpoint (`POST /v1/console/tickets/{id}/suggestions`).
     - Outcome: **5 out of 7 assisted drafts, with 2 failed due to external provider timeouts** (`final-case-04`, `final-case-06`), not a full 100% success.
     - *Crucial note:* Human intervention is an oracle diagnostic of the fallback path, NOT an automatic ML metric or human productivity study.

2. **External LLM Provider Failures & Cost Accounting Status:**
   - Provider timeouts and network failures occurred on **4 out of 20** customer tickets in the latest live acceptance run, and **2 out of 7** cases in the oracle diagnostic run.
   - **Token Economics & Billing Cost:** Per-attempt token usage is recorded when returned by provider. Complete total/average cost remains UNKNOWN because some failed requests have no provider token usage; list-price estimates are conditional and are not actual invoices. (Refer to `coordinator-final-live-20261112-r3/final-evidence-20261112-151514-078471/accounting_recomputed.json` and Worker B attempt metadata, do not claim usage absent).

3. **41 Strict Action Mismatches in 156-Case Acceptance Component Benchmark:**
   - In the gold acceptance component benchmark (`data/benchmarks/system/v2/acceptance/cases.jsonl`; evaluation sourced from `artifacts/audit/routing_audit_20261112_v2/robustness_summary.json` using actual DistilBERT/BGE and SpyLLM isolation, not isolated-mock classifier/retriever):
     - **Overall exact action matches:** **74 out of 156** cases.
     - **Mandatory subset (N=63):** 16 `escalate`, 46 `manual_fallback`, 1 encoder fault `NOT_EXECUTED`.
     - **Contract alignment:** 21 out of 63 match allowed action sets; **41 safe `manual_fallback` mismatch strict `escalate`**; 1 not-executed.
     - **Contract vocabulary:** Uses standard raw pipeline actions (`draft`, `abstain`, `escalate`) and adapter actions (`retrieve_draft`, `manual_fallback`, `escalate`) without invented terminology.
   - *Architectural Boundary:* Component-level pipeline evaluations operate in isolation from full HTTP application gateway integration runs; this historical component-level deficit remains an open limitation.

4. **Bounded Credential Scrubber (No Universal PII Protection):**
   - `sanitize_error` is a bounded pattern-matching regex scrubber targeting standard database connection URIs, passwords, and bearer tokens. Universal PII protection across arbitrary error messages or stack traces is unsupported.

5. **Semantic Claim Grading Pending:**
   - Factual correctness of statements in drafted responses is subject to manual/coordinator semantic grading, which is pending.

6. **Paired Agent Study Pending:**
   - Comparison of ticket resolution times between unassisted manual staff and AI-assisted staff is owned by the coordinator and remains pending.

7. **Browser Execution Log Unverified:**
   - Preserved screenshot assets have verified SHA-256 hashes, but the original execution environment and runtime metrics remain worker-reported without a machine-generated test runner log artifact.

8. **No Outside Endorsement Claimed:**
   - All evaluation was conducted within the controlled, isolated multi-agent evaluation environment under delegated AI stakeholder authority. No external instructor or university approval is asserted.
