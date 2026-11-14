# Acceptance Closure Round Implementation Plan

> **For agentic workers:** Execute the assigned task in its existing Orca workspace; use Ponytail ultra. No helper workers.

**Goal:** Close verified defects and improve correct automatic draft eligibility while preserving all safety controls in `docs/CHỦ ĐỀ 1.md`.

**Architecture:** Keep the current application and provider model. B fixes the existing Engine branch; A investigates a bounded classifier improvement; C owns independent acceptance checks. Only reviewed candidates passing independent gates may replace serving weights.

**Tech Stack:** Existing Python virtual environment, PyTorch, pytest, PostgreSQL and Orca.

**Spec:** `docs/CHỦ ĐỀ 1.md`, `docs/audits/2026-11-13-post-guard-acceptance.md`.

## Global Constraints

- Ponytail ultra; no new dependencies or speculative abstractions.
- Preserve frozen fixtures, 404 ownership denial, source validation, authority checks and staff approval.
- No live provider calls in this round; 18/24 previously used, 6 reserved.
- User delegated stakeholder and AI grading roles; disclose AI simulation and zero human participants without inventing research or instructor approval.
- Preserve serving weights until independent promotion gates pass. Previous repeatedly examined probes are development data, not fresh holdout.

## Review Focus

- Encoder missing versus runtime failure: distinct codes, same fail-closed escalation contract.
- Correct intent coverage: distinguish raw drafts, correct-intent drafts and staff overrides.
- Novel OOD/compound requests: no eligibility gain by unsafe drafting.
- Mandatory escalation: no arbitrary threshold reduction or case-specific regexes.
- Evaluation provenance: fixed splits, hashes, no training on held-out cases or invented billing totals.

## B: Encoder parity

Files: `apps/ai_service/engine.py`, existing affected unit/e2e tests.

- [ ] Reproduce encoder-unavailable parity failure with a focused assertion.
- [ ] Remove the legacy empty-document classification for that fault and recommend escalation with `insufficient_evidence,encoder_unavailable`.
- [ ] Preserve missing/expired evidence behavior and runtime-failure codes; run focused tests and commit.

## A: Bounded classifier improvement

Files: existing training/calibration modules only as needed; isolated candidate artifacts; existing classifier gate tools.

- [ ] Diagnose genuine serving failures against training distribution and prior rejected experiments before choosing a change.
- [ ] Select one materially different, justified approach using existing architecture; at most two new fits in this round. Report a negative result instead of repeating rejected threshold/CLS/lexical approaches.
- [ ] Fix train/calibration split and manifests before fitting; do not use C's sealed independent cases or frozen evaluation as training labels.
- [ ] Compare candidate against serving on identical inputs: 46-label retention, robustness, mandatory safety, OOD and correct automatic draft eligibility. Commit only reproducible source/metadata/reports; preserve serving weights.

## C: Independent acceptance

Files: new small sealed holdout under evaluation artifacts and an additive acceptance report; minimal existing evaluation code changes only if needed.

- [ ] Freeze independent policy-grounded answerable, OOD and mandatory-escalation probes before seeing A's candidate. Publish counts/hash to A, not probe content.
- [ ] Verify B's locked commit and A's locked candidate independently; keep original strict-gold results separate from justified fixture dispositions.
- [ ] Reconcile all explicit rubric requirements, including traditional baseline evidence and delegated paired workflow/decision measurements; list actual missing evidence separately from optional goals.
- [ ] Report achieved criteria and unresolved defects. No acceptance claim by changing frozen gold or hiding failure.

## Coordinator integration

- [ ] Review selective changes and independent results, run checks covering integration gaps, commit, reload owned services and verify readiness.
- [ ] Allocate the next bounded round for each remaining real gap. Acceptance requires evidence; negative model experiments do not end the objective.
