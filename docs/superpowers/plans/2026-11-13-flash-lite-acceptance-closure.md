# Flash-Lite acceptance closure implementation plan

> For agentic workers: use the applicable implementation, debugging, verification
> and review skills. User explicitly requests three Orca Antigravity workers;
> coordinator reviews and selectively integrates their results.

**Goal:** Close demonstrated safety and routing gaps, verify actual application
drafting with Gemini 3.5 Flash-Lite, and report acceptance against the topic spec.

**Spec:** `docs/CHỦ ĐỀ 1.md`.

**Architecture:** Preserve the trained single-label 46-intent classifier and
separate optional rejection decisions. Preserve approved versioned retrieval,
source-grounded generation and mandatory staff review. Evaluate the real
application path separately from component/oracle-intent diagnostics.

**Tech stack:** existing Python 3.12 root venv, PyTorch, FastAPI, PostgreSQL,
Gemini Developer API, existing frontend and evaluation tools. No new dependency.

## Global constraints

- Base root commit `c01f0ff`; existing reviewed adapter fix is integrated at
  `88eef1d`, runtime/gate at `b54f958`. Active private model is
  `gemini-3.5-flash-lite`; source fallbacks still need aligning to that choice.
- Main serves the original classifier. Candidate `028ed76` is rejected:
  3/80 OOD leaks, one real mandatory leak. No model swap without independent gate.
- Do not edit frozen benchmark cases, expected actions, approved KB or published
  old artifacts. Previous inspected regression suites are not new holdouts.
- Do not add per-case keyword patches or lower policy confidence/margin thresholds.
- No auto-send, financial/order execution, invented human participants, account
  credit balance, complete cost from missing usage, or external stakeholder approval.
- User delegates AI stakeholder and manual grading roles. Disclose AI grading;
  absence of human participants is a limitation, not a new permission requirement.
- Use root `.venv/Scripts/python.exe`; Windows driver `PSYCOPG_IMPL=python`, PG
  bin `F:/PostgreSQL/bin`. No printing/copying/committing secrets or user PPTX files.
- Worker commits are integrated selectively, never whole-branch merged into root.

## Review focus

- Ambiguous/multiple/unsupported intents must not become confident unsafe drafts.
- Safe fallback and mandatory escalation are different outcomes; retain counters.
- Accepted rejector decisions cannot bypass authority, policy, retrieval or slots.
- Provider timeout/503, missing usage and exhausted live budget must fail closed.
- Distinguish application completion, component drafts and oracle overrides.

## A: classifier safety experiment

Own `pipeline/training/`, focused classifier tests, new A evaluation artifacts.
Do not edit runtime, policy, approved knowledge, old artifacts or C's shared gate.

- [ ] Reconcile current sources with root and preserve all previous experiments.
- [ ] Predeclare at most two new offline fits and at most 30 minutes training.
  Train on verified Bitext train replay and new generic multi-intent, ambiguous
  and unsupported-retail examples with disjoint source-row/template-family
  train/calibration/evaluation splits. No frozen benchmark text in training.
- [ ] Select model, temperature and existing-schema rejector on calibration only;
  lock artifacts before evaluating new holdout and known regression suites once.
- [ ] Report eligibility precision and correct-intent coverage, 46/34-label
  retention, noise calibration, strict mandatory actions and all unsafe leaks.
  No claim that abstention improves classification accuracy.
- [ ] Use existing `selective_calibration.v1` supported feature specs. If they
  cannot close the gap, report evidence and a scoped proposal, not runtime edits.
- [ ] Commit source, dataset manifests/hashes and raw results; ignored weights
  remain available at exact paths. Do not promote or make live provider requests.

## B: mandatory routing and override safety

Own `apps/ai_service/engine.py`, `apps/core_backend/intent/routing.py`, relevant
routing/engine tests and new B raw diagnostic artifacts. Coordinate shared routing
file with coordinator; schemas/client already fixed unless new repro requires more.

- [ ] Reproduce strict 21/63 baseline and separate uninjected fixture failures.
- [ ] Group action mismatches by actual cause and document what the specification
  requires. Establish red tests for general rules, not frozen case IDs/text.
- [ ] Implement minimal common routing/uncertainty/escalation behavior needed for
  mandatory cases without turning every query into escalation or removing staff
  clarification/override options. Preserve default output scores and precedence.
- [ ] Verify both in-process Engine and HTTP IntentClient -> decide_route paths,
  regression cases, authorized overrides, no LLM on veto and no auto-send.
- [ ] Report before/after exact matches, unsafe drafts and changes to answerable
  coverage. Missing simulated fault injection stays NOT_EXECUTED, never PASS.
- [ ] Commit tested changes; no model fits, provider edits, live requests or gold
  expected-action modifications.

## C: independent application evidence and live LLM trial

Own evaluation/collector scripts, focused tests and new C evidence artifacts;
update evidence matrix/audit only after reviewing current records. No production
engine/routing/provider edits, training or serving model promotion.

- [ ] Verify existing 10-fold OOF records/lineage and list actual missing evidence;
  do not rerun training or label available records missing without inspection.
- [ ] Execute frozen application scenarios (12 answerable, 12 safety/unanswerable,
  plus declared boundary fixtures) with serving classifier and Gemini3.5Flash-Lite.
  Use synthetic accounts/orders only and an owned isolated runtime when practical.
  Preserve root user application data and active services; no shared destructive DB.
- [ ] New live allowance: **24 actual generation HTTP requests maximum including
  all retries**, shared across this task and any permitted diagnostic overrides.
  Implement pre-network global counting and disable hidden lower-layer retries.
  Record preflight, actual count and decline before network when exhausted. Old
  8-call, Hydrogen migration/diagnostic and cheap-comparison budgets stay spent.
- [ ] Keep current application deadlines for primary results. Any longer-timeout
  component diagnostic must be separately labeled and count toward the same cap.
  No silent model fallback. No whole-system success claim from readiness alone.
- [ ] Record raw status, actual reported model, source/version citations,
  automatic vs staff override, attempt timing, p50/p95, error rate, observed usage,
  unknown complete costs and no-auto-send. Report sample sizes and denominator.
- [ ] Coordinator performs AI claim grading and paired workflow evaluation using
  captured outputs; label simulated roles and timing limits honestly.
- [ ] Independently gate A/B outputs when their locked commits arrive. If waiting,
  send exact pending dependency and deliberately idle; do not poll or repeat work.
- [ ] Commit scripts/tests/evidence and report acceptance gaps with exact paths.

## Coordinator integration

- [ ] Align tracked current defaults/examples with user-selected3.5Flash-Lite while
  retaining explicit Hydrogen and prior-model request compatibility.
- [ ] Review C's drafts against actual cited source text, record AI grading and
  compare paired simulated workflows without asserting real-user improvement.
- [ ] Verify independent worker results, resolve conflicts selectively, run focused
  root tests and required checks, commit, reload owned services and verify health.
- [ ] Update acceptance matrix: confirmed, failed and not executed are separate.
  Stop promotion if unsafe leaks persist. Report complete evidence and remaining
  blockers; do not mark system accepted simply because workers finish.
