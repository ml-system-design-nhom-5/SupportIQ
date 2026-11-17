# eval

`eval/` holds the evaluation code, the test and scenario sets with their frozen inputs, the release command, and, later, the load test of NFR-08 ([ADR-0021, Target layout](../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#target-layout)). It reaches `ai-service` only through its HTTP contract, the public interface of its package, or the formats of the model artifact and the release manifest, never through its internals (ADR-0021, Where the code of `main` goes, statement 1).

Two parts live here:

- the release command, in [`release/`](release/README.md): new code at the rule level of `ai-service`, which ingests the KB and builds the candidate releases that the offline evaluation gate checks;
- the evaluation code and the suites of `main`, which came from `pipeline/evaluation/`, `data/benchmarks/`, and `data/knowledge/`. The join moved them as they were: their only changes are the format fixes that the root hooks need and the deletion of the code that imports a deleted module ([ADR-0021, CI](../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#ci), statement 5). The code cannot run yet ([State after the join](#state-after-the-join)).

## Layout

| Path | Holds |
|---|---|
| [`release/`](release/README.md) | The release command `supportiq-release`, a project of its own |
| [`kb-ingestion/v2/`](kb-ingestion/v2/) | The output of KB ingestion for KB v2: the KB file, the document-to-intent mapping, and the report |
| `src/supportiq_eval/` | The evaluation code of `main`: hold-out and robustness evaluation of the intent model, the comparison of the baselines with the transformer models, the contracts, metrics, and report of the system evaluation, its human assessment, and the latency benchmark |
| `src/supportiq_eval/autoeval/` | The parts of the autoeval of `main` that the join kept: the frozen datasets, the gates, the metrics, the numpy inference backend, and the report |
| `src/supportiq_eval/intent_schemas.py` | The schemas of `main` for an intent prediction, the context and result of a routing decision, and the intent policy file. No module of `eval/` imports it ([Open questions](#open-questions)) |
| `configs/` | The configurations of `main`: the autoeval and its saved baseline report, the comparison, the hold-out evaluation, and the three system evaluations |
| `suites/` | The frozen suites: `system/v1`, `system/v2/acceptance`, `system/v2/dev`, `final_acceptance/v1`, `final_acceptance_supplement/v1`, `autoeval/v1`, and `app_retrieval_gold/v2`, each with its README |
| `suites/system/inputs/` | The inputs that the manifests of the system suites pin: `approved_kb.v1.json`, `mock_orders.json`, and `intent_policy.v2.json`, the routing policy of `main` |
| `tests/` | The tests of the evaluation code of `main` |

## State after the join

- The evaluation code does not import: it still names `pipeline.evaluation`, `pipeline.preparation`, and `pipeline.training`, which are now `supportiq_eval` and `supportiq_ml` under `eval/src/` and `ml/src/`. The tests import the same names.
- The paths that the code computes from its own file (`parents[2]`, `parents[3]`) now land on `eval/`, not on the repository root. The configurations and the manifests of the suites name the paths of `main` (`data/benchmarks/`, `data/knowledge/`, `apps/`, `artifacts/`); each suite README lists where those files are now.
- The hold-out evaluation and the system evaluation have no runner. The join deleted `run_evaluation.py`, `run_system_evaluation.py`, `system_execution.py`, `system_server.py`, `system_performance.py`, `oversight_scenarios.py`, and `complete_system_report.py`, because each imports a deleted module, directly or through another of these files ([ADR-0021, Where the code of `main` goes](../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#where-the-code-of-main-goes), statement 2). Only `run_comparison.py` and `assess_system.py` still have a command, and `assess_system.py` reads the folder of a completed system evaluation run, which only the deleted runner wrote.
- The autoeval has no runner either: its command line (`cli.py` and `__main__.py`), `ml_suite.py`, and `llm_suite.py` were deleted with the modules they imported ([ADR-0021, CI](../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#ci), statement 6).
- The evaluation code has no `pyproject.toml`, no `uv.lock`, and no CI workflow. It imports numpy, pandas, scikit-learn, pydantic, and cloudpickle; torch and transformers for the transformer models; and scipy and threadpoolctl when they are installed. Its tests use pytest. The first PR after the join brings `eval.yml` and the interim rule level (statements 8 and 9), and its `tech-debt` issue tracks this work.

Until then, only the release command runs.

## Frozen data

- The suites and their inputs keep every byte ([ADR-0021, Large files and data](../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#large-files-and-data), statement 3). `.gitattributes` turns off line-end conversion for them, and the hooks that fix files skip them ([DATA-06](../docs/rules/data-and-ml.md#data-layout), [DATA-08](../docs/rules/data-and-ml.md#data-layout)).
- The manifests of the system suites pin the uppercase SHA-256 of every byte of their files. The manifest of `autoeval/v1` pins the lowercase SHA-256 of each text file after CRLF is turned into LF. The manifests are never edited, and the paths in them are those of `main` (statement 4).
- A suite is never edited or regenerated after its results have been seen; a necessary change needs an ADR and invalidates earlier results ([DATA-23](../docs/rules/data-and-ml.md#splits-and-evaluation-protocol)).
- Test data never enters training, feature fitting, calibration, threshold or rerank-weight tuning, few-shot examples, or prompts ([DATA-25](../docs/rules/data-and-ml.md#leakage)). A set for tuning is a separate development set.

## The offline evaluation gate

The release command builds a candidate release manifest, runs the gate on exactly that manifest, and publishes it only when the gate passes ([ADR-0021, Release and the offline evaluation gate](../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#release-and-the-offline-evaluation-gate), [DATA-57](../docs/rules/data-and-ml.md#models-and-artifacts)). It builds the candidate already; the gate itself follows ([`release/README.md`, Known limits](release/README.md#known-limits)).

- The gate of the first release is the minimum of DATA-57: every guardrail test of [TEST-26](../docs/rules/testing.md#guardrail-tests) and every mandatory escalation case passes, with exactly that manifest loaded where a test uses `ai-service`. No current release exists to compare with.
- The shared scenario set of Groups 2 and 5 does not exist yet. Until it is in `eval/`, ADR-0021 replaces it with interim cases written from ESC-01 to ESC-05: fixtures in `eval/`, approved by the project lead, and labeled "interim, not the shared scenario set" ([ADR-0021, Exception to TEST-26](../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#exception-to-test-26)). These fixtures are planned and do not exist yet. Every report of the gate must state the TEST-26 item on the shared scenario set as not met.
- The gate runs by command before each release, not on every PR.
- Groundedness is graded by two people, each sample independently, with their agreement reported ([DATA-46](../docs/rules/data-and-ml.md#evaluation-and-reporting), NFR-04).

## What the evaluation code of `main` measures

This section describes what the evaluation code of `main` measures, as `main`'s `docs/autoeval.md` and `pipeline/evaluation/README.md` recorded it. Where the join deleted the runner, it describes the runs on `main` in the past tense. Its module paths and output folders (`artifacts/`) are not those of this repository, so no command of `main` is repeated here.

### Intent model

- On `main`, the hold-out evaluation scored each trained model on the test set of the split: Macro-F1, accuracy, per class, the confusion matrix, the 12 in-scope intents, robustness slices, and latency on CPU. Its functions remain in `evaluate_intent.py`; its runner was deleted.
- It only called `predict`: it never fitted, never tuned a hyperparameter or a threshold on the test set, and never changed the winner that cross-validation chose ([`ml/README.md`, Training](../ml/README.md#training)).
- It concluded only about the intent model. Criteria of the whole system, such as Recall@3, grounding, oversight, and end-to-end latency, stay `not_evaluated` in its requirements matrix (`reporting.py`).
- The comparison of the three baselines with two DistilBERT models (`run_comparison.py`) ranks only the models whose training rows are shown to be disjoint from the test set: the baselines, trained on the split, and a transformer whose membership evidence, a file of its training row IDs with a pinned checksum, shares no row with the test set. `configs/comparison.json` gives that evidence for `supportiq_distilbert` and none for `supportpilot_distilbert` (`membership_evidence: null`), so the scores of `supportpilot_distilbert` are only descriptive.

### System

- On `main`, the system evaluation ran the whole chain on the system suites. The join deleted its runner with the modules that the runner imported; its contracts, metrics, and report are kept.
- The `mock` profile ran offline with simulated dependencies; its evidence was `simulated`, and it could never pass acceptance. The `live` profile used the real model, the real encoder, and Gemini, after checks of the release, the encoder, the KB snapshot, and the token budget.
- Its exit status was `0` when every mandatory gate passed on live evidence, `2` when the run was valid but did not pass (always for `mock`, or when human evidence was missing), and `1` for a configuration or provenance error.
- Human assessment requires a human reviewer (`reviewer_type: human`), the time of the review, an attestation that every factual claim was reviewed, and, for each supported claim, its source, document version, and evidence span. A review prepared by an AI is labeled `ai` and is never imported as a human grade. A case that should have a draft and has none counts as missing evidence.

### Autoeval

- The ML suite checked the integrity of the model, then scored it on the 156 written cases of `system/v1`: accuracy, Macro-F1, the in-scope and out-of-scope split, calibration (the expected calibration error, ECE, and a reliability table), routing, the noisy set (`ml_noise.jsonl`, NFR-02), and the out-of-scope set (`ml_oos.jsonl`). Its latency was the compute time of the inference backend (`IntentModel.predict` in `autoeval/backends.py`), not the latency of the service.
- The LLM suite, offline, built the payload of Gemini for the cases with an order and checked whether a name, phone number, email, order ID, or tracking ID reached it. It also probed the output validator with fake responses of Gemini, `redact_contacts()` with fixed input strings, and the `PipelineRunner` of `main` with fake components for its handling of LLM and model failures. Live, it called Gemini on 66 fixed cases within a budget of calls and cost.
- Each gate of `configs/autoeval.json` names a metric, a threshold, and a severity, `block` or `warn`. A gate is `pass` when its metric meets the threshold; `fail` or `warn`, by its severity, when the metric misses it; `skipped` when its `skip_if` condition holds; and `not_run` when its suite did not run or its metric is missing (`autoeval/gates.py`). A gate that did not run is not a pass.
- `configs/autoeval_baseline.json` is the saved report of one run on `main`.
- These suites were built for the routing and the drafting of `main`. Their results measure that code, not `ai-service`.

### Results recorded on `main`

[ADR-0021, Evaluation evidence on `main`](../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#evaluation-evidence-on-main) records which results of `main` stand: the autoeval ran the real model on 156 cases, with a Macro-F1 of 0.611 and an expected calibration error of 0.106. The Macro-F1 of 0.9736 does not measure the model, and the acceptance set `system/v2/acceptance` holds all 50 cases of `system/v2/dev`. None of these numbers was measured again here.

## Known limits

- The acceptance set `system/v2/acceptance` is contaminated, so no quality target is reported from it ([DATA-23](../docs/rules/data-and-ml.md#splits-and-evaluation-protocol)); a new acceptance set needs its own ADR ([ADR-0021, Follow-ups](../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#follow-ups)).
- The 63 `must_escalate` cases of the system suites follow a meaning that differs from the requirements: only the 5 `human_agent` cases match ESC-03 (b), and no case is an ESC-03 (a) request (ADR-0021, Evaluation evidence on `main`).
- The routing results of `main` came from its second routing (`decide_route`), not from the routing that served (ADR-0021, What `main` holds).
- `main` recorded that some labels of the 156 cases of `system/v1` are disputed between Bitext intents that are close in meaning, and that the noisy set (84 cases in 5 variants, 420 rows) and the out-of-scope set (80 cases) are small and show only a direction (`git show 19ece5d:docs/autoeval.md`).
- The first release serves no KB document, so every policy question abstains ([ADR-0021, KB ingestion](../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#kb-ingestion)).
- `autoeval/backends.py` reads the pinned checksums of the model from `apps/ml_inference/app.py`, which no longer exists, so its model check stops with an error ([Open questions](#open-questions)). The join deleted the evaluation code that imported a deleted module (ADR-0021, Where the code of `main` goes, statement 2).
- The docstring of `src/supportiq_eval/autoeval/__init__.py` still points to `docs/autoeval.md` and to `python -m pipeline.evaluation.autoeval`; this README replaces that document, and the code stays as it was moved (ADR-0021, CI, statement 5).
- No load test of NFR-08 exists yet, and the product-value study of NFR-11 has not been run: no result claims a measured gain in handling time.

## Open questions

- Whether the hold-out evaluation, the system evaluation, and the autoeval get new runners, and which issue brings them. ADR-0021 (CI, statement 6) states only that the autoeval does not run between the join PR and the first PR after it, and the scope of the `eval.yml` issue does not include a runner.
- Where the model check of `autoeval/backends.py` takes its pinned checksums from. The `eval.yml` issue resets the root paths, but `apps/ml_inference/app.py` exists at no path of the tree.
- Whether `intent_schemas.py` stays in `eval/`. No module imports it since the join deleted `mock_dependencies.py`, and ADR-0021 (Where the code of `main` goes, statement 2) deletes only code that imports a deleted module.
