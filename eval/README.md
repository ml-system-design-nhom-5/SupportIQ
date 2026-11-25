# eval

`eval/` holds the release command of `ai-service`, the gate run records and published manifests of its releases, and the output of KB ingestion ([ADR-0028, Copies deleted from `build/join-main`](../docs/decisions/0028-repository-layout-for-the-pull-request-into-main.md#copies-deleted-from-buildjoin-main), statement 3). The release command reaches `ai-service` only through its HTTP contract, the public interface of its package, or the formats of the model artifact and the release manifest, never through its internals ([ADR-0021, Where the code of `main` goes](../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#where-the-code-of-main-goes), statement 1).

The evaluation code of `main` that remains is in [`pipeline/evaluation/`](../pipeline/evaluation/README.md), and the test and scenario sets are in `data/benchmarks/`, both kept at their paths ([ADR-0028, Kept parts of `main`](../docs/decisions/0028-repository-layout-for-the-pull-request-into-main.md#kept-parts-of-main); [ADR-0031, What is retired](../docs/decisions/0031-retiring-apps-and-the-evaluation-runners-of-main.md#what-is-retired)).

## Layout

| Path | Holds |
|---|---|
| [`release/`](release/README.md) | The release command `supportiq-release`, a project of its own: it ingests the KB, builds candidate releases, runs the offline evaluation gate on them, publishes those that pass, packs each published release into its release archive, and downloads a release for the Modal deploy and the local run ([`release/README.md`, Release download](release/README.md#release-download)) |
| [`releases/`](releases/) | The gate run record and the published manifest of each release, one folder per release, and the pinned file `pinned-release.txt`, which names the release in use |
| [`kb-ingestion/v2/`](kb-ingestion/v2/), [`kb-ingestion/v2.1/`](kb-ingestion/v2.1/) | The output of KB ingestion for KB v2 and KB v2.1: the KB file, the document-to-intent mapping, and the report. KB v2 admits no version, and KB v2.1 admits 14 |

## Test and scenario sets

- The interim escalation cases of the gate are in [`data/benchmarks/escalation/interim-v1/`](../data/benchmarks/escalation/interim-v1/README.md), written for a KB without documents, and [`data/benchmarks/escalation/interim-v2/`](../data/benchmarks/escalation/interim-v2/README.md), written for KB v2.1 ([The offline evaluation gate](#the-offline-evaluation-gate)). The other sets of `data/benchmarks/` and the other data folders of `main` are the frozen suites of `main`, at the paths that their manifests name.
- Every set keeps every byte. `.gitattributes` turns off line-end conversion for `data/`, and the hooks that fix files skip the data of the sets ([ADR-0028, Checks](../docs/decisions/0028-repository-layout-for-the-pull-request-into-main.md#checks), statements 1, 2, and 5; [DATA-06](../docs/rules/data-and-ml.md#data-layout), [DATA-08](../docs/rules/data-and-ml.md#data-layout)).
- A set is never edited or regenerated after its results have been seen; a necessary change needs an ADR and invalidates earlier results ([DATA-23](../docs/rules/data-and-ml.md#splits-and-evaluation-protocol)).
- Test data never enters training, feature fitting, calibration, threshold or rerank-weight tuning, few-shot examples, or prompts ([DATA-25](../docs/rules/data-and-ml.md#leakage)). A set for tuning is a separate development set.

## The offline evaluation gate

The release command builds a candidate release manifest, runs the gate on exactly that manifest, and publishes it only when the gate passes ([ADR-0021, Release and the offline evaluation gate](../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#release-and-the-offline-evaluation-gate), [DATA-57](../docs/rules/data-and-ml.md#models-and-artifacts)). `supportiq-release run-gate` runs the gate in Docker, and `publish-candidate` publishes a candidate whose run passed ([`release/README.md`, The offline evaluation gate](release/README.md#the-offline-evaluation-gate)). `release-2026-11-18-02` and `release-2026-11-23-01`, which the pinned file names, passed it, and their records are [`releases/release-2026-11-18-02/gate-run.json`](releases/release-2026-11-18-02/gate-run.json) and [`releases/release-2026-11-23-01/gate-run.json`](releases/release-2026-11-23-01/gate-run.json).

- The gate of the first release is the minimum of DATA-57: every guardrail test of [TEST-26](../docs/rules/testing.md#guardrail-tests) and every mandatory escalation case passes, with exactly that manifest loaded where a test uses `ai-service`. The escalation cases and the checks on the candidate load it; the guardrail tests check code and settings that no asset of the manifest changes ([`release/README.md`, Known limits](release/README.md#known-limits)). `release-2026-11-18-02` had no release to compare with. For `release-2026-11-23-01`, the model, the prompts, and the routing equal those of `release-2026-11-18-02`, as the [gate design](../docs/design/gate-for-a-release-with-kb-documents.md#data-57-item-2-against-release-2026-11-18-02) requires.
- The shared scenario set of Groups 2 and 5 does not exist yet. Until it is in `data/benchmarks/escalation/`, ADR-0021 replaces it with interim cases written from ESC-01 to ESC-05: fixtures approved by the project lead and labeled "interim, not the shared scenario set" ([ADR-0021, Exception to TEST-26](../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#exception-to-test-26)). The fixtures are [`data/benchmarks/escalation/interim-v1/`](../data/benchmarks/escalation/interim-v1/README.md), written for the routing configuration `main-untuned-v1` ([ADR-0025](../docs/decisions/0025-routing-configuration-of-the-first-release.md)); the project lead approved and froze them on 2026-11-17, before the first gate run. For `release-2026-11-23-01`, the fixtures are [`data/benchmarks/escalation/interim-v2/`](../data/benchmarks/escalation/interim-v2/README.md), written for KB v2.1 and frozen with the project lead's approval of 2026-11-23, before its gate run. Every report of the gate must state the TEST-26 item on the shared scenario set as not met.
- The gate runs by command before each release, not on every PR.
- Groundedness is graded by two people, each sample independently, with their agreement reported ([DATA-46](../docs/rules/data-and-ml.md#evaluation-and-reporting), NFR-04).

## Autoeval

- The autoeval of `main` and its workflow are retired ([ADR-0031, What is retired](../docs/decisions/0031-retiring-apps-and-the-evaluation-runners-of-main.md#what-is-retired)). [`docs/autoeval.md`](../docs/autoeval.md), a kept document of `main`, still describes it ([ADR-0031, Open questions](../docs/decisions/0031-retiring-apps-and-the-evaluation-runners-of-main.md#open-questions), item 4).
- Its suites were built for the routing and the drafting of `main`. Their results measure that code, not `ai-service`.

## Results recorded on `main`

[ADR-0021, Evaluation evidence on `main`](../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#evaluation-evidence-on-main) records which results of `main` stand: the autoeval ran the real model on 156 cases, with a Macro-F1 of 0.611 and an expected calibration error of 0.106. The Macro-F1 of 0.9736 does not measure the model, and the acceptance set `system/v2/acceptance` holds all 50 cases of `system/v2/dev`. None of these numbers was measured again here.

## Known limits

- The acceptance set `system/v2/acceptance` is contaminated, so no quality target is reported from it ([DATA-23](../docs/rules/data-and-ml.md#splits-and-evaluation-protocol)); a new acceptance set needs its own ADR ([ADR-0021, Follow-ups](../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#follow-ups)).
- The 63 `must_escalate` cases of the system suites follow a meaning that differs from the requirements: only the 5 `human_agent` cases match ESC-03 (b), and no case is an ESC-03 (a) request (ADR-0021, Evaluation evidence on `main`).
- The routing results of `main` came from its second routing (`decide_route`), not from the routing that served (ADR-0021, What `main` holds).
- `main` recorded that some labels of the 156 cases of `system/v1` are disputed between Bitext intents that are close in meaning, and that the noisy set (84 cases in 5 variants, 420 rows) and the out-of-scope set (80 cases) are small and show only a direction (`git show 19ece5d:docs/autoeval.md`).
- The first release, `release-2026-11-18-02`, serves no KB document, so every policy question abstains with it ([ADR-0021, KB ingestion](../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#kb-ingestion)). The release in use, `release-2026-11-23-01`, serves KB v2.1, whose versions all expire on 2026-12-31 ([`data/raw/kb/v2.1/README.md`](../data/raw/kb/v2.1/README.md)).
- No file of `pipeline/` or `tests/` builds an LLM client ([ADR-0031, The temporary rules end](../docs/decisions/0031-retiring-apps-and-the-evaluation-runners-of-main.md#the-temporary-rules-end)).
- No load test of NFR-08 exists yet, and the product-value study of NFR-11 has not been run: no result claims a measured gain in handling time.
