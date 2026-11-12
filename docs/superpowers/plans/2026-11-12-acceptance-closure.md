# SupportIQ Acceptance Closure Implementation Plan

> **For agentic workers:** Execute through Orca Antigravity workers, three backend and one frontend, as explicitly selected by the user. Use applicable debugging, test-driven-development and verification skills. Coordinator reviews and integrates each result.

**Goal:** Close backend acceptance gaps and improve the light interface for routine support work.

**Architecture:** Retain the application API and PostgreSQL, AI gateway and React. Isolate independent changes in four worker worktrees based on coordinator HEAD.

**Tech Stack:** FastAPI, SQLAlchemy/PostgreSQL, Python/pytest, React/TypeScript/Vite, Vitest/Playwright.

**Spec:** `docs/superpowers/specs/2026-11-12-acceptance-closure-design.md`.

## Current integration status

| Task | Evidence and status |
|---|---|
| B1 | Worker `98e6469` + reviewed followup `ff6a0fb` integrated as `0a1caae` + `42936f8`; coordinator PostgreSQL safety/boundary/retry subset: 24 passed. Worker reports broader focused suite 60 passed, 1 skipped. |
| B2 | Work remains isolated in retrieval worker; revised local gold not yet approved. Exploratory results do not certify Recall@3. |
| B3 | Runner/provenance work remains in worker; published model list prices verified separately at `artifacts/evaluation/pricing/gemini-3.1-flash-lite-20261112.json`. No complete final latency/cost acceptance yet. |
| F1 | Worker baseline `04433ec` integrated as `ba43381`; coordinator finished review fixes after repeated provider503. Final 18 frontend tests, production build and 12 Edge E2E passed. Exact route/check scope and visual review in `docs/design/2026-11-12-frontend-usability-notes.md`. |

Task checklists below describe the intended deliverables; this table and linked reports state actual evidence. Entire-plan completion is not implied by a component pass.

## Global constraints

Synthetic data only; explicit human sends; no automatic transactions. Preserve API compatibility and fail-closed provenance. Missing evidence is not_evaluated. No false shared/instructor approval, human study, live execution or pricing claims. No reset or stop of coordinator services. Keep user PPTX files unchanged.

## Review focus

- Chargeback/fraud/exception wording and staff override must not lose authority or receive misleading generic payment advice.
- Citation validity must not conceal unsupported policy generalization.
- Gold must precede retrieval execution and match document versions, not be derived from retrieved results.
- Queued job completion and egress tests must exercise real application boundaries, not only helpers.
- Narrow layouts and error states must leave sources and review actions reachable.

## Task B1 — Backend workflow, authority and privacy

**Owner:** Backend worker 1.
**Files:** `apps/backend/tickets/`, backend application tests, dedicated new safety tests; avoid AI engine/retriever/evaluation/frontend edits.
**Interface:** Existing ticket commands, jobs, allowed_actions, audit and gateway transport. Preserve request/response fields and ownership.

- [ ] Trace FR-04–08; reproduce concrete authority, asynchronous completion, audit or egress gaps using failing integration tests.
- [ ] Add boundary tests for staff override on authority cases, duplicate send, AI failure preserving manual reply, synthetic PII outbound payload and log redaction. Check actual runtime DB role where possible; record role scope.
- [ ] Apply minimal fixes proven by failures; do not substitute a helper test for gateway transport capture.
- [ ] Run focused unit and PostgreSQL application tests in disposable schemas, commit changes and provide exact commands/counts and gaps.

## Task B2 — Retrieval, policy grounding and sensitive routing

**Owner:** Backend worker 2.
**Files:** `apps/ai_service/engine.py`, `apps/core_backend/` retrieval/prompt as needed, additive `data/benchmarks/` local gold, dedicated retrieval/grounding tests and evidence. No backend ticket or general evaluation framework edits.
**Interface:** `Engine.analyse/draft` and existing retriever result/versions; keep compatible.

- [ ] Inspect active approved KB against old shared UUID gold; lock an app-specific gold with expected doc/version IDs from policies before running retrieval. Preserve old shared gold unchanged.
- [ ] Write failing tests for sealed-cosmetics overgeneralization, unsuitable duplicate-charge advice for unauthorized payment, expired/conflict/no-document and top-3 scoring behavior.
- [ ] Fix policy grounding/routing conservatively; uncertainty and sensitive intent ambiguity yield clarification/authority handling without factual invention.
- [ ] Run real active retriever against locked gold, output raw top-k/source versions, hashes, Recall@3 denominator and robustness slices. Seek coordinator review of local gold; never claim cross-group approval.
- [ ] Commit code, tests and reproducible bounded evidence; report failures honestly.

## Task B3 — Acceptance runner and ML/performance evidence

**Owner:** Backend worker 3.
**Files:** `pipeline/evaluation/`, additive `scripts/` acceptance runner, dedicated evaluation tests and report under a new artifacts path. Avoid B1/B2 owned source and frontend.
**Interface:** Existing application ticket/jobs HTTP endpoints, metrics/provenance contracts and stored ML OOF files. Do not relabel cached as live.

- [ ] Audit 46-label/fold coverage, baseline/model split compatibility, per-class/confusion output and existing checkpoint manifests. Validate real provenance; do not forge missing fold artifacts.
- [ ] Add tests proving missing ML provenance, unavailable price, failed/timeout jobs and wrong KB gold cannot certify acceptance.
- [ ] Implement or repair a bounded runner measuring ticket submission through terminal AI job state; preserve synthetic schemas/tickets, avoid sending replies, and record p50/p95/errors, tokens and cost coverage from declared verified pricing.
- [ ] Produce per-class/confusion and robustness reports from supported evidence with exact execution labels; make runner repeatable and document prerequisites without secrets.
- [ ] Run focused tests and bounded local evaluation if safely isolated; commit with counts and unresolved gates.

## Task F1 — Usable light frontend

**Owner:** Frontend worker.
**Files:** `apps/frontend/`, `DESIGN.md`, frontend surface brief/design notes only. No backend or acceptance docs changes.
**Interface:** Existing authenticated routes/API, human review actions and source metadata; no invented backend capabilities.

- [ ] Read both named skills and full app-screens reference; capture incumbent authenticated console/shop/admin at relevant widths. Inventory user jobs, draw app direction retaining compatible established brand and record choice.
- [ ] Improve hierarchy and action grouping, text readability, restrained neutral surfaces, clear selection/empty/error/loading states and phone navigation. Preserve confidentiality, access behavior and source/AI distinction with text rather than excessive color.
- [ ] Read Impeccable craft floor immediately before edits; document Operate mode and approved bright restrained refinement.
- [ ] Run frontend tests/build, authenticated browser flows and axe/overflow checks; inspect production build screenshots at 1440/768/390 and 360 where relevant. Run both design detectors; disclose failures rather than bypass checks.
- [ ] Commit changes and report before/after, direction/seed, screenshot paths, test counts and any remaining issues.

## Coordinator integration

- [ ] Review each diff and evidence; send corrections to owning workers. Review local gold and record delegated approval without implying external approval.
- [ ] Cherry-pick clean commits, resolve contract mismatches, run integrated Python/frontend/E2E checks and live smoke against final code.
- [ ] Grade new claims and paired workflows as AI/agent; keep raw sources and hashes. Verify current provider pricing from primary sources if computing cost.
- [ ] Update FR/quality acceptance matrix and report which original gates pass, fail or remain outside local authority. Independent final review before completion claim.
