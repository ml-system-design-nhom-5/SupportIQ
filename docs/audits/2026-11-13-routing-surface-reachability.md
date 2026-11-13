# Routing Surface Reachability Audit (`IntentClient -> decide_route`, `2026-11-13`)

- **Scope & Constraints:** Review-only trace under Ponytail ultra (`0` live provider calls, `0` edits to `apps/`, `pipeline/`, or frozen gold).

## 1. Verdict: Bare `IntentClient -> decide_route` Is Not an Exposed HTTP Product Path

Tracing every FastAPI route in `apps/` and every `decide_route` caller shows **zero exposed HTTP endpoints** execute bare `IntentClient -> decide_route` without `PipelineRunner` or `Engine` guards:

1. **Primary Product API (`apps/backend/main.py` -> `apps/backend/tickets/jobs.py` -> `apps/ai_service/main.py`):**
   - `apps/backend/main.py` (`@app.post("/v1/shop/tickets")` at `L205`, `@app.post("/v1/console/tickets/{ticket_id}/suggestions")` at `L249`) dispatches to `apps/backend/tickets/jobs.py`, which calls `settings.ai_service_base_url + "/v1/analyses"` and `"/v1/drafts"` (`jobs.py:153-155`). `apps/backend/` has **0** imports/calls to `IntentClient`, `decide_route`, or `PipelineRunner`.
   - `apps/ai_service/main.py` (`@app.post("/v1/analyses")` at `L176-179`, `@app.post("/v1/drafts")` at `L183-186`) delegates solely to `Engine.analyse` / `Engine.draft` (`apps/ai_service/engine.py`), which enforce shared `apps/core_backend/safety.py` text/evidence/post-gen guards (and `2b46968` `encoder_unavailable` escalation parity) without calling `decide_route`.
2. **ML Inference Service (`apps/ml_inference/app.py`):**
   - Exposes `GET /health` (`L755`), `GET /ready` (`L759`), and `POST /predict` (`L773-797`). `/predict` returns raw `PredictResponse` (`container.predict`), never calling `decide_route` or returning routing actions.
3. **Demo HTTP App (`apps/demo/app.py` -> `apps/demo/service.py` -> `PipelineRunner`):**
   - `POST /api/demo/runs` (`apps/demo/app.py:95-99`) calls `DemoService.submit_run` (`apps/demo/service.py:65-103`) -> `PipelineRunner.run` (`apps/core_backend/orchestration/pipeline_runner.py:55-145`).
   - `PipelineRunner.run` (`L79`) is the **only** caller of `decide_route` anywhere under `apps/`. Immediately after `decide_route` and `commerce.lookup_order`, `PipelineRunner.run` enforces `evaluate_text_safety(text)` (`L106-119`) from `apps/core_backend/safety.py` before step 5 retrieval/drafting (`L131`), followed by `evaluate_evidence_scope(...)` (`L136-145`) and post-generation validation.

## 2. Where the `12` Mandatory & `2/80` OOD Bare-Stage Numbers Originate

- `decide_route(prediction: IntentPrediction, context: RoutingContext, policy: IntentPolicy)` (`apps/core_backend/intent/routing.py:134-138`) takes **no customer message text**; it is a pure metadata/label/threshold/slot/override router.
- All other `decide_route` callers are offline evaluation harnesses and unit tests:
  - `pipeline/evaluation/classifier_acceptance_gate.py:988, 1072, 1168` (`clf.predict(txt) -> decide_route`)
  - `pipeline/evaluation/system_execution.py:330` (`scope == "component"` bare component probe)
  - `pipeline/evaluation/autoeval/ml_suite.py:24`
  - `scripts/compare_trained_candidates.py:426`, `scripts/diagnose_final_12_cases.py:84`, `scripts/run_benchmarks.py:39`, `scripts/run_offline_robustness.py:51`
  - Unit tests (`tests/unit/test_routing.py`, `test_completion_routing.py`, `test_mandatory_routing_b.py`, `test_intent_client_rejector_routing.py`, `test_intent_policy_and_escalation.py`, `test_system_components.py`) — whereas `tests/unit/test_pipeline_runner_safety_b.py` and `pipeline/evaluation/guard_corrections_verifier.py` test the guarded `IntentClient -> decide_route -> PipelineRunner` path.
- Thus, the documented `12` mandatory (`37/60` unfaulted) and `2/80` `ml_oos_80` (`4/11` non-answerable `final_acceptance`) `retrieve_draft` leaks (`docs/audits/2026-11-13-task-c-independent-evaluation.md:238`, `docs/audits/2026-11-13-mandatory-routing-integration.md:24-27`) measure the **unguarded bare intent-stage diagnostic (`IntentClient -> decide_route`)**, not an exposed HTTP product route.

## 3. Smallest Reporting Correction (Preserving Raw Numbers)

- Do **not** add redundant text parsing inside `decide_route` (`apps/core_backend/intent/routing.py`) or hide the raw `12` mandatory / `2/80` OOD bare classifier+router counts (those remain real stage-level metrics for serving `distilbert-supportiq` + `decide_route` when invoked without `PipelineRunner`).
- In acceptance tables (`docs/audits/2026-11-13-post-guard-acceptance.md:20`, `docs/REQUIREMENTS_EVIDENCE_MATRIX.md:279`), relabel `"LEGACY HTTP ROUTER UNCHANGED"` / `"separate HTTP IntentClient -> decide_route path"` to:
  > **`Bare Intent-Stage Diagnostic (IntentClient -> decide_route)`**: retains `12` mandatory / `2/80` OOD raw `retrieve_draft` recommendations in standalone/component evaluation; **not** an exposed HTTP product route (`apps/` calls `decide_route` only inside guarded `PipelineRunner.run`, and `apps/backend` -> `apps/ai_service` uses guarded `Engine`).
