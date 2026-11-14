# Guard and typed-fault integration

Selectively integrated A `85aa931`, B `eb85d0d` and `7e3b1a9`, C `4c25072` and `692e171`, and A audit `1dc25ff`. Historical before-fix artifacts remain unchanged; they describe earlier code, not the integrated behavior.

Root verification used the project virtual environment, `PSYCOPG_IMPL=python`, and `F:/PostgreSQL/bin` on PATH:

- 201 tests passed across typed faults, pipeline safety, guard/fault evaluation, mandatory routing, grounding, Gemini, intent metadata, and both PostgreSQL application suites (46.44 seconds).
- After adding bounded IntentClient error messages, 78 related intent/pipeline/fault tests passed (7.27 seconds).
- Root additive execution: `artifacts/evaluation/root_guard_integration_20261113`; 23 fault scenarios preserved absence of drafts, zero live provider requests, 13 guard probes, historical evidence hashes unchanged, temporary PostgreSQL schema verified absent after cleanup.
- Six imported historical/corrected report hashes verified. The first root test run caught a stale pre-fix timeout assertion; C corrected it to require both canonical `ml_timeout` and compatibility `ml_unavailable` without changing frozen gold.

Acceptance remains open. Engine still abstains on encoder unavailability while PipelineRunner escalates. Other frozen strict mismatches include contradictory expected actions, privacy-preserving 404 intake denial, and reason aliases. Correct-intent automatic live draft coverage remains 4/12; staff overrides are separate. AI grading is not a real-human study, and complete billed cost remains unknown when thought-token usage is omitted. No additional live LLM tests were run.

All three workers acknowledged the user's Ponytail ultra instruction. Subsequent work must use the smallest complete fix and preserve privacy, validation, and required checks.
