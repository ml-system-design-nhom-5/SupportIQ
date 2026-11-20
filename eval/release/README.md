# Release command

`supportiq-release` builds what a release of `ai-service` serves, runs the offline evaluation gate on it, and publishes it. It is the release command of [ADR-0021, Release and the offline evaluation gate](../../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#release-and-the-offline-evaluation-gate), with four commands:

- `ingest-kb` admits or quarantines the KB document versions of a raw KB folder ([KB ingestion](#kb-ingestion));
- `build-candidate` copies the six assets into a new folder and writes the manifest of a candidate release, which no replica serves until the offline evaluation gate passes ([Candidate release](#candidate-release));
- `run-gate` runs the offline evaluation gate on a candidate and records the run ([The offline evaluation gate](#the-offline-evaluation-gate));
- `publish-candidate` copies a candidate whose gate run passed into a release folder and links the run in its manifest ([Publish](#publish)).

The gate run of `release-2026-11-18-02` passed, and its record is [`../releases/release-2026-11-18-02/gate-run.json`](../releases/release-2026-11-18-02/gate-run.json). The first run, of `release-2026-11-18-01`, failed on two defects of the gate itself, fixed in `86f73df`; its record stays in [`../releases/release-2026-11-18-01/`](../releases/release-2026-11-18-01/gate-run.json), and that release ID is never used again ([DATA-48](../../docs/rules/data-and-ml.md#evaluation-and-reporting), [ARCH-40](../../docs/rules/architecture.md#versioned-assets)).

It is a project of its own, apart from the evaluation code that `eval/` took over from `main`:

- ADR-0021 (Where the code of `main` goes, statement 3) makes the release command new code that uses none of the moved evaluation code.
- ADR-0021 (CI, statement 7) holds it to the rule level of `ai-service` now, while the moved code waits for the interim level of statements 8 and 9.

It imports only public modules of `ai-service`, never their internals (ADR-0021, Where the code of `main` goes, statement 1), and a contract of import-linter checks this:

- `supportiq_ai_service.release.manifest`, to check a candidate and a published release;
- in the gate only, `supportiq_ai_service.composition_root`, `intent`, `retrieval`, and `drafting`, to build the application of a candidate with the ports of the gate.

## Run and test

Run the commands from the repository root, after [Set up](#set-up). `--project` keeps the root as the working folder, so the paths stay those of the repository.

```bash
uv run --project eval/release supportiq-release ingest-kb \
  --kb-folder data/raw/kb/v2 \
  --intent-labels contracts/schemas/IntentLabel.yaml \
  --output eval/kb-ingestion/v2
```

```bash
uv run --project eval/release supportiq-release build-candidate \
  --spec <release spec> \
  --release-records eval/releases \
  --output <new folder outside the repository>
```

```bash
eval/release/gate/run-gate.sh \
  --candidate <candidate folder> \
  --cases data/benchmarks/escalation/interim-v1/cases.json
```

```bash
uv run --project eval/release supportiq-release publish-candidate \
  --candidate <candidate folder> \
  --cases data/benchmarks/escalation/interim-v1/cases.json \
  --release-records eval/releases \
  --output <new folder>
```

`run-gate` itself needs torch, so `run-gate.sh` runs it in Docker ([Run in Docker](#run-in-docker)). `build-candidate` and `publish-candidate` need no torch.

```bash
uv run --project eval/release pytest eval/release
```

The tests need no network, no `.env`, and no torch: the gate runs on a fake application of a candidate, and the routes of the real application of `ai-service` are read from its `create_app` with fake ports, through the FastAPI that `ai-service` locks. They read `data/raw/kb/v2/`, `contracts/schemas/IntentLabel.yaml`, `eval/kb-ingestion/v2/`, `data/benchmarks/escalation/interim-v1/`, and `ai-service/prompts/grounded-v4/` without changing them.

## Set up

1. Install [uv](https://docs.astral.sh/uv/) 0.11.11 or later. It installs the Python version of [`../../.python-version`](../../.python-version).
2. Install the locked dependencies:

   ```bash
   uv sync --locked --project eval/release
   ```

## Commands

Run each check in `eval/release/`.

| Check | Command |
|---|---|
| Format | `uv run ruff format --check .` |
| Lint | `uv run ruff check .` |
| Types | `uv run pyright` |
| Layer boundaries | `uv run lint-imports` |
| Tests | `uv run pytest` |
| Coverage | `uv run pytest --cov --cov-report=`, then the two reports below |
| Dependency vulnerabilities | `uv export --locked --all-groups --no-emit-project --no-emit-local --format requirements-txt --output-file <temporary file>`, then `uv run --locked pip-audit --strict --disable-pip --require-hashes --timeout 60 --requirement <temporary file>`, as in `backend` CI. `--no-emit-local` leaves out the path dependency on `ai-service`, which has no hash; its own dependencies are in the export |

```bash
uv run coverage report --fail-under=80
uv run coverage report --fail-under=90 --include="*/supportiq_release/*/domain/*"
```

## KB ingestion

`ingest-kb` reads a raw KB folder, `data/raw/kb/<kb_version>/`, and writes three files into a new or empty output folder ([Output](#output)). It never changes the raw folder: an output folder in `data/raw/` or inside an input is refused ([DATA-06](../../docs/rules/data-and-ml.md#data-layout)).

The raw folder holds two files, both kept byte for byte:

- the release file of the KB holder, `kb-release.json`: the name of its release and the document versions it releases;
- the KB file, the one that its `source` names. `source` names the path on `main`, so only the file name is used, in the same folder.

Either file missing, unreadable, or with another shape stops the run with exit status 2, and nothing is written. Ingestion quarantines records, never the files that list them.

### Admission

A record is admitted only when both hold ([ADR-0021, KB ingestion](../../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#kb-ingestion), statement 1):

- its `document_id` and `version` are a pair that `kb-release.json` lists, compared as exact texts;
- every field below is present, with the type, length, and pattern of `KbDocumentVersion` in the contract ([DATA-12](../../docs/rules/data-and-ml.md#validation-at-every-boundary)).

Ingestion never invents a value. A JSON `null` counts as missing, a version written as a number is not turned into text, and a missing field is never filled in.

| Field of the KB file | Field of `KbDocumentVersion` | Checked |
|---|---|---|
| `document_id` | `document_id` | Required; the pattern of `KbDocumentId` |
| `version` | `version` | Required; the pattern of `KbDocumentVersionTag` |
| `title` | `title` | Required; 1 to 200 characters |
| `content` | `body` | Required; 1 to 20 000 characters |
| `content_hash` | None | Required; 64 lowercase hexadecimal characters, equal to the SHA-256 of `content` in UTF-8: the matching checksum of [DATA-12](../../docs/rules/data-and-ml.md#validation-at-every-boundary). It is not written, because `KbDocumentVersion` has no such field |
| `policy_key` | `policy_key` | Required; 1 to 100 characters |
| `valid_from` | `effective_start_at` | Required; the pattern of `Timestamp`, and a real time |
| `valid_to` | `effective_end_at` | Optional; the pattern of `Timestamp`, and later than `valid_from` |
| `approved_by` | `owner` | Required; 1 to 100 characters, copied unchanged (statement 2) |
| None | `source` | The name of the KB file with its KB version, such as `approved_kb.v2.json, KB v2` (statement 2) |
| `supported_intents` | The intents of the mapping | Required; a list of texts, at least one, each once, each one of the labels of `contracts/schemas/IntentLabel.yaml` (statement 4) |

Lengths count characters, not bytes, as the contract does. Every text must be one that UTF-8 can write, so a lone surrogate such as `\ud800`, which JSON allows, is invalid. `title`, `content`, `policy_key`, and `approved_by` must hold a character that is not white space, as the importer of `main` required of `approved_by`.

Other fields of the KB file are not read. `last_reviewed_at` is left out, because the KB file does not provide it ([DATA-13](../../docs/rules/data-and-ml.md#validation-at-every-boundary)).

### Quarantine

Every other record is quarantined with every reason, sorted by code, then by field, both in alphabetical order, as in the table ([DATA-13](../../docs/rules/data-and-ml.md#validation-at-every-boundary)). The `field` of a reason names the field of the KB file.

| Code | When |
|---|---|
| `duplicate_version` | Another record has the same pair. Neither is admitted, because ingestion cannot tell which one the KB holder released |
| `invalid_field` | A field has another type, length, or pattern, `valid_to` is not later than `valid_from`, or `content_hash` is not the checksum of `content` |
| `missing_field` | A required field is absent or `null` |
| `not_in_release` | `kb-release.json` does not list the pair, or the pair is not two texts |
| `unknown_intent` | `supported_intents` names a label outside the contract |

A run fails until an issue reviews and accepts what it did not admit ([DATA-13](../../docs/rules/data-and-ml.md#validation-at-every-boundary)): the quarantined records, and the released versions that the KB file lacks, since both make the KB differ from the release of the KB holder ([ADR-0021, KB ingestion](../../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#kb-ingestion), statement 1). It still writes its three files, and it exits with status 3 unless `--accepted-quarantine` names the URL of that issue. The report then records the URL as `quarantine_accepted_in`.

### Conflicts

A conflict between admitted versions is listed in the report and never removed ([DATA-12](../../docs/rules/data-and-ml.md#validation-at-every-boundary), [DATA-19](../../docs/rules/data-and-ml.md#knowledge-base)). `ai-service` shows it to staff at `as_of` with the validity `conflicting` and the reason code `conflicting_sources`.

The rule is a copy of the rule of `ai-service`, because the release command never imports its internals. `ai-service/src/supportiq_ai_service/suggestions/domain/evidence.py`, `_in_effect` and `_validity` (lines 144 to 154 at commit `1d6ab7a`), make two rules:

- a version is in effect from `effective_start_at`, included, until `effective_end_at`, excluded;
- two versions in effect at `as_of` with one `policy_key` are both `conflicting`.

So two admitted versions conflict exactly when they share a `policy_key` and their effective periods overlap. This lists every pair that DATA-12 asks for, and also pairs with the same content. `tests/unit/kb_ingestion/test_conflicts.py` holds the cases of the conflict tests of `ai-service` (`ai-service/tests/unit/suggestions/test_evidence.py`), so a change of either rule shows as a failing test.

### Output

| File | Format | Holds |
|---|---|---|
| `kb.json` | `supportiq-kb/interim-1` | The admitted versions, with the fields of `KbDocumentVersion`. The only file with text of the KB |
| `document-intents.json` | `supportiq-document-intents/interim-1` | The intents of each admitted version. Its version is the KB version |
| `ingestion-report.json` | `supportiq-kb-ingestion-report/interim-1` | The KB version, the release of the KB holder, the SHA-256 of both input files, and, by document ID and version only, the admitted versions, the quarantined records with their reasons, the conflicts, and the released versions that the KB file lacks |

`ai-service` reads the first two formats (`ai-service/README.md`, Asset formats). A data contract in `contracts/` replaces all three (ADR-0021, Follow-ups; [#21](https://github.com/ml-system-design-nhom-5/SupportIQ/issues/21)). Each file is UTF-8 JSON with two-space indents, LF line ends, and a final newline, and the same input always gives the same bytes.

Both commands write their files into a new hidden folder next to the output, `.<name>.partial-<random>`, and move it to the output only once every file is written. A run that fails for any reason removes that folder, so the output is complete or absent, never half written. A process that is killed can leave the hidden folder behind; no command reads it.

A quarantined record is named by its position in the KB file, from 0, and by its document ID and version only when they are valid identifiers: any other value could hold text of the KB.

### KB v2

[`../kb-ingestion/v2/`](../kb-ingestion/v2/) holds the output for `data/raw/kb/v2/`. It admits 0 document versions and quarantines all 17 ([ADR-0021, KB ingestion](../../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#kb-ingestion), statement 5):

- the 14 `POL-…` documents: `missing_field` for `policy_key`. `POL-ORD-003` and `POL-SHIP-001` also get `unknown_intent`, because their `supported_intents` name `edit_order`, `change_shipping_address`, and `delivery_options`, which are not labels of the contract;
- the 3 `b1000000-…` documents: `not_in_release`, and `invalid_field` for `version`, which is a number.

Issue [#13](https://github.com/ml-system-design-nhom-5/SupportIQ/issues/13) reviewed the quarantine and the project lead accepted it there (DATA-13), so the committed report records that issue as `quarantine_accepted_in`, and ADR-0021 (Validation) is met for KB v2. A test runs the command with `--accepted-quarantine` and that issue, checks that it exits with status 0 and that the committed files equal the new run, and that the raw folder keeps its SHA-256.

### The checks of the importer of `main`

`main` had its own KB importer, `retrieval/adapters/kb_importer.py` (deleted in the join; commit `3a4544b` holds it). Each of its checks maps to KB ingestion as follows.

| Check of `main` | Here |
|---|---|
| `missing_metadata`: a document without approval metadata | `missing_field` for each missing field (DATA-12, DATA-13) |
| `invalid_approval_metadata`: blank `approved_by`, invalid dates, an empty or unknown `allowed_roles` | `missing_field` and `invalid_field` for `approved_by`, `valid_from`, and `valid_to`; an `approved_by` of white space only is `invalid_field`. `allowed_roles` is not read: see the row of roles |
| `inactive_or_not_approved`: the status is not `approved`, or the version is not active | Replaced by the release file: a version is admitted only when `kb-release.json` lists it (ADR-0021, KB ingestion, statement 1). `KbDocumentVersion` has no status |
| `eligible_versions` by time | `ai-service` decides the validity at `as_of` from `effective_start_at` and `effective_end_at` (DATA-19) |
| `eligible_versions` by role | Not applicable: KB documents reach only the console of `staff` and `manager`, and `/v1/shop/` has no schema that can hold AI output ([contracts v1 design](../../docs/design/contracts-v1.md), `backend` contract) |
| `detect_rule_conflicts`: the same rule key with overlapping conditions and other values | Not removed: listed in the report, by the rule of [Conflicts](#conflicts) (DATA-12, DATA-19) |
| `publish_approved_kb`: never overwrite a published KB | The output folder must be new or empty |
| `publish_approved_kb`: the declared `content_hash` equals the SHA-256 of `content` in UTF-8 | The same check, as `invalid_field` for `content_hash`; a missing checksum is `missing_field`. `main` compared without case, while ingestion requires lowercase, as `hashlib` writes it and as every record of KB v2 has it |

## Candidate release

`build-candidate` reads a spec, copies the six assets that it names into a new or empty folder, writes the manifest of a candidate, and checks the candidate with `verify_candidate` of `supportiq_ai_service.release.manifest`, the one module of `ai-service` that it imports ([`ai-service/README.md`, Release manifest](../../ai-service/README.md#release-manifest)). The candidate has `"gate_run": null`, so `ai-service serve` refuses it, and only the offline evaluation gate may link a passing run ([DATA-57](../../docs/rules/data-and-ml.md#models-and-artifacts)).

### The spec

The spec is a JSON file in `supportiq-release-spec/interim-1`, with exactly these fields. A missing, unknown, or empty field refuses it.

| Field | Holds |
|---|---|
| `format` | Always `supportiq-release-spec/interim-1` |
| `release_id` | The identifier of the release, with the pattern of `release_id` in the contract. It is never reused, not even after a candidate fails the gate ([ARCH-40](../../docs/rules/architecture.md#versioned-assets)). Only the record of a gate run reserves it ([Known limits](#known-limits)) |
| `assets` | Exactly the six assets: `model`, `kb`, `mapping`, `prompts`, `routing`, and `index` |
| `assets.<asset>.version` | The version that results report, with the pattern of `AssetVersion` in the contract. `assets.kb.version` equals the `kb_version` of the KB file, and `assets.mapping.version` equals the `version` of the mapping file, whose `kb_version` equals `assets.kb.version`, as `ai-service` requires |
| `assets.<asset>.source` | The file or folder to copy, relative to the folder of the spec, or absolute. The sources of `kb` and `mapping` are single files |
| `assets.<asset>.path` | Where the asset goes in the release folder: a file path for a file, a folder path for a folder |
| `assets.routing.model_version` | The model version that the routing configuration was tuned for, equal to `assets.model.version` ([DATA-58](../../docs/rules/data-and-ml.md#models-and-artifacts)) |

For KB v2, the sources of `kb` and `mapping` are `eval/kb-ingestion/v2/kb.json` and `eval/kb-ingestion/v2/document-intents.json`, and the source of `prompts` is a folder of `ai-service/prompts/`.

### Checks before the first copy

The command stops with exit status 2 and writes nothing when any of these fails, in this order:

1. The spec has its shape; the release ID and each version fit their patterns; each path is one that `ai-service` accepts (segments of letters, digits, `.`, `_`, and `-`, no `.` or `..` segment, at most 255 characters); no asset path is inside another or is `release-manifest.json`, compared without case, because the file system of macOS does not tell `kb` from `KB`; and `routing` was tuned for the model of the spec.
2. `--release-records` names an existing folder, and it holds no entry named by the release ID. Each run of the gate keeps its record in `eval/releases/<release_id>/`, passed or failed, so an ID that a gate run used is never given again.
3. Every source exists and holds only regular files and folders, because `ai-service` refuses every link in a release. A source that is a symbolic link stops the build, and so does a link anywhere inside a folder source, even one that points inside it; the folders above a source are not checked. A folder of the Hugging Face cache holds only links to its blobs, so copy its real files first. A folder source holds at least one file, no hidden entry such as `.DS_Store`, which would change what the release serves, and no folder that cannot be listed, whose files would otherwise be left out; each file name fits the paths that a release can hold.
4. The KB file and the mapping file hold the versions of the spec (`assets.<asset>.version` above).
5. The output folder is new or empty, and lies neither in `data/raw/` nor inside the spec or a source.

Each file is then copied byte for byte into a file that did not exist, and the manifest lists the SHA-256 and the size of the copied bytes. `verify_candidate` checks the manifest, the links, the sizes, and the checksums, not the formats of the assets: the gate checks those when it loads the candidate. If `verify_candidate` refuses the candidate, or a source cannot be read during the copy, the command prints the reason, the asset, and the path inside the release, never the content of a file, and exits with status 2; nothing is left in the output ([Output](#output)).

## The offline evaluation gate

`run-gate` runs the gate of the first release, the minimum of [DATA-57](../../docs/rules/data-and-ml.md#models-and-artifacts) that ADR-0021 (Release and the offline evaluation gate, statement 3) sets: every case of a frozen set of escalation cases, three checks on the application of the candidate, and both folders of guardrail tests of [TEST-26](../../docs/rules/testing.md#guardrail-tests). The cases are [`../../data/benchmarks/escalation/interim-v1/`](../../data/benchmarks/escalation/interim-v1/README.md), which replace the shared scenario set ([ADR-0021, Exception to TEST-26](../../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#exception-to-test-26)).

### Checks before the run

The command stops with exit status 2 and writes no record when any of these fails, in this order:

1. `verify_candidate` accepts the candidate, and its KB is one file with a list of document versions.
2. The cases have the format of their README, and no case ID is given twice. Each request holds a message; each recommendation, draft status, and reason code is a value of contract 1.0.0; and each injected distribution lists intent labels once each, most likely first, with probabilities that add up to at most 1 and stay above the equal share of the rest. A refusal names the case when it can.
3. `approval.json`, next to `cases.json`, has its format, is for the same set, is `frozen` with `approved_by` and `approved_on`, and covers the SHA-256 of `cases.json` as it is ([Approval record](../../data/benchmarks/escalation/interim-v1/README.md#approval-record)).
4. `label` and each field of `written_for` match the candidate: contract 1.0.0, the model version, the routing version, the KB version, and the number of KB document versions. The message names each field that differs.
5. Each JUnit XML file of the guardrail tests is the report of its folder: a regular file whose every `testsuite` has the name of the folder (`ai_service_guardrails` or `backend_guardrails`, which `run-gate.sh` sets with `-o junit_suite_name`), holds `tests`, `failures`, `errors`, and `skipped` as integers of at least 0, and holds one `testcase` for each test, each in `tests.integration.guardrails`. A document type, an entity, and an external reference are refused. A report that is missing or cannot be read therefore gives no record; `run-gate.sh` produces both reports or stops before `run-gate`.
6. `--release-records` names an existing folder that holds no entry named by the release ID. `--git-commit` takes the 40 lowercase hexadecimal characters of a commit.

### The run

`run-gate` builds the application of the candidate in its own process with `build_candidate_application` of `ai-service`, and the ports of `gate/adapters/gate_ports.py`:

- the intent model and the search of the candidate, except for a case that injects an intent distribution or a failure ([How the gate runs a case](../../data/benchmarks/escalation/interim-v1/README.md#how-the-gate-runs-a-case));
- an LLM step that records each call and fails it with `llm_unavailable`, so the gate never calls a provider ([ADR-0021, CI](../../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#ci), statement 2).

The settings come from the environment of the process, as for `serve`. The command line sets the ones of the gate once, before it builds the application: a service token made for the run, and LLM settings that no call reads. The manifest is an argument, not a setting. Each case sends its request to `createAnalysis` and then to `createDraft` through an ASGI transport, inside the lifespan of the application, so no port is opened, and every field of `expected` is compared with both responses. The fields of an outcome are read only from a `200` body, and the problem type only from a Problem Details body, whose `status` is the HTTP status and never the status of a draft.

The checks on the candidate are:

- `routes_are_those_of_contract_1_0_0`: the application serves exactly the six routes of contract 1.0.0, none of which performs a transaction (FR-06). FastAPI keeps each included router as one route, so the gate reads the routes inside it, with the prefix of the inclusion. It also reads the routes that FastAPI serves after all others, such as those that `frontend()` adds. A route of another kind, such as a websocket route or a frontend, fails the check;
- `no_case_text_in_the_logs`: no log line holds the message of a case or a placeholder in it ([LOG-29](../../docs/rules/logging-and-observability.md#privacy-in-telemetry));
- `no_llm_call`: the LLM step received no call.

The gate passes only when every case and every check passes, and each folder of guardrail tests ran at least one test with no failure, no error, and no skip, because a skipped guardrail test is not a pass ([TEST-20](../../docs/rules/testing.md#flaky-and-skipped-tests)). Which parts load the candidate is in [Known limits](#known-limits).

### The record

Each run, passed or failed, writes `eval/releases/<release_id>/gate-run.json` into a folder that it creates exclusively, so a release ID gets one gate run ([ARCH-40](../../docs/rules/architecture.md#versioned-assets)). The record is in `supportiq-gate-run/interim-1` and holds identifiers, versions, checksums, counts, and codes, never text of a message or of the KB.

| Field | Holds |
|---|---|
| `format` | Always `supportiq-gate-run/interim-1` |
| `run_id`, `release_id` | The release ID of the candidate, which the run takes as its ID |
| `manifest_sha256` | The SHA-256 of the manifest file of the candidate |
| `git_commit` | The commit of the repository that the run used |
| `escalation_cases` | The name of the set, the SHA-256 of `cases.json`, the number of cases, the number of each kind, and for each case its ID, its rule, its kind, the injected failure if any, whether it passed, each field that did not match, as `<operation>.<field>`, and what the candidate gave for it: an HTTP status, a value of a closed set of the contract, or reason codes, with `null` for an absent value or list, `empty` for an empty list of codes, and `other` for a value outside the set, never its text |
| `candidate_checks` | Each check on the candidate, whether it passed, and what made it fail: each route outside contract 1.0.0 as `+<method> <path>` and each missing one as `-<method> <path>`, the IDs of the cases whose text was logged, or the number of LLM calls |
| `candidate_scope` | The parts that run on the candidate, the parts that do not, and why |
| `guardrails` | For each folder of guardrail tests: the tests, failures, errors, and skips, the test classes that ran, and whether it passed |
| `llm` | The calls that the LLM step received, and a sentence that no call was made or that a call fails the gate |
| `test_26` | The TEST-26 item on the shared scenario set, stated as not met ([Exception to TEST-26](../../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#exception-to-test-26), statement 3) |
| `known_gaps` | The three gaps of ADR-0021 (Release and the offline evaluation gate, statement 4) and the untuned routing of [ADR-0025](../../docs/decisions/0025-routing-configuration-of-the-first-release.md) |
| `outcome` | `passed` or `failed` |

The kind of a case is what its outcome rests on: `real_model`, `injected_distribution`, `injected_failure`, or `staff_choice`. Of the 27 cases of `interim-v1`, 6 rest on the real model, 17 on an injected distribution, 2 on an injected failure, and 2 on an intent that staff chose.

`run-gate` exits with status 0 when the gate passed and 1 when it failed; the record is written either way. It prints the release ID, the number of cases and of failed cases, the outcome, and the path of the record. Any other failure of any command, such as a record that cannot be written, prints only the name of its type and exits with status 2, so status 1 always means a gate run that failed.

### Publish

`publish-candidate` checks the approval of the cases as `run-gate` does, then reads the record of the release ID. It stops with exit status 2, names the problem, and leaves the output as it was when:

- the record is not a JSON object in `supportiq-gate-run/interim-1`, or did not pass;
- the record names another release ID or another SHA-256 of the manifest;
- the record ran other bytes of the cases;
- the release ID is already published: `eval/releases/<release_id>/release-manifest.json` exists;
- `--release-records` is not a relative path inside the repository, such as `eval/releases`, which the manifest uses to link the record.

It then copies every file of the candidate into a staging folder next to the output, writes the manifest with `gate_run` (the run ID of the record, `passed`, the path of the record, and its SHA-256), checks it with `verify_release`, and moves the folder to the output. Only then does it write the same manifest next to the record, which links the release ([ADR-0021, Release and the offline evaluation gate](../../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#release-and-the-offline-evaluation-gate), statement 1). A move that fails leaves neither the output nor the link, so the command can run again ([ERR-04](../../docs/rules/errors-and-reliability.md#handling-rules)).

### Run in Docker

`run-gate` loads the model of the candidate, which needs torch on Linux, so [`gate/run-gate.sh`](gate/run-gate.sh) runs the whole gate in Docker. It needs Docker with Compose v2 (`docker compose`, not `docker-compose`), because `gate/compose.yaml` names its project with the top-level `name`. BuildKit (`docker buildx`) is required: the repository has no `.dockerignore` at its root, and only BuildKit reads `gate/Dockerfile.dockerignore`, so `run-gate.sh` stops with status 2 without it.

| File | Does |
|---|---|
| `gate/Dockerfile` | Builds two images from the repository root. `gate` holds `ai-service` with its torch and dev groups, the release command, and the tests of `ai-service` in one environment; `backend-guardrails` holds `backend` with its dev group for its guardrail tests |
| `gate/check_locks.py` | Stops the build of the `gate` image when `ai-service/uv.lock` and `eval/release/uv.lock` pin a shared package at different versions, and names the package and both versions |
| `gate/Dockerfile.dockerignore` | Lets into the build context only the projects, locks, sources, and tests that the two images need, never a `.env` file, `data/`, `eval/releases/`, or `.git` |
| `gate/compose.yaml` | Runs the guardrail tests of `backend` against a throwaway PostgreSQL 17 in tmpfs, on an internal network, with the steps and settings of the CI job `backend-tests` |
| `gate/postgres-init.sql` | Creates the owner role and the database of those tests, with a throwaway password |
| `gate/run-gate.sh` | Runs the steps below and exits with the status of `run-gate`: 0 passed, 1 failed, 2 for an input that cannot be used or a step that wrote no report |

`run-gate.sh --candidate <folder> --cases <folder>/cases.json` runs these steps:

1. It refuses a worktree with any change, untracked files included, because the images and the record must match one commit. The candidate therefore lies outside the repository or in an ignored path, and the record of a previous run is committed before the next run.
2. It takes the commit with `git rev-parse HEAD` and creates `eval/releases/` when it is missing. An empty folder is not a change for git.
3. It builds both images from the worktree.
4. It runs the guardrail tests of `backend`, then those of `ai-service` in the `gate` image without network, each writing a JUnit XML file, named after its folder, into the work folder of the run. A failed test does not stop the script, so the gate records it; a step that writes no report, such as a failed migration, stops it with status 2.
5. It runs `supportiq-release run-gate` in the `gate` image without network, with the candidate, the folder of the cases, and the reports mounted read-only, and `eval/releases/` mounted writable.

Every container runs as the user who runs the script, so the record and the reports belong to them. Docker Desktop and Colima share only the home folder with their VM by default, so the reports go under `~/.cache/supportiq-gate`; set `GATE_WORK_DIR` to change it.

`publish-candidate` needs no torch, so it runs on the machine with `uv run` ([Run and test](#run-and-test)).

## Layout

| Path | Holds |
|---|---|
| `src/supportiq_release/kb_ingestion/domain/` | The rules of admission and of conflicts, with no file access |
| `src/supportiq_release/kb_ingestion/adapters/` | Reading the raw KB folder and the intent labels, and writing the output |
| `src/supportiq_release/candidate/domain/` | The spec of a candidate and the rules of its paths, with no file access |
| `src/supportiq_release/candidate/adapters/` | Reading the spec, checking the release ID, copying the sources, and writing and checking the manifest |
| `src/supportiq_release/gate/domain/` | The escalation cases, their approval, the comparison of a case with the responses, and the outcome of a gate run, with no file access |
| `src/supportiq_release/gate/adapters/` | Reading the cases, their approval, the facts of a candidate, and the JUnit XML files; the ports of the gate; running the cases; writing the record; publishing |
| `src/supportiq_release/files/` | Strict JSON files and new or empty output folders, for every command |
| `src/supportiq_release/errors.py` | `ReleaseCommandError`, the root of every error that the command raises on purpose ([PY-20](../../docs/rules/python.md#errors)); the command line prints its message and exits with status 2 |
| `src/supportiq_release/composition_root/` | The command line; `gate_commands.py` holds `run-gate` and `publish-candidate`, and `exit_statuses.py` the exit statuses |
| `gate/` | The Docker files and the script of a gate run ([Run in Docker](#run-in-docker)) |
| `typings/defusedxml/` | The types of the names of `defusedxml` that the command uses, because the package ships none |
| `tests/` | Unit tests of each module, with a fake application of a candidate for the gate; the test of KB v2; a candidate from the files of the repository; the test of `gate/check_locks.py` |

## Dependencies

Each dependency is justified here ([WF-27](../../docs/rules/workflow.md#dependencies)), and `uv.lock` pins every transitive dependency ([WF-28](../../docs/rules/workflow.md#dependencies)). The 78 packages that `uv.lock` shares with `ai-service/uv.lock` have the same versions.

### Runtime

| Name | Version | License | Why |
|---|---|---|---|
| supportiq-ai-service | The `ai-service/` of the same commit, as a path dependency | Not published | `verify_candidate` checks a candidate, and `build_candidate_application` builds it for the gate, with the code that serves it. Only the public modules of the introduction are imported, which a contract of import-linter checks (ADR-0021, Where the code of `main` goes, statement 1) |
| defusedxml | 0.7.1 | PSF-2.0 | Reads the JUnit XML files of the guardrail tests, refusing a document type, an entity, and an external reference, which `xml.etree` would read (ruff `S314`) |
| httpx | 0.28.1 | BSD-3-Clause | Sends the requests of each case to the application of the candidate through its ASGI transport, without opening a port. The version of `ai-service` |
| starlette | 1.10.0 | BSD-3-Clause | The type of the application of the candidate and of its routes, which the gate checks. The version of `ai-service` |

KB ingestion itself needs only the standard library.

### Development

Each development dependency has the version that `ai-service` uses, for the same reason.

| Name | Version | License | Why |
|---|---|---|---|
| pytest | 9.2.0 | MIT | The test runner ([ADR-0003](../../docs/decisions/0003-tech-stack.md)) |
| pytest-xdist | 3.8.0 | MIT | Parallel runs (TEST-15) |
| pytest-randomly | 5.0.0 | MIT | Random order (TEST-15) |
| pytest-socket | 0.8.1 | MIT | Blocks the network (TEST-16) |
| pytest-cov | 7.1.0 | MIT | Coverage from pytest (TEST-21) |
| coverage | 7.17.2 | Apache-2.0 | Branch coverage and its floors (TEST-21) |
| ruff | 0.17.4 | MIT | Format and lint (ADR-0003) |
| pyright (with the `nodejs` extra) | 1.1.414 | MIT | Strict types (ADR-0003) |
| import-linter | 2.16 | BSD-2-Clause | Layer boundaries (ARCH-11) |
| pip-audit | 2.10.1 | Apache-2.0 | Dependency vulnerabilities ([rules](../../docs/rules/README.md#enforcement)) |

These dependencies have a license outside the list of [WF-30](../../docs/rules/workflow.md#dependencies). Each one is also a dependency of `ai-service` or of `backend`:

- through `ai-service`: `certifi` (MPL-2.0), `numpy` (0BSD, Zlib, and CC0-1.0 for bundled parts), `regex` (Apache-2.0 AND CNRI-Python), `tqdm` (MPL-2.0 AND MIT), and `typing-extensions` (PSF-2.0). They wait for the approval of the project lead in the join PR, as `ai-service/README.md` (Dependencies) states;
- `defusedxml` (PSF-2.0), a runtime dependency here and a dependency of `pip-audit`, which the project lead accepted for `backend`.

The build backend is `uv_build`, from the same release as uv (MIT or Apache-2.0).

## Known limits

- Only some parts of the gate load the candidate. The 27 escalation cases and the checks on the candidate (the routes of contract 1.0.0, no case text in the logs, no LLM call) run on the application of the candidate, with its manifest loaded. The guardrail tests do not load it: those of `ai-service` check the service token and the packaged egress allow-list, those of `backend` serve `ai-service` from fakes, and no asset of the manifest changes what they check. They run at the commit that the record names, those of `ai-service` in the image of the gate. This reads ADR-0021 (Release and the offline evaluation gate, statement 3) as "where a test depends on what the manifest serves", and `candidate_scope` in the record states the same split.
- No CI job checks a published manifest yet, although ADR-0021 (Release and the offline evaluation gate, statement 2) asks CI to reject a manifest without a passing gate run or with a wrong checksum. `publish-candidate` writes the manifest next to the record for that check.
- The six cases that rest on the real model were written without a run of model `v1.0.0` ([Limits of the set](../../data/benchmarks/escalation/interim-v1/README.md#limits-of-the-set)). In the first gate run, all six matched.
- The formats of the spec and of the three outputs of ingestion are interim, and the readers of `ai-service` define the KB and mapping formats. A data contract replaces them ([ADR-0021, Follow-ups](../../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#follow-ups); [#21](https://github.com/ml-system-design-nhom-5/SupportIQ/issues/21)).
- Ingestion neither copies `last_reviewed_at` nor lists the versions without it, as the freshness rule of the [contracts v1 design, KB data contract](../../docs/design/contracts-v1.md#kb-data-contract-contractskb-contractmd) requires. KB v2 provides no `last_reviewed_at`, no policy area has a freshness rule yet, and ingestion admits no version of KB v2, so no output changes yet. The `tech-debt` issue for `source_review_overdue` adds both ([#22](https://github.com/ml-system-design-nhom-5/SupportIQ/issues/22)).
- `build-candidate` does not reserve the release ID. Until a gate run writes its record in `eval/releases/<release_id>/`, two candidates built with one ID and other sources can both exist; only one of them can then get a gate run.
- The acceptance of a quarantine names an issue, but it is not bound to the report it accepts, such as by the SHA-256 of the inputs, and a run with nothing to accept still records the URL.
- Sources are checked, then opened, so a link made in between would be followed. The candidate stays consistent, because the manifest lists the checksums of the bytes that were copied, and `verify_candidate` checks them.
- Release IDs are compared with their case, so on macOS two IDs that differ only in case name one folder of records.
- The rule of conflicts is a copy of the rule of `ai-service`. Their tests hold the same cases, but a change on one side needs the same change on the other.
- The intent labels are read from the layout of `contracts/schemas/IntentLabel.yaml` without a YAML library: one `enum:` line, then one line for each label, with two spaces before `- <label>`. A file with any other layout stops the run.
- `ai-service.yml` runs the checks of this project until `eval.yml` exists ([ADR-0021, CI](../../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#ci), statement 7).
