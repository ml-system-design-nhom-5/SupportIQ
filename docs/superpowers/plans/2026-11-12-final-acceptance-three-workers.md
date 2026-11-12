# Final prototype acceptance implementation plan

> **For agentic workers:** Use Orca Antigravity workers as explicitly requested by the user. Apply systematic debugging, meaningful regression tests, verification-before-completion and coordinator review. Three NEW isolated workspaces; do not reuse deleted workers.

**Goal:** Close the remaining Topic 1 prototype acceptance gaps using current-model evidence, source-based AI grading and measured agent-simulated product trials.

**Architecture:** Keep the existing application, PostgreSQL job workflow and verified AI gateway. Independent workers own routing/robustness, usage/accounting and evidence collection; the coordinator owns stakeholder decisions, claim grading, paired trials, integration and final verdict.

**Tech Stack:** Existing Python/FastAPI/PostgreSQL, PyTorch/Transformers, Gemini and pytest. No new infrastructure dependencies.

**Spec:** `docs/superpowers/specs/2026-11-12-acceptance-closure-design.md`, narrowed by this plan and `docs/CHỦ ĐỀ 1.md`.

## Authority and approach

The user explicitly requested three new workers through final acceptance, retains delegation of stakeholder decisions and AI/agent evaluation. Continue the approved implementation scope without another approval round. Existing code is preferable to a rewrite; reusing historical summaries alone cannot demonstrate the current release. Model retraining is conditional on demonstrated failure or unavailable evidence, not automatic.

## Global constraints

Synthetic data only. No auto-send or automatic transactions. No push/deploy/database reset. Coordinator owns root services; workers must not stop/restart them or write root files. Keep user PPTX files unchanged. Do not recreate `pipeline/monitoring` or `pipeline/retrieval`. Keep historical gold/evidence immutable; every run has exclusive new output directory and source/config/code hashes. Missing measurements are unknown, never zero. AI grading and agent timing are explicitly simulated evidence, not human/instructor/cross-group approval.

Root interpreter: `F:/Năm 3/SD/project/SupportIQ/.venv/Scripts/python.exe`. Native PostgreSQL bin `F:/PostgreSQL/bin`, `PSYCOPG_IMPL=python`. Root local credentials may be read privately by tests via explicit secrets path; never print them or `.env` contents. Services backend8080/AI8002/PostgreSQL55432 are running from integrated code. Start base is coordinator commit after this plan commit.

## Review focus

- Correct OOD labels supplied by mocks must not masquerade as actual classifier behavior.
- Universal abstention must not inflate safety while destroying useful in-scope drafts.
- Provider total tokens and thought counts may differ; verify billing semantics before deriving counts.
- Policy citations alone do not prove claim support or business appropriateness.
- Paired timing must measure actual coordinator work, preserve task/order and disclose learning/tool overhead.

## Worker A: Current-model robustness and safe routing

**Owns:** `apps/ai_service/engine.py`, routing policy if necessary, additive robustness runner under `scripts/`, dedicated tests and `artifacts/evaluation/final-routing-*`. Do not edit Gemini client, drafting budgets, jobs or acceptance framework.

- [ ] Lock hashes of existing noise/OOD suites and approved local gold before inference. Load actual verified serving model, not fake prediction fixtures. Recompute typo/casual/clean metrics and OOD/ambiguous routing with raw predictions/reasons.
- [ ] Reproduce unsafe draft recommendations and authority loss with focused failing regressions. Fix shared routing minimally; do not keyword-match case IDs or rewrite gold. Keep supported-query coverage visible alongside abstention.
- [ ] Evaluate all 12 product intents and sensitive fraud/chargeback/refund/exception scenarios, including override. LLM must be a spy that fails if called during offline robustness; label Engine versus HTTP/application boundaries precisely.
- [ ] Retest fixed cases plus unchanged suites, report exact denominators, safety failures and in-scope coverage; commit and report current Task/Dispatch IDs.

## Worker B: Usage completeness and repeatable performance accounting

**Owns:** `apps/core_backend/llm/gemini.py`, `apps/ai_service/drafting.py`, `pipeline/evaluation/application_acceptance.py`, additive dedicated accounting tests and evidence. Do not edit Engine or jobs. Coordinate any interface change with A/C and coordinator first.

- [ ] Reproduce unknown/missing thought counts, billable invalid output and retry accounting gaps. Preserve provider raw usage/provenance and all measured attempts without credentials or raw sensitive data.
- [ ] Verify Gemini usage semantics from official primary docs before any derivation. If explicit total permits complete billable-output accounting without a separate thought count, retain the reported total and label derived billing values with formula/provenance. Otherwise keep incomplete cost null with observed lower bound. Never assume missing thoughts zero.
- [ ] Ensure provider/model/tier matching fails closed for VERIFIED labels; unknown account tier is explicitly conditional list-price estimation. Include missing provider, mixed attempts/models, no-call abstention, inconsistent totals, invalid numeric values and failed attempts in tests.
- [ ] Add/use bounded runner that separates draft-producing versus abstention latency and reports p50/p95/error rate/mean per submitted ticket, with actual boundary and immutable artifacts. Initial work is offline/mock only; request coordinator authorization before external calls or service restart.
- [ ] Run relevant tests, commit and report evidence and unresolved limits. No fabricated checkpoints/training lineage.

## Worker C: Frozen scenario suite and current-release evidence collector

**Owns:** additive scenario JSON/manifest under `data/benchmarks/final_acceptance/`, additive collector under `scripts/`, dedicated tests, `artifacts/evaluation/final-evidence-*`. Do not edit product runtime or A/B files.

- [ ] Freeze 24 synthetic cases before execution covering 12 product intents, unauthorized/exception/authority, expired/conflict/no-source and OOD. Gold source expectations derive from approved active policies, not observed retrieval. Separate production fixtures from injected robustness fixtures; ask coordinator to approve frozen suite before scored execution.
- [ ] Build a reusable isolated-PostgreSQL/application collector using actual gateway with raw prediction/routing, full draft text/citations, immutable source content/version/hash snapshots, timings, tokens/metadata and customer no-auto-send observation. Preserve draft availability and all failures. No private data or destructive resets.
- [ ] Prepare at least 12 paired tasks (same cases manual vs assisted; alternate order). Collector records real events/timing and coordinator review decisions. Do NOT invent manual outputs, ratings, times or approvals; coordinator performs AI claim grading and agent trials after handoff.
- [ ] Test collector with controlled transport and error paths. Commit locked suite + collector first. Initial execution is offline/mock only; coordinator approves suite and at most24 live synthetic cases before external calls. Report mismatched provenance/failures, not blanket PASS.

## Coordinator integration and verdict

### Integration checkpoint: Worker A

Worker A commits `bb3754c`, `cbeb761`, and `36d82c8` were reviewed and integrated as `8203996`, `7fd798c`, and `ad7833b`. Coordinator verification: 32 dedicated routing regressions passed; 63 existing routing, grounding, authority, and backend safety checks passed. Root services have not yet been reloaded with these changes; accounting and collector review remain open.

Use `artifacts/evaluation/final-routing-20261112-v3/ROBUSTNESS_REPORT.md` as the corrected Worker A report; v1/v2 reports are historical and superseded. Current actual-model evidence shows 80/80 OOD cases without a draft recommendation, 23/23 explicit sensitive scenarios retaining authority, 2/2 valid courier pickup cases reaching drafting, and 21/34 answerable acceptance cases reaching drafting. These are component observations, not whole-system acceptance. Severe typo accuracy remains 59.92%, with macro-F1 0.6267.

The 11 unanswerable cases reaching draft recommendation require additional coordinator-owned downstream evaluation; they are not implicitly covered by Worker C's separately frozen suite. The synthetic encoder-failure case was not injected in this component run and receives no fault-handling success credit. Mandatory escalation action correctness remains unresolved even where abstention prevents drafting.

### Integration checkpoint: Worker C

Worker C commits `34d4784`, `cb3154f`, `85ba113`, `f632e12`, and `b52dc9f` were reviewed and integrated through main commit `95190af`. Coordinator verification at root: 23 suite and collector tests passed in 30.10 seconds, including real encoder readiness contract checks, failure without live mock fallback, both declared LF/CRLF provenance pairs, and rejection of mixed pairs. Frozen suite hashes remain unchanged. Historical mock artifacts are dry-run evidence only; initial reports were superseded by collector corrections.

The coordinator-owned supplement is frozen at `data/benchmarks/final_acceptance_supplement/manifest.json` (11 unchanged original cases, SHA-256 `5659c7070064aa36b328a7e4087ab939c43d210863591e2dff3642431832dc0a`). Neither that supplement nor the final 24-case suite has been executed against the final integrated release. Worker B accounting corrections, gateway reload, live collection, semantic claim grading, and paired agent trials remain outstanding.

- [ ] Approve independent local gold before scored runs and synchronize workers on reviewed commits. Review changes and tests before cherry-picking; resolve overlap preserving B1 safety and persisted metadata.
- [ ] Run the current-model routing suite and bounded live application evaluation after final reload. AI-grade all factual claims against captured sources; separate supported, unsupported, unverifiable and business-inappropriate advice. Target >=90% supported; mandatory escalation scenarios all correct, no auto-sends/transactions.
- [ ] Execute paired agent trials on >=12 same-case tasks, record real wall times, order, outputs and approve/edit/reject decisions; report denominators and simulation limits.
- [ ] Run relevant integrated checks, full suite once final runtime changes settle, and browser E2E if application behavior changed. Commit evidence and final FR01-08/quality matrix: pass, fail or not evaluated with direct links.
- [ ] Final verdict targets the Topic1 prototype, not unsolicited production certification. Shared KB/gold synchronization and instructor approval can only be marked external-unverified when no independent evidence exists; user delegation does not fabricate those identities.
