# Codebase Cleanup Implementation Plan

> **For agentic workers:** Execute only the assigned task in the existing Orca workspace, using Ponytail ultra. No helper agents.

**Goal:** Remove proven dead code and make evaluation tooling portable without changing product decisions, API contracts or model artifacts.

**Architecture:** Keep existing layers and public helper names. Reuse the existing CLI/path conventions; preserve the shared safety boundary and client ownership rules. The remote refactor is already integrated and pushed at `19ece5d`.

**Tech Stack:** Python, pytest, existing application services and Orca.

**Spec:** User request to plan and execute cleanup; `docs/design/codebase-cleanup-and-refactoring.md` informs scope but its historical thresholds/test counts are not new runtime requirements.

## Global Constraints

- Preserve serving weights, calibration, routing thresholds, approved KB, frozen gold and all evaluation artifacts.
- Preserve user PPTX files and private credentials; do not commit either.
- No new dependencies, generic wrappers, feature work or Agent Evaluator implementation.
- B's separately authorized real-LLM experiment owns the remaining six provider attempts; cleanup uses zero provider/GPU/training calls.
- Do not unify hash helpers by changing uppercase/lowercase contracts or introducing runtime dependencies on training modules.

## Review Focus

- Dynamic imports/re-exports: remove only symbols with proven zero callers.
- Security: keep policy contact provenance, customer redaction and error validation intact.
- CLI portability: repository and candidate roots must be explicit and testable from a different directory.
- Historical experiments: no deletion based solely on zero Python imports.
- SQLite/client ownership: retain the verified persistence fix and injected HTTP-client lifetime.

## A: Portable evaluation paths

Files: `scripts/run_closure_candidate_audit.py`, `scripts/collect_final_acceptance_evidence.py`, focused tests.

- [ ] Replace hardcoded main/candidate workspace roots in the closure audit with CLI arguments; default main root to the script repository and candidate root to an explicit required argument. Retain model-directory layout beneath those roots.
- [ ] Remove the redundant machine-specific secrets fallback after the repository-relative fallback; retain explicit path/environment handling.
- [ ] Add a small parser/path test using temporary directories without loading model weights or credentials; verify existing collector tests and script help.
- [ ] Commit scoped changes and report evidence; do not rerun historical audits into immutable artifact directories.

## C: Proven dead application code

Files: unused imports identified in backend/AI/demo modules; `apps/core_backend/retrieval/encoder.py`; unreferenced exported contact maps in `apps/core_backend/llm/gemini.py` only if zero callers still hold on pushed main.

- [ ] Merge pushed main in the worker, repeat caller checks, then remove only confirmed unused imports, the unused `count_tokens` helper and unused derived contact-map exports.
- [ ] Keep the pinned policy registry, provenance validator, all validation functions and observable response fields.
- [ ] Run relevant offline safety/privacy/client/application tests; preserve line endings and commit minimal changes.

## Coordinator review and completion

### Documentation scope added by the user

- [ ] C reviews root drafts and `docs/` for duplicate or superseded content, retaining unique material at a canonical path before deleting redundant files.
- [ ] Update references, `docs/README.md` navigation and the existing cleanup log; check links in changed documents.
- [ ] Preserve the assignment, active requirements/runbooks/ADRs, historical acceptance evidence and all user PPTX files. No blanket documentation purge.

- [ ] Review both diffs independently; confirm model/KB/evidence hashes untouched.
- [ ] Run default pytest and frontend checks appropriate to integrated changes; fix any meaningful failures.
- [ ] Commit, push reviewed cleanup, reload owned services if application code changed and verify readiness.
- [ ] Report actual deleted code/portable paths and unresolved classifier acceptance separately. Cleanup does not mean the system passed acceptance.
