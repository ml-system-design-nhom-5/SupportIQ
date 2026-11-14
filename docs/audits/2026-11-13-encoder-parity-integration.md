# Encoder fault parity integration

Integrated B `2b46968` after independent C approval (`a8955ee`). Engine now escalates both unavailable and failed retrieval encoders with distinct bounded codes. Neither is classified as a missing document. Empty or expired knowledge still abstains; source validation and privacy denial remain unchanged.

Root verification: 73 tests passed in 81.64 seconds across `test_pipeline_runner_safety_b.py`, `test_full_pipeline.py`, `test_fault_boundary_checks.py` and PostgreSQL `test_backend_safety_closure.py`, using the project virtual environment, `PSYCOPG_IMPL=python` and PostgreSQL binaries on PATH. C independently ran the 23 fault scenarios with zero provider calls and clean PostgreSQL schema removal. Imported parity report hashes verified.

The previous audits describe the pre-fix encoder divergence; this addendum closes that defect. Frozen tests injecting encoder unavailability under a runtime-failure fixture still have a reason-code mismatch: distinct faults remain distinct. Full acceptance is still open pending classifier improvement and final rubric reconciliation. No live provider requests were added.
