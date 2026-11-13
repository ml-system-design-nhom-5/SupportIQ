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

4. **Tier 4: Browser Evidence Assets & Fresh Isolated E2E Execution**:
   - **Fresh Isolated Browser Execution (Post-Fix Verified):** [`artifacts/browser/playwright-e2e-20261113-verified/`](../artifacts/browser/playwright-e2e-20261113-verified/) with machine-generated [`manifest.json`](../artifacts/browser/playwright-e2e-20261113-verified/manifest.json), [`report.json`](../artifacts/browser/playwright-e2e-20261113-verified/report.json), [`playwright.log`](../artifacts/browser/playwright-e2e-20261113-verified/playwright.log), and **48/48** SHA-256 verified screenshots across 4 viewports (`12/12` passed at commit `49fa441`, **controlled mock AI boundary** via `EphemeralMockAIGateway`, `external_provider_calls: 0`).
   - **Tablet UI Defect Red/Green Provenance:** Preserved pre-fix failing captures in [`artifacts/browser/playwright-e2e-20261113/`](../artifacts/browser/playwright-e2e-20261113/) and [`artifacts/browser/playwright-e2e-20261113-repro/`](../artifacts/browser/playwright-e2e-20261113-repro/) (`11/12` passed, tablet `.source-row` WCAG `target-size` failure) plus focused tablet recheck [`artifacts/browser/playwright-e2e-20261113-tablet-recheck/`](../artifacts/browser/playwright-e2e-20261113-tablet-recheck/) (`1/1`, `6/6` screenshots).
   - **Derived Historical Browser Catalog:** Preserved in tracked directory [`artifacts/browser/playwright-e2e-20261112/`](../artifacts/browser/playwright-e2e-20261112/) with cryptographic SHA-256 manifest [`manifest.json`](../artifacts/browser/playwright-e2e-20261112/manifest.json) (24 screenshots copied from `.impeccable/review/`; runtime execution log is unverified / null; execution metrics worker-reported unverified).

---

## 1. Executive Summary & Status Overview

| Dimension | Specification Target (CHỦ ĐỀ 1) | Actual Verified Result | Status |
| :--- | :--- | :--- | :--- |
| **FR-01: Intent Classification** | Single-label 46 intents, 12 in-scope; Bitext 10-fold CV Macro-F1 ≥ 0.85 target; confidence display | Real noise F1: clean **0.7858**, casual **0.7359**, typo **0.6267** (Bitext 10-fold CV OOF mean pending coordinator manifest); confidence metadata displayed in console | **PARTIAL / PENDING OOF** |
| **FR-02: Policy Retrieval & Boundary Checks** | Recall@3 ≥ 0.80; detect expired / conflicting policies | Historical benchmark Recall@3 = **0.9839** (fractional per-query mean across 31 answerable cases); live r3 4/4 fixtures verified with real BGE encoder (2/2 expired filtered, 2/2 conflict detected) | **PASS** |
| **FR-03: Grounded Draft Generation** | LLM draft with verifiable citations, no ungrounded claims | **21/22 (95.45%)** semantic propositions supported across 6 emitted drafts (1 automatic + 5 oracle-assisted; 5 approve, 1 edit for unresolved public hotline `[PHONE_OR_NUMBER]`, 0 reject) via coordinator review [`semantic_claim_review.json`](../artifacts/evaluation/coordinator-ai-review-20261112/semantic_claim_review.json); **live whole-system AI acceptance still fails** due to 1/12 automatic live draft rate, 4/20 provider timeouts, and open `[PHONE_OR_NUMBER]` hotline defect | **PARTIAL / REVIEWED (21/22 SAMPLE; WHOLE-SYSTEM FAIL)** |
| **FR-04: Human Oversight & No-Auto-Send** | Staff review/edit/send; strictly NO automated sending | **20/20 (100%)** customer HTTP tickets verified with `reply: null` and `customer_status: "received"` (the 4 component fixtures are retrieval-only and have NULL customer HTTP fields); zero automated sends | **PASS** |
| **FR-05: Abstention, Fallback & Escalation** | Safe fallback on uncertainty, missing info, errors | Low confidence abstains; sensitive requests escalate; system errors fail closed without hallucinations | **PASS** |
| **FR-06: Human Authority for Sensitive Actions** | Refund/financial exceptions require manager authority | `Ticket.is_authority_required: true` enforced on sensitive keywords/intents; staff direct reply blocked (403 `authority-required`) | **PASS** |
| **FR-07: Audit Logging & Traceability** | Log staff decisions, overrides, source versions | Immutable `AuditEntry` records in PostgreSQL for `intent.overridden`, `message.pseudonymized`, `ticket.escalated`, `reply.sent` | **PASS** |
| **FR-08: Data Privacy & Error Handling** | PII pseudonymization; RBAC; secure API boundaries | Bidirectional pseudonymization (`pseudonymize()`); RBAC enforced; bounded regex scrubbing (`sanitize_error()`; universal PII scrubbing unsupported) | **BOUNDED BEST-EFFORT** |
| **Latency: p95 Budget** | p95 latency ≤ 12.0 seconds | Live r3 Application p50 = **338.47 ms**, p95 = **10,757.08 ms** (10.76s ≤ 12.0s target) | **PASS** |
| **Live Automatic Draft Coverage** | 12/12 product answerable cases draft automatically | Live r3: **1/12 drafted** (**0/12** both correct-intent AND `draft_ready`; `final-case-02` predicted `return_policy` != `return_product`), **7/12 abstained**, **4/12 provider timed out**; frozen Serving pre-LLM draft eligibility **5/12 raw / 4/12 correct-intent** on `final_acceptance` and **21/34 raw / 17/34 correct-intent** on `system_acceptance` ([`BASELINE_FREEZE_REPORT.md`](../artifacts/evaluation/independent_baseline_20261113/BASELINE_FREEZE_REPORT.md)). Worker A first candidate (`4cb07f4`, `1fc2d1b1...`) **REJECTED** ([`classifier_gate_task_a_first_20261113/`](../artifacts/evaluation/classifier_gate_task_a_first_20261113/CLASSIFIER_GATE_REPORT.md)) and followup candidate (`32e9781`, `b9e500b2...`) **REJECTED** (`1/80` `ml_oos_80` leak `oos-multi_intent-02`, conservative `15/34` `system_acceptance` correct-intent draftable, `promotion_approved: false`; [`CLASSIFIER_GATE_REPORT.md`](../artifacts/evaluation/classifier_gate_task_a_followup_20261113/CLASSIFIER_GATE_REPORT.md)); Serving unchanged | **DEFICIENT / CANDIDATES REJECTED (SERVING UNCHANGED)** |
| **External LLM Reliability & Cost** | Reliable generation within budget | Controlled mock resilience (`18` schedules, 0 live calls): `ff0e147` improves `4/9 -> 6/9` with wait-inclusive latency & hard-quota fail-fast ([`BEFORE_AFTER_COMPARISON.md`](../artifacts/evaluation/provider_resilience_ff0e147_20261113/BEFORE_AFTER_COMPARISON.md)). Bounded live oracle-intent component check (`ff0e147`, `8/8` HTTP calls / `4` cases, `0` secrets logged): **`2/4` recovered (`final-case-10` policy-supported, `final-case-12` conditional payment guidance; oracle component boundary only)**, `2/4` fell closed (`llm_timeout`), `no_auto_send_all=True`, interpolated median **`8.26355s`** (vs `9.9265s` index `len//2`, tiny-sample `n=4` `p95=max=10.1452s`), `incomplete_token_coverage` (`6/8` attempts missing usage; complete cost `null`), recomputed conditional USD **`$0.0012365`** at verified `$0.25/$1.50` incl. thinking (old `$0.075/$0.30` -> `$0.00033345` retained for history) ([`accounting_recomputed.json`](../artifacts/evaluation/live_ff0e147_oracle_20261113/accounting_recomputed.json)) | **VERIFIED BOUNDED COMPONENT (`ff0e147` `2/4` LIVE); LIVE ACCEPTANCE OPEN** |
| **Staff Intent Override Diagnostic** | Recover low-confidence cases via human-in-the-loop | **5/7 assisted drafts**, **2 failed (provider timeouts)**; 7/7 no-auto-send; 7/7 audit logs | **5/7 DRAFTS, 2 TIMEOUTS** (Diagnostic only, not full success) |
| **Component Benchmark Action Routing** | Component-level strict routing contract | N=156: **74/156** exact matches; within mandatory N=63: 21/63 allowed, **41 safe manual_fallback mismatch strict escalate**, 1 encoder fault not-executed (`data/benchmarks/system/v2/acceptance/cases.jsonl`) | **74/156 MATCHES; MANDATORY 21/63 MATCHES (Component Boundary)** |
| **UI Responsiveness (Browser E2E)** | Desktop (1440x900), Tablet (768x1024), Mobile (390x844), Small-Phone (360x800) clean layout & WCAG 2.2 AA | **12/12 passed** (`48/48` screenshots + SHA-256 + `report.json` + `playwright.log`) against actual `apps/frontend/dist` + FastAPI `create_app` + isolated ephemeral PG schema + **controlled mock AI boundary** (`EphemeralMockAIGateway`, `llm_unavailable`, `external_provider_calls: 0`) after fixing tablet `.reply-panel` / `.source-row` overlap (`f5de616`); historical [`playwright-e2e-20261112/`](../artifacts/browser/playwright-e2e-20261112/) preserved as unverified assets | **VERIFIED (MOCK AI BOUNDARY)** |
| **Paired Agent Study & Semantic Grading** | Measure assisted vs manual time; semantic grading | **12 paired AI cases completed** (`0` human participants; [`summary.json`](../artifacts/evaluation/coordinator-paired-ai-20261112/summary.json)): mean **8.974584s** manual vs **8.970244s** assisted (median 7.747585s vs 8.171049s; 5 approve, 1 edit, 6 manual fallback) — **no demonstrated productivity gain**; semantic grading **21/22 (95.45%)** | **COMPLETE (NO GAIN SHOWN)** |

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
  - **Semantic Claim Grading & Honest Boundary:** Coordinator proposition-level grading ([`semantic_claim_review.json`](../artifacts/evaluation/coordinator-ai-review-20261112/semantic_claim_review.json)) scored **21/22 (95.45%)** grouped verification units supported across 6 emitted drafts (1 automatic live draft + 5 oracle-assisted drafts; 5 approve, 1 edit, 0 reject). One proposition failed because the draft retained an unresolved placeholder/public hotline reference (`[PHONE_OR_NUMBER]`, open defect). Because only 1/12 live non-escalated tickets received an automatic draft and 4/20 provider calls timed out, sample claim grading passes the 90% proposition threshold (`sample_threshold_met: true`) while whole-system live AI acceptance remains **FAIL** (`whole_system_acceptance: false`). Source citation existence does NOT prove factual claim validity, and fresh browser E2E used a controlled mock AI boundary rather than live ML output.

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
| **LLM Grounding** | ≥ 90% facts supported by citations | **21/22 (95.45%)** sample props; **WHOLE-SYSTEM FAIL** | Coordinator review of 6 emitted drafts (1 auto + 5 oracle-assisted): 5 approve, 1 edit (`[PHONE_OR_NUMBER]` hotline defect), 0 reject. Live coverage remains only 1/12 auto-drafted. |
| **Safety: Human Approval**| 100% replies via human flow; 0 auto-send | **100% (20/20 HTTP tickets)** | 20 customer HTTP tickets verified in database and customer GET view (the 4 component fixtures are NULL HTTP observations). |
| **Mandatory Escalation** | 100% mandatory cases escalate | **100% (3/3)** escalated | `final-case-13`, `final-case-14`, and human request. |
| **End-to-End Latency** | p95 ≤ 12.0 seconds | Application p50 = **0.34s**, p95 = **10.76s** | **Passes budget** (10.76s < 12.0s). |
| **UI Responsiveness** | Desktop, Tablet, Mobile, Small-Phone clean + axe WCAG 2.2 AA | **12/12 passed (Mock AI boundary)** | Fresh isolated run [`playwright-e2e-20261113-verified/`](../artifacts/browser/playwright-e2e-20261113-verified/) on commit `49fa441`: `48/48` screenshots, `report.json`, `playwright.log`, SHA-256 manifest, `external_provider_calls: 0`. Historical [`playwright-e2e-20261112/`](../artifacts/browser/playwright-e2e-20261112/) kept as derived unverified assets. |
| **Product Value: Handling Time** | Compare manual vs assisted time | **No demonstrated productivity gain** | 12 paired AI cases (`0` human participants; [`summary.json`](../artifacts/evaluation/coordinator-paired-ai-20261112/summary.json)): mean manual **8.974584s** vs assisted **8.970244s** (`-0.004340s`; median 7.747585s vs 8.171049s; 5 approve, 1 edit, 6 manual fallback). |

---

## 4. Playwright Browser E2E Verification Details

### 4.1 Fresh Isolated Browser Execution (`playwright-e2e-20261113-verified/`) — Mock AI Boundary
- **Test Specification & Config:** `apps/frontend/e2e/application.spec.ts` (`apps/frontend/playwright.config.ts`: `channel: 'msedge'`, `headless: true`, projects: `desktop` 1440x900, `tablet` 768x1024, `mobile` 390x844, `small-phone` 360x800).
- **Status:** **Verified Fresh Execution — 12/12 passed, 0 failed, 0 skipped, 0 flaky** (controlled mock AI boundary).
- **Commit, Version & Timing:**
  - Commit: `49fa441d8a56a1c8efcc0fc8a1266ab6fa54db39`
  - Started / Created: `2026-11-13T01:39:36.752773+00:00` -> `2026-11-13T01:40:48.636676+00:00`
  - Playwright Version: `Version 1.64.1` (`channel: "msedge"`, `headless: true`)
  - Duration: `61.72s` Playwright execution (`61165.23ms` reporter stats), `71.88s` total isolated pipeline
- **Actual Command & Isolated Ports/Schema:**
  - Command: `C:\Users\PC\AppData\Local\pnpm\bin\pnpm.CMD --dir C:\Users\PC\orca\workspaces\SupportIQ\supportiq-final-evidence\apps\frontend exec playwright test --reporter=json,list`
  - Backend: FastAPI `create_app` serving built `apps/frontend/dist` at `http://127.0.0.1:8089`
  - Database: Owned ephemeral PostgreSQL cluster at `127.0.0.1:55500`, isolated random schema `browser_e2e_e61b5e789a` (dropped + temp cluster removed on teardown), temporary synthetic worker credentials (restored on teardown)
  - AI Service: Owned loopback `EphemeralMockAIGateway` at `http://127.0.0.1:49272` (`llm_unavailable`, `external_provider_calls: 0`)
- **Machine Reporter & SHA-256 Artifacts:**
  - [`report.json`](../artifacts/browser/playwright-e2e-20261113-verified/report.json) (SHA-256: `2f310458903fde52782f031380ed8d70ab612b9faab4b2f58059811cf53ebeda`)
  - [`playwright.log`](../artifacts/browser/playwright-e2e-20261113-verified/playwright.log) (SHA-256: `d2273a6c7f1591ba7ce83c68dd55655a502252cd49559d29394e9ba67a4ff05b`)
  - [`manifest.json`](../artifacts/browser/playwright-e2e-20261113-verified/manifest.json) (**48/48** SHA-256 verified PNG screenshots: 12 screens x 4 viewports)
- **Actual Spec Routes, Verified Flows & Explicit Mock-AI Boundary:**
  1. `customer request, human reply and customer receipt`: `/sign-in` -> `/shop` -> `/shop/orders` -> `/shop/orders/{id}` -> `/console/tickets/{id}` (explicit staff reply) -> `/shop/support/{id}` (`Replied` badge).
  2. `admin confirmations, versions and manager reports`: `/console/accounts` -> confirmation modal cancellation -> `/console/versions` -> `/console/reports` ("Support reports" heading and "Tickets created" metric; does **not** exercise manager escalation approval).
  3. `general support without an order`: `/shop/support` -> submits general query -> receives ticket.
  4. Automated checks per page (`checkPage` helper): `scrollWidth <= innerWidth` horizontal overflow check + `@axe-core/playwright` WCAG 2.0/2.1/2.2 AA (`wcag2a`, `wcag2aa`, `wcag21a`, `wcag21aa`, `wcag22aa`).
  - **Mock AI Boundary (NOT Live ML/LLM Acceptance):** `EphemeralMockAIGateway` returns `llm_unavailable` fallback states with `external_provider_calls: 0`; this proves real built frontend/backend/DB/browser/accessibility/manual-reply integration, **not** live ML/LLM draft acceptance, factual AI claim support, or manager escalation approval.

### 4.2 Tablet UI Defect Red/Green Provenance
- **Red Pre-Fix Evidence (Preserved Untouched):** [`artifacts/browser/playwright-e2e-20261113/`](../artifacts/browser/playwright-e2e-20261113/) and [`artifacts/browser/playwright-e2e-20261113-repro/`](../artifacts/browser/playwright-e2e-20261113-repro/) (commit `8c8e5e1`, `11/12` passed, `1` failed, `47/48` screenshots, missing `order-replied-tablet.png`) failed `[tablet] › e2e/application.spec.ts:30:1` on axe WCAG 2.2 AA `target-size` (`wcag22aa`, `wcag258`) for `<button class="source-row">` because `.reply-panel` retained `flex: 1 0 360px` under `@media (max-width: 1000px)` with `.panel { overflow: hidden }`, allowing `#reply-body` to overlap `.source-row` (smallest unobstructed space `470px x 2.7px < 24x24px`).
- **Fix & Focused Verification:** Commit `f5de616` changed `.reply-panel` in `apps/frontend/src/styles.css` from `flex: 1 0 360px` to `flex: 1 0 auto`, rebuilt `apps/frontend/dist`, passed Vitest (`4/4` files, `18/18` tests), passed `impeccable detect` (`[]`) and `design-taste-frontend` lint (`0 FAIL, 3 WARN`), passed focused tablet recheck [`artifacts/browser/playwright-e2e-20261113-tablet-recheck/`](../artifacts/browser/playwright-e2e-20261113-tablet-recheck/) (`1/1`, `6/6` screenshots), and passed all `12/12` tests in [`playwright-e2e-20261113-verified/`](../artifacts/browser/playwright-e20261113-verified/).

### 4.3 Derived Historical Browser Assets (`playwright-e2e-20261112/`)
- Preserved in [`artifacts/browser/playwright-e2e-20261112/`](../artifacts/browser/playwright-e2e-20261112/) (24 screenshots copied from `.impeccable/review/` across `desktop` and `mobile`/`tablet`/`small-phone` cataloged in [`manifest.json`](../artifacts/browser/playwright-e2e-20261112/manifest.json); `raw_test_results_log_attached: false`, worker-reported historical assertion preserved as unverified provenance).

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

5. **Semantic Claim Grading & Unresolved Public Hotline Defect:**
   - Coordinator proposition-level grading ([`semantic_claim_review.json`](../artifacts/evaluation/coordinator-ai-review-20261112/semantic_claim_review.json)) evaluated 6 emitted drafts (1 automatic + 5 oracle-assisted) and scored **21/22 (95.45%)** verification units supported (`5 approve`, `1 edit`, `0 reject`), with one failure due to an unresolved `[PHONE_OR_NUMBER]` hotline placeholder defect. Sample threshold is met (`sample_threshold_met: true`), while live whole-system AI acceptance remains **FAIL** (`whole_system_acceptance: false`).

6. **Paired AI Timing Exercise Shows No Productivity Gain:**
   - Coordinator 12-case paired AI exercise ([`summary.json`](../artifacts/evaluation/coordinator-paired-ai-20261112/summary.json)) included `0` human participants and observed mean manual handling time **8.974584s** vs assisted **8.970244s** (`-0.004340s`; median `7.747585s` vs `8.171049s`; 5 approve, 1 edit, 6 manual fallback) — **no demonstrated productivity gain**.

7. **Browser E2E Mock AI Boundary & Historical Provenance:**
   - Fresh isolated browser execution ([`playwright-e2e-20261113-verified/`](../artifacts/browser/playwright-e20261113-verified/)) passes **12/12** (`48/48` screenshots, machine `report.json`, `playwright.log`) against actual `apps/frontend/dist` and FastAPI `create_app`, using `EphemeralMockAIGateway` (`llm_unavailable`, `external_provider_calls: 0`). This verifies real UI/API/accessibility integration and manual flows, **not** live ML/LLM draft acceptance, AI factual support, or manager escalation-approval workflow. Historical [`playwright-e2e-20261112/`](../artifacts/browser/playwright-e20261112/) remains preserved as derived unverified screenshot assets (`raw_test_results_log_attached: false`).

8. **No Outside Endorsement Claimed:**
   - All evaluation was conducted within the controlled, isolated multi-agent evaluation environment under delegated AI stakeholder authority. No external instructor or university approval is asserted.

9. **Task C Round 2 — Controlled Provider Resilience (`ff0e147` Latest, `9160ffb` History Preserved) & Missing Classifier Candidate Blocker:**
   - Full raw measurements, checksum freeze, SHA-256 report hashes, and final recommendation are recorded in [`docs/audits/2026-11-13-task-c-independent-evaluation.md`](audits/2026-11-13-task-c-independent-evaluation.md):
     - **Baseline Correct-Intent Recomputation:** [`BASELINE_FREEZE_REPORT.md`](../artifacts/evaluation/independent_baseline_20261113/BASELINE_FREEZE_REPORT.md) establishes Serving `distilbert-supportiq` raw vs correct-intent draft eligibility at **5/12 vs 4/12** (`final_acceptance`), **21/34 vs 17/34** (`system_acceptance` `draft_expected`), and **0/12** both correct-intent and `draft_ready` in live `r3`, with `supportpilot-distilbert` OOD leak verified in `raw_predictions.jsonl` as `oos-multi_intent-07`.
     - **Final Worker B Evaluation (`ff0e147` vs `54fda75`, `18` schedules + 5 edge contracts, 0 live calls):** Final commit `ff0e147` raises controlled transient recovery from **4/9 (44.44%)** to **6/9 (66.67%)**, enforces `latency_includes_retry_waits_all=True` (`18/18` schedules; separated `transport_latency_seconds` + `retry_wait_seconds` in both success output and `LLMError`), passes typed `google.rpc.RetryInfo` (`E02` untyped rejected), hard-quota `429 QuotaFailure` + valid `Retry-After: 1` fail-fast (`E01`, `1` attempt, `0` sleep), malformed injected `retry_after` fail-closed, zero fabricated token totals, and strict `no_auto_send_all=True` ([`BEFORE_AFTER_COMPARISON.md`](../artifacts/evaluation/provider_resilience_ff0e147_20261113/BEFORE_AFTER_COMPARISON.md), [`candidate_edge_contracts.json`](../artifacts/evaluation/provider_resilience_ff0e147_20261113/candidate_edge_contracts.json), [`report_hashes.json`](../artifacts/evaluation/provider_resilience_ff0e147_20261113/report_hashes.json)). **Recommended APPROVE for controlled resilience/accounting** (retaining `trust_env=True` proxy default and deadline-allocation boundary; controlled recovery does **not** prove live external LLM availability). Preserved interim `9160ffb` history remains unchanged in [`provider_resilience_9160ffb_20261113/`](../artifacts/evaluation/provider_resilience_9160ffb_20261113/).
     - **Worker A First Candidate (`4cb07f4`, SHA `1fc2d1b1...`) Independent Gate -> `REJECT`:** Bitext raw/cleaned/splits were recovered from pinned public HuggingFace provenance (`12dd624...`), and `domain_templates.jsonl` passed Task C split-isolation & gold-contamination checks (`PASS`, 0 overlaps/gold matches); however, the candidate failed independent safety gates on `oos_draft_leak` (`2/80` at `T=1.0`, `3/80` at `T=0.75`) and `34_label_regression_system_acceptance` (`0.5897 < 0.6154`), plus mandatory escalation draft leaks (`1 -> 3` at `T=0.75`) ([`CLASSIFIER_GATE_REPORT.md`](../artifacts/evaluation/classifier_gate_task_a_first_20261113/CLASSIFIER_GATE_REPORT.md)).
     - **Worker A Follow-Up Candidate (`32e9781`, SHA `b9e500b2...`, `T=1.0`, `neg_kl=0.75`) Independent Gate -> `REJECT`:** Both `domain_templates.jsonl` (`216`) and `domain_negatives.jsonl` (`90`) passed Task C split-isolation & gold-contamination checks (`0` overlaps vs `1,009` gold prompts), held-out `domain_negatives` scored `27/27 (1.0)` safe (`0` false drafts), `34`-label escalation parity was restored (`0.6520 >= 0.6471` macro-F1), and `final_acceptance` wrong-intent drafts dropped to `0`; however, `ml_oos_80` still leaked **`1/80` (`oos-multi_intent-02`)**, answerable draft coverage became conservative (`15/34` `system_acceptance` correct-intent vs `17/34` Serving; `5/12` `final_acceptance`), legacy top-level provenance keys remain unmapped (`candidate_provenance_manifest.json` SHA-256 verified), and Worker A's own `promotion_approved` is `false` ([`CLASSIFIER_GATE_REPORT.md`](../artifacts/evaluation/classifier_gate_task_a_followup_20261113/CLASSIFIER_GATE_REPORT.md), [`followup_supplement.json`](../artifacts/evaluation/classifier_gate_task_a_followup_20261113/followup_supplement.json)). Serving model `distilbert-supportiq` remains unchanged.

10. **Task C Bounded Live Oracle-Intent Grounded-Provider Component Verification (`ff0e147`, `8/8` HTTP Requests) & Recomputed Accounting:**
    - Authorized per `9b52b31` (`preflight 0/8 -> final 8/8`, `transport_retries_configured=0`, `rejected_before_network=0`, `0` secrets persisted; [`LIVE_VERIFICATION_REPORT.md`](../artifacts/evaluation/live_ff0e147_oracle_20261113/LIVE_VERIFICATION_REPORT.md), [`live_verification.json`](../artifacts/evaluation/live_ff0e147_oracle_20261113/live_verification.json) preserved byte-identical `548a96fd...`, [`accounting_recomputed.json`](../artifacts/evaluation/live_ff0e147_oracle_20261113/accounting_recomputed.json), [`report_hashes.json`](../artifacts/evaluation/live_ff0e147_oracle_20261113/report_hashes.json)).
    - Strictly bounded to **`oracle_intent_grounded_provider_component_verification`** (4 cases: `final-case-02, 03, 10, 12` with `intent_override` and approved KB evidence; **NOT** automatic end-to-end classifier coverage or whole-system live acceptance): under live Gemini `503`/`ReadTimeout` failures (`6/8` attempts), `ff0e147` recovered **`2/4`** (`final-case-10` citing `POL-SHIP-004:1.0`, coordinator review `policy_supported`; `final-case-12` citing `POL-PAY-001:1.0`, coordinator review `conditional_payment_guidance`) and failed closed (`llm_timeout`) on `final-case-02, 03` with `no_auto_send_all=True`.
    - **Latency & Pricing Correction (`accounting_recomputed.json`):** Across `8` HTTP calls / `4` cases (`[6.4771, 6.6006, 9.9265, 10.1452]`), standard interpolated median is **`8.26355s`** (vs `9.9265s` nearest-rank `len//2`; tiny-sample `n=4` `p95` collapses to `max=10.1452s`). Recomputed at verified primary `gemini-3.1-flash-lite` standard paid rates (`$0.25` input / `$1.50` output incl. thinking per 1M via [`gemini-3.1-flash-lite-20261112.json`](../artifacts/evaluation/pricing/gemini-3.1-flash-lite-20261112.json) / `ai.google.dev/gemini-api/docs/pricing`), conditional observed USD is **`$0.0012365`** (`3446` prompt + `250` billable output; legacy unverified `$0.075/$0.30` -> `$0.00033345` retained in audit history), while `complete_cost_known=False` (`complete_cost_usd: null`, `6/8` missing attempt usage, omitted `thoughtsTokenCount` not proof of `0`, account tier/invoice unverified).
