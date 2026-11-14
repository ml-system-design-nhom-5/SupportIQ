# Retrieval and evaluation integration, 2026-11-12

The coordinator integrated backend retrieval worker commits through `e53744d` and evaluation worker commits through `34a4e35`. This records component integration, not overall Topic 1 acceptance.

## Integration and verification

- User-requested deletion of `pipeline/monitoring` and `pipeline/retrieval` committed as `15490b1`. Runtime retrieval remains under `apps/core_backend/retrieval`; observability remains under `apps/backend/platform/observability.py`.
- Retrieval integrated through `b0a3876`. A line-ending conflict in `apps/backend/tickets/jobs.py` was resolved by keeping the coordinator's B1 safety implementation and adding only B2's `llm_metadata` persistence. Analysis failure fallback, draft failure recovery and sticky authority were preserved.
- Evaluation integrated through `55f4eb1`. Stored OOF audit is historical evidence, not a fresh training run. Individual fold checkpoint manifests remain unverified.
- Coordinator independently ran the worker's retrieval/Gemini/grounding suite: 60 passed in 2.76 seconds.
- Coordinator then ran retrieval/Gemini/grounding plus PostgreSQL application safety/boundary/retry on the integrated tree: 84 passed in 7.80 seconds.
- Coordinator independently ran the evaluation worker's preceding revision: 21 passed in 9.96 seconds. The final integrated full suite, including the final 24 evaluation guardrail cases, completed: **622 passed, 2 skipped, 2 deselected in 147.84 seconds**.
- Backend and AI service were restarted using the checked-in application scripts with dependency installation and frontend rebuild skipped. PostgreSQL remained running; no database reset. Both readiness endpoints passed; AI reports trained, verified model and configured LLM.
- Post-reload Edge application E2E: **12 passed in 29.4 seconds**, across desktop, tablet and two phone widths.

Commands use `.venv/Scripts/python.exe -X utf8 -m pytest`, `PSYCOPG_IMPL=python` and the discovered PostgreSQL binary directory on PATH. The 84-test subset consists of `test_retrieval_grounding_b2.py`, `test_gemini_llm.py`, `test_ai_grounding.py`, `test_backend_safety_closure.py`, `test_ai_boundary.py` and `test_llm_retry.py`.

## Retrieval evidence scope

Gold v2.1 was approved by the AI coordinator under delegated stakeholder authority before the acceptance run; no instructor or cross-group approval is claimed. Frozen SHA-256: `a33e6394d6d76384ac33771d014816ae7e2d1a3c379b3c1ec3a7f3605940bee7`.

`artifacts/evaluation/app-retrieval-v2-acceptance-run2/` records oracle-intent retrieval Recall@3 **0.9839**, Hit@3 **1.0**, on **31 answerable queries covering 11 intents**. The twelfth product intent, `human_agent`, has three unanswerable escalation cases. Optional `edit_order` queries are separate. Two conflict queries are explicitly not executed on the active coherent KB.

OOD retrieval false-answer rate is **0.6000 (3/5)**. The five-case Engine test supplies mocked out-of-scope classifier outputs; it verifies the Engine guard given those outputs, not actual ML predictions on those queries. It must not be cited as end-to-end deployed OOD accuracy. The contradictory-KB fixture exercises the real retriever with an offline encoder and shared policy keys; it does not prove arbitrary natural-language contradiction detection.

The worker's earlier artifacts are preserved as historical runs. This note limits broader wording in those artifacts; it does not rewrite their original bytes or hashes.

## Bounded live verification

`artifacts/evaluation/coordinator-integrated-20261112-live/runs/accept-20261112-123928-2802bd/` contains a five-ticket run on integrated commit `55f4eb1`. It uses real PostgreSQL jobs and the reloaded AI service, with the application boundary driven through in-process ASGI TestClient. It does not measure a physical browser/network round trip.

Command: `.venv/Scripts/python.exe -X utf8 -m scripts.run_application_acceptance --mode live --num-warm 4 --poll-timeout 25 --pricing-file artifacts/evaluation/pricing/gemini-3.1-flash-lite-20261112.json --output-dir artifacts/evaluation/coordinator-integrated-20261112-live`.

All five tickets reached the expected terminal state: **2 draft_ready, 3 abstained**. No technical errors, timeouts, failed jobs or unreviewed customer replies were observed. Mixed-workload p50 was **0.17556s**, p95 **3.56772s**. These five cases are a small smoke sample, not a representative performance certification; three abstentions avoid LLM generation. The application's first measured request is not a model cold start.

The two drafted requests preserved `google_ai_studio`, `gemini-3.1-flash-lite`, `grounded-v2` metadata and 2,988 input plus 281 candidate tokens. Thinking counts were absent. Complete cost is therefore unavailable. Using the published standard paid rates conditionally gives a recorded lower bound of **USD 0.0011685 for the run**, or **USD 0.0002337 per submitted ticket** across this mixed five-ticket workload. Account billing tier and invoices remain unverified. No unknown token count is asserted to be zero.

## Remaining acceptance limits

The live runner verifies lifecycle, latency and no-auto-send observations, not factual support for every draft claim, actual-model OOD robustness, sensitive escalation coverage or agent-simulated productivity. Those must be assessed with their own scoped evidence before a final Topic 1 verdict. Prior phase claims/agent study artifacts remain historical and are not relabeled as new measurements. No instructor, cross-group or real-human sign-off is claimed.
