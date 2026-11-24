# Release command

`supportiq-release` builds what a release of `ai-service` serves, runs the offline evaluation gate on it, publishes it, and distributes it. It is the release command of [ADR-0021, Release and the offline evaluation gate](../../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#release-and-the-offline-evaluation-gate), with seven commands:

- `ingest-kb` admits or quarantines the KB document versions of a raw KB folder ([KB ingestion](#kb-ingestion));
- `build-candidate` copies the six assets into a new folder and writes the manifest of a candidate release, which no replica serves until the offline evaluation gate passes ([Candidate release](#candidate-release));
- `run-gate` runs the offline evaluation gate on a candidate and records the run ([The offline evaluation gate](#the-offline-evaluation-gate));
- `publish-candidate` copies a candidate whose gate run passed into a release folder and links the run in its manifest ([Publish](#publish));
- `pack-release`, `download-release`, and `check-pinned-release` write the release archive of a published release and the pinned file, download a release from its GitHub Release into a cache, and check the pinned file against GitHub ([Release download](#release-download), [ADR-0030](../../docs/decisions/0030-release-archives-and-the-modal-function-of-ai-service.md)).

The gate run of `release-2026-11-18-02` passed, and its record is [`../releases/release-2026-11-18-02/gate-run.json`](../releases/release-2026-11-18-02/gate-run.json). The first run, of `release-2026-11-18-01`, failed on two defects of the gate itself, fixed in `86f73df`; its record stays in [`../releases/release-2026-11-18-01/`](../releases/release-2026-11-18-01/gate-run.json), and that release ID is never used again ([DATA-48](../../docs/rules/data-and-ml.md#evaluation-and-reporting), [ARCH-40](../../docs/rules/architecture.md#versioned-assets)). The gate run of `release-2026-11-21-01` also passed ([record](../releases/release-2026-11-21-01/gate-run.json)), but that candidate has no published manifest, and its ID is never used again either. The gate run of `release-2026-11-23-01`, the first release that serves KB documents, passed with the case set `escalation/interim-v2` ([record](../releases/release-2026-11-23-01/gate-run.json)), and the pinned file names that release.

It is a project of its own, apart from the evaluation code that `eval/` took over from `main`:

- ADR-0021 (Where the code of `main` goes, statement 3) makes the release command new code that uses none of the moved evaluation code.
- ADR-0021 (CI, statement 7) holds it to the rule level of `ai-service` now, while the moved code waits for the interim level of statements 8 and 9.

It imports only public modules of `ai-service`, never their internals (ADR-0021, Where the code of `main` goes, statement 1), and a contract of import-linter checks this:

- `app.release.manifest`, to check a candidate and a published release;
- in the gate only, `app.composition_root`, `intent`, `retrieval`, and `drafting`, to build the application of a candidate with the ports of the gate.

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

```bash
uv run --project eval/release supportiq-release pack-release \
  --release-folder <published release folder> \
  --release-records eval/releases \
  --output <new folder outside the repository> \
  --pin
```

```bash
uv run --locked --project eval/release supportiq-release download-release [--release <release_id>] [--yes]
```

```bash
uv run --locked --project eval/release supportiq-release check-pinned-release [--remote]
```

`run-gate` itself needs torch, so `run-gate.sh` runs it in Docker ([Run in Docker](#run-in-docker)). The other commands need no torch.

```bash
uv run --project eval/release pytest eval/release
```

The tests need no network, no `.env`, and no torch: the gate runs on a fake application of a candidate, the routes of the real application of `ai-service` are read from its `create_app` with fake ports, through the FastAPI that `ai-service` locks, and the release download talks to a fake GitHub through an `httpx.MockTransport`. They read `data/raw/kb/v2/`, `contracts/schemas/IntentLabel.yaml`, `eval/kb-ingestion/v2/`, `data/benchmarks/escalation/interim-v1/`, and `ai-service/prompts/grounded-v4/` without changing them.

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

### KB v2.1

[`../kb-ingestion/v2.1/`](../kb-ingestion/v2.1/) holds the output for `data/raw/kb/v2.1/`, the release `current-policies-v1.1`. It admits all 14 `POL-…` document versions, quarantines none, and lists no conflict and no released version that the KB file lacks. Each version has its own `policy_key`, and its intents are labels of the contract ([`data/raw/kb/v2.1/README.md`](../../data/raw/kb/v2.1/README.md), the manifest of the folder and its approved changes).

Nothing is quarantined, so the run needs no `--accepted-quarantine`, and the report holds no `quarantine_accepted_in`. A test runs the command, checks that it exits with status 0 and that the committed files equal the new run, and that the raw folder keeps its SHA-256. It also checks that the mapping and the report hold no text of the KB, and that no text names the brand of KB v2.

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

`build-candidate` reads a spec, copies the six assets that it names into a new or empty folder, writes the manifest of a candidate, and checks the candidate with `verify_candidate` of `app.release.manifest`, the one module of `ai-service` that it imports ([`ai-service/README.md`, Release manifest](../../ai-service/README.md#release-manifest)). The candidate has `"gate_run": null`, so `ai-service serve` refuses it, and only the offline evaluation gate may link a passing run ([DATA-57](../../docs/rules/data-and-ml.md#models-and-artifacts)).

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

For KB v2, the sources of `kb` and `mapping` are `eval/kb-ingestion/v2/kb.json` and `eval/kb-ingestion/v2/document-intents.json`, and the source of `prompts` is a folder of `ai-service/prompts/`. For KB v2.1, they are the same files of `eval/kb-ingestion/v2.1/`. The source of `index` is then a folder outside the repository with `index.json` of `ai-service/index/bge-small-en-v1.5-main-untuned-v1-kb-v2.1/`, because the index names its KB, and the same six files of the encoder in `encoder/` ([ADR-0027](../../docs/decisions/0027-retrieval-index-configuration-of-the-first-release.md#the-configuration), statements 2 and 4).

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
2. The cases have the format of their README, and no case ID is given twice. Each request holds a message; each recommendation, draft status, and reason code is a value of contract 1.0.0; and each injected distribution lists intent labels once each, most likely first, with probabilities that add up to at most 1 and stay above the equal share of the rest. A case whose `llm_called` is `true` lists `llm_sources_include`, at least one document version, and `llm_sources_exclude`, each version once and never in both, as `{"document_id": …, "version": …}`; no other case lists either ([gate design for a release with KB documents](../../docs/design/gate-for-a-release-with-kb-documents.md#search-in-the-draft-cases)). A refusal names the case when it can.
3. `approval.json`, next to `cases.json`, has its format, is for the same set, is `frozen` with `approved_by` and `approved_on`, and covers the SHA-256 of `cases.json` as it is ([Approval record](../../data/benchmarks/escalation/interim-v1/README.md#approval-record)).
4. `label` and each field of `written_for` match the candidate: contract 1.0.0, the model version, the routing version, the KB version, and the number of KB document versions. The message names each field that differs.
5. Each JUnit XML file of the guardrail tests is the report of its folder: a regular file whose every `testsuite` has the name of the folder (`ai_service_guardrails` or `backend_guardrails`, which `run-gate.sh` sets with `-o junit_suite_name`), holds `tests`, `failures`, `errors`, and `skipped` as integers of at least 0, and holds one `testcase` for each test, each in `tests.integration.guardrails`. A document type, an entity, and an external reference are refused. A report that is missing or cannot be read therefore gives no record; `run-gate.sh` produces both reports or stops before `run-gate`.
6. `--release-records` names an existing folder that holds no entry named by the release ID. `--git-commit` takes the 40 lowercase hexadecimal characters of a commit.

### The run

`run-gate` builds the application of the candidate in its own process with `build_candidate_application` of `ai-service`, and the ports of `gate/adapters/gate_ports.py`:

- the intent model and the search of the candidate, except for a case that injects an intent distribution or a failure ([How the gate runs a case](../../data/benchmarks/escalation/interim-v1/README.md#how-the-gate-runs-a-case));
- an LLM step that records each call and fails it with `llm_unavailable`, so the gate never calls a provider ([ADR-0021, CI](../../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#ci), statement 2). Of each call it keeps only the document versions (`document_id`, `version`) of the policy sources, never their text. The candidate uses this step without the retries of `ai-service`, so a draft makes at most one call.

The settings come from the environment of the process, as for `serve`. The command line sets the ones of the gate once, before it builds the application: a service token made for the run, and LLM settings that no call reads. The manifest is an argument, not a setting. Each case sends its request to `createAnalysis` and then to `createDraft` through an ASGI transport, inside the lifespan of the application, so no port is opened, and every field of `expected` is compared with both responses. For a case that expects a draft, every version of `llm_sources_include` must reach the LLM step during `createDraft`, and no version of `llm_sources_exclude` may. The search of the candidate stays real, so other versions may reach it too. `required_reason_codes` and `no_other_reason_codes` hold for both operations, and `createAnalysis` never carries `llm_unavailable`, so a case that expects a draft states the failed call with `draft_status` `llm_unavailable`, does not require that code, and sets `no_other_reason_codes` to `false`. The fields of an outcome are read only from a `200` body, and the problem type only from a Problem Details body, whose `status` is the HTTP status and never the status of a draft.

The checks on the candidate are:

- `routes_are_those_of_contract_1_0_0`: the application serves exactly the six routes of contract 1.0.0, none of which performs a transaction (FR-06). FastAPI keeps each included router as one route, so the gate reads the routes inside it, with the prefix of the inclusion. It also reads the routes that FastAPI serves after all others, such as those that `frontend()` adds. A route of another kind, such as a websocket route or a frontend, fails the check;
- `no_case_text_in_the_logs`: no log line holds the message of a case or a placeholder in it ([LOG-29](../../docs/rules/logging-and-observability.md#privacy-in-telemetry));
- `llm_calls_as_expected`: the LLM step received one call for each case whose `llm_called` is `true`, and no other call. For `interim-v1`, whose cases all expect no call, that means no call at all.

The gate passes only when every case and every check passes, and each folder of guardrail tests ran at least one test with no failure, no error, and no skip, because a skipped guardrail test is not a pass ([TEST-20](../../docs/rules/testing.md#flaky-and-skipped-tests)). Which parts load the candidate is in [Known limits](#known-limits).

### The record

Each run, passed or failed, writes `eval/releases/<release_id>/gate-run.json` into a folder that it creates exclusively, so a release ID gets one gate run ([ARCH-40](../../docs/rules/architecture.md#versioned-assets)). The record is in `supportiq-gate-run/interim-2` and holds identifiers, versions, checksums, counts, and codes, never text of a message or of the KB. `interim-1`, the format of the record of `release-2026-11-18-02`, named the check of the LLM step `no_llm_call` and held no document version.

| Field | Holds |
|---|---|
| `format` | Always `supportiq-gate-run/interim-2` |
| `run_id`, `release_id` | The release ID of the candidate, which the run takes as its ID |
| `manifest_sha256` | The SHA-256 of the manifest file of the candidate |
| `git_commit` | The commit of the repository that the run used |
| `escalation_cases` | The name of the set, the SHA-256 of `cases.json`, the number of cases, the number of each kind, and for each case its ID, its rule, its kind, the injected failure if any, whether it passed, each field that did not match, as `<operation>.<field>`, and what the candidate gave for it: an HTTP status, a value of a closed set of the contract, reason codes, or, for `createDraft.llm_sources`, the versions that reached the LLM step as `<document_id>@<version>`, sorted, with `null` for an absent value or list, `empty` for an empty list, and `other` for a value outside the set, never its text |
| `candidate_checks` | Each check on the candidate, whether it passed, and what made it fail: each route outside contract 1.0.0 as `+<method> <path>` and each missing one as `-<method> <path>`, the IDs of the cases whose text was logged, or the IDs of the cases whose call of the LLM step differs from what they expect, with `calls:<number>` when the total differs |
| `candidate_scope` | The parts that run on the candidate, the parts that do not, and why |
| `guardrails` | For each folder of guardrail tests: the tests, failures, errors, and skips, the test classes that ran, and whether it passed |
| `llm` | The calls that the LLM step received, and a sentence: that no call was made, that each call came from a case that expects one, or that a call that no case expects fails the gate |
| `test_26` | The TEST-26 item on the shared scenario set, stated as not met ([Exception to TEST-26](../../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#exception-to-test-26), statement 3) |
| `known_gaps` | While the KB of the candidate holds no document version: the three gaps of ADR-0021 (Release and the offline evaluation gate, statement 4) and the untuned routing of [ADR-0025](../../docs/decisions/0025-routing-configuration-of-the-first-release.md). Otherwise: the first two gaps of ADR-0021, the untuned routing, the untuned minimum similarity of the index ([ADR-0027](../../docs/decisions/0027-retrieval-index-configuration-of-the-first-release.md)), and retrieval and grounding as a first baseline outside the gate ([gate design, DATA-57, item 2](../../docs/design/gate-for-a-release-with-kb-documents.md#data-57-item-2-against-release-2026-11-18-02)) |
| `outcome` | `passed` or `failed` |

The kind of a case is what its outcome rests on: `real_model`, `injected_distribution`, `injected_failure`, or `staff_choice`. Of the 27 cases of `interim-v1`, 6 rest on the real model, 17 on an injected distribution, 2 on an injected failure, and 2 on an intent that staff chose.

`run-gate` exits with status 0 when the gate passed and 1 when it failed; the record is written either way. It prints the release ID, the number of cases and of failed cases, the outcome, and the path of the record. Any other failure of any command, such as a record that cannot be written, prints only the name of its type and exits with status 2, so status 1 always means a gate run that failed.

### Publish

`publish-candidate` checks the approval of the cases as `run-gate` does, then reads the record of the release ID. It stops with exit status 2, names the problem, and leaves the output as it was when:

- the record is not a JSON object in `supportiq-gate-run/interim-2`, or did not pass;
- the record names another release ID or another SHA-256 of the manifest;
- the record ran other bytes of the cases;
- the release ID is already published: `eval/releases/<release_id>/release-manifest.json` exists;
- `--release-records` is not a relative path inside the repository, such as `eval/releases`, which the manifest uses to link the record.

It then copies every file of the candidate into a staging folder next to the output, writes the manifest with `gate_run` (the run ID of the record, `passed`, the path of the record, and its SHA-256), checks it with `verify_release`, and moves the folder to the output. Only then does it write the same manifest next to the record, which links the release ([ADR-0021, Release and the offline evaluation gate](../../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#release-and-the-offline-evaluation-gate), statement 1). A move that fails leaves neither the output nor the link, so the command can run again ([ERR-04](../../docs/rules/errors-and-reliability.md#handling-rules)).

A published release reaches the Modal deploy and the local run through its release archive on GitHub. The steps after `publish-candidate` keep this order, so that every `git pull` finds the archive of the pinned release on GitHub ([ADR-0030, Release archives](../../docs/decisions/0030-release-archives-and-the-modal-function-of-ai-service.md#release-archives), statement 5):

1. Commit the record and the manifest that `publish-candidate` wrote into `eval/releases/<release_id>/`.
2. `pack-release --pin` writes `<release_id>.tar.gz` outside the repository, and the pinned file ([Release download](#release-download)).
3. In the browser, draft a GitHub Release whose tag is the release ID, on a commit that holds the manifest of step 1, attach the archive, and publish it. The form preselects `main`: choose the branch that holds that commit, and check the tag as the [deploy README, Publish a release](../../deploy/README.md#publish-a-release), states. Immutable releases were off when both releases were uploaded. They stay off by the project lead's decision of 2026-11-23, until the system has taken shape, and [ADR-0018, Follow-ups](../../docs/decisions/0018-hosting-of-ai-service-on-modal.md#follow-ups) stays open until then.
4. `download-release --release <release_id> --yes` downloads the archive from GitHub and runs every check of the download, which proves the upload end to end.
5. `check-pinned-release --remote` checks the pinned file against GitHub.
6. Only then commit and push the pinned file.

An uploaded archive is never replaced or deleted. A wrong one stays, and the fix is a new release ID ([DATA-36](../../docs/rules/data-and-ml.md#models-and-artifacts)). To go back to the previous release, revert the commit of the pinned file: its archive is still on GitHub.

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

## Release download

A published release leaves the repository as one release archive, the only asset of a GitHub Release whose tag is the release ID. The Modal deploy and the local run download it with the same command, and the manifest in git is the source of trust ([ADR-0030](../../docs/decisions/0030-release-archives-and-the-modal-function-of-ai-service.md); [release download and Modal deploy design](../../docs/design/release-download-and-modal-deploy.md)). The publish order is in [Publish](#publish).

### The release archive

`pack-release --release-folder <folder> --release-records eval/releases --output <new folder> [--pin]` writes `<output>/<release_id>.tar.gz`:

- It packs only a published release: `verify_release` passes on `<folder>/release-manifest.json`, and that manifest is byte for byte `eval/releases/<release_id>/release-manifest.json`. Otherwise it exits with status 2 and writes nothing.
- The archive holds `release-manifest.json` and every file of the manifest, at their paths, and nothing else: no folder entry and no link.
- It is reproducible: members sorted by path, each a regular file in the ustar format with mode `0644`, owner and group 0, empty owner and group names, and modification time 0; gzip with modification time 0, no file name, and level 9. The same files with the same versions of Python and zlib give the same bytes.
- It goes through a staging folder, so the output holds the whole archive or nothing.
- It prints `release_id=<id> archive=<path> archive_size_bytes=<n>` on standard output.

### The pinned file

`eval/releases/pinned-release.txt` names the release that the local run and the Modal deploy take by default, and the size of its archive. It holds exactly two lines, each ended by LF, in ASCII, without comments or spaces:

```text
release_id=<release_id>
archive_size_bytes=<the size that pack-release prints>
```

- `release_id` has the pattern of `release_id` in the contracts, and `eval/releases/<release_id>/release-manifest.json` is a published manifest of that ID.
- `archive_size_bytes` is a decimal number without a leading zero, of at most 10 digits, from 1 to 2,147,483,647.
- `.gitattributes` sets `text eol=lf` for it, so every checkout keeps its LF line ends, whatever `core.autocrlf` says. A CR in it stops the command.
- Only `pack-release --pin` writes it, both lines at once, through a temporary file that it renames over the old one. Without `--pin`, the file stays as it is, for example when an older release is packed again. Never edit it by hand.
- "Newest" means what this file says, never an order of release IDs or GitHub's latest release ([CON-15](../../docs/rules/contracts.md#api-conventions)).

### Download

`download-release [--release <release_id>] [--release-records eval/releases] [--yes]` puts a release into the cache and prints its folder:

1. The release is `--release`, checked against the pattern of a release ID, or the one of the pinned file. Its published manifest must be in `eval/releases/`.
2. A release that is already in the cache, with the manifest of git and with `verify_release` passing, is a cache hit: no request, no question, status 0. A cached folder that fails its check is never repaired or deleted: the command exits with status 6, names the folder, and says to remove it to download the release again.
3. The command looks up the GitHub Release of the tag. It must have exactly one uploaded asset, `<release_id>.tar.gz`. Without `--release`, its size must also be the one in the pinned file.
4. It checks the free space of the nearest folder of the cache that exists, for the archive and the unpacked files.
5. It prints the plan on standard error (the release ID, the size, and the folder) and asks `Proceed? [y/N]`. Only `y` goes on. `--yes` answers for it. Without a terminal on standard input and without `--yes`, it exits with status 4 before any request, so it never waits.
6. Only then does it create the cache folder, stream the archive into a hidden partial file, and unpack it into a hidden staging folder. It never calls `extractall`: every member must be a regular file named in the manifest of git, appear once, and have exactly the size that the manifest states. Then the unpacked manifest must equal the one in git, and `verify_release` must pass.
7. It renames the staging folder to `<cache>/<release_id>/`, removes the archive, and prints the absolute path of that folder.

On status 0, standard output holds only that path. Every other message goes to standard error and never holds the token. A failure removes the partial archive and the staging folder, Ctrl+C included, so the cache gets no new release. A declined run, or one that fails before the answer, creates nothing. A failure after the answer leaves at most the empty cache folder and the parents that it needed, when the cache folder did not exist before.

### Settings

| Name | Default | Meaning |
|---|---|---|
| `SUPPORTIQ_RELEASE_TOKEN` | Not set | Optional, Secret ([SEC-01](../../docs/rules/security-and-privacy.md#data-classification)). A GitHub token sent as `Authorization: Bearer` to `api.github.com` only, for a higher rate limit. The repository is public, so no token is needed. It is never printed or written |
| `SUPPORTIQ_RELEASE_CACHE` | `$HOME/.cache/supportiq/releases` | The cache folder, an absolute path. The default ignores `XDG_CACHE_HOME`, so the bash of the local run computes the same path. In a container, set it to the path on the host |
| `HOME` | From the system | Read only for the default of the cache, and then an absolute path |

An empty value counts as not set. A value that breaks its rule stops the command with status 2 and a message that names the setting, never its value. The cache and `HOME` are checked only when a cache is needed, so `check-pinned-release` uses only the token and never checks the cache or `HOME`.

### HTTP

- Every client has `trust_env=False`, so no proxy setting and no `.netrc` of the environment is used, and `follow_redirects=False`, so the command follows each redirect itself. Connection timeout 10 s, read timeout 60 s for each read, no total timeout, and no retry ([ERR-12](../../docs/rules/errors-and-reliability.md#retries)): run the command again.
- Every request sends `Accept-Encoding: identity`, `X-GitHub-Api-Version: 2026-03-10`, and `User-Agent: supportiq-release`. The archive is counted as raw bytes and stops at its announced size.
- The asset request follows at most 3 redirects, only to `https://`. The token goes only with the first request, whatever the host of a redirect.

### Exit statuses

| Status | Meaning | Commands |
|---|---|---|
| 0 | Done | Every command |
| 1 | A gate run that ran and failed | `run-gate` |
| 2 | An input that cannot be used, a file that cannot be written, too little free space, a token that GitHub refuses (`token_refused`: a `401` of a request that sent it; fix or unset `SUPPORTIQ_RELEASE_TOKEN`), or an unexpected error, which prints only its type | Every command |
| 3 | A quarantine that waits for an accepting issue | `ingest-kb` |
| 4 | Declined: the answer was not `y`, or no terminal and no `--yes` | `download-release` |
| 5 | Network: a connection error, a timeout, a `5xx`, a rate limit (`403` or `429`), another unexpected status such as a `401` without a token, or a redirect that is not allowed. Run the command again | `download-release`, `check-pinned-release --remote` |
| 6 | Check failed: no published GitHub Release for the tag, not exactly one uploaded asset of that name, another size, a member that is not allowed or is missing, a manifest that differs from git, `verify_release` refuses, a cached folder fails its check, or a pinned file that breaks its format for `check-pinned-release` | `download-release`, `check-pinned-release` |

### The check of the pinned file

`check-pinned-release [--release-records eval/releases] [--remote]` checks the format of the pinned file and that its release has a published manifest in `eval/releases/`, without a request. With `--remote`, it also checks on GitHub that the tag has a published GitHub Release with exactly one uploaded asset, `<release_id>.tar.gz`, of the pinned size. It downloads nothing.

The CI job `ai-service-release-command` runs it on every push to `main` or a `build/**` branch and on every pull request to `main`, with `--remote` only when the pinned file differs from the base commit or the base is missing or cannot be fetched, so the anonymous rate limit of GitHub is not a risk for other changes ([repository checks, What runs where](../../docs/guides/repository-checks.md#what-runs-where)).

## Layout

| Path | Holds |
|---|---|
| `src/supportiq_release/kb_ingestion/domain/` | The rules of admission and of conflicts, with no file access |
| `src/supportiq_release/kb_ingestion/adapters/` | Reading the raw KB folder and the intent labels, and writing the output |
| `src/supportiq_release/candidate/domain/` | The spec of a candidate and the rules of its paths, with no file access |
| `src/supportiq_release/candidate/adapters/` | Reading the spec, checking the release ID, copying the sources, and writing and checking the manifest |
| `src/supportiq_release/gate/domain/` | The escalation cases, their approval, the comparison of a case with the responses, and the outcome of a gate run, with no file access |
| `src/supportiq_release/gate/adapters/` | Reading the cases, their approval, the facts of a candidate, and the JUnit XML files; the ports of the gate; running the cases; writing the record; publishing |
| `src/supportiq_release/distribution/domain/` | The text of the pinned file, the members that an archive may hold, the choice of the release asset, and the size checks, with no file or network access |
| `src/supportiq_release/distribution/adapters/` | The GitHub client over httpx, the archive writer and reader over `tarfile` and `gzip`, the pinned file, the release cache, the published manifest, and the question on the terminal |
| `src/supportiq_release/files/` | Strict JSON files, new or empty output folders with the hidden paths of their staging, and the message of a release that `verify_release` refuses, for every command |
| `src/supportiq_release/errors.py` | `ReleaseCommandError`, the root of every error that the command raises on purpose ([PY-20](../../docs/rules/python.md#errors)); the command line prints its message and exits with status 2. Its three subclasses for the release download exit with their own status: `DownloadDeclinedError` 4, `NetworkFailedError` 5, and `ReleaseCheckFailedError` 6 |
| `src/supportiq_release/composition_root/` | The command line; `gate_commands.py` holds `run-gate` and `publish-candidate`, `distribution_commands.py` the commands of the release download, `download_settings.py` their settings, and `exit_statuses.py` the exit statuses |
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
| httpx | 0.28.1 | BSD-3-Clause | Sends the requests of each case to the application of the candidate through its ASGI transport, without opening a port, and the requests of the release download to GitHub. The version of `ai-service` |
| pydantic | 2.14.3 | MIT | The types of the settings of the release download, with the token as `SecretStr` ([PY-44](../../docs/rules/python.md#settings)). Already locked through `ai-service`, and declared directly because the command imports it. The version of `ai-service` |
| pydantic-settings | 2.16.2 | MIT | Reads the settings of the release download once from the environment into one settings class ([PY-43](../../docs/rules/python.md#settings)). Already locked through `ai-service`, and declared directly for the same reason. The version of `ai-service` |
| starlette | 1.10.0 | BSD-3-Clause | The type of the application of the candidate and of its routes, which the gate checks. The version of `ai-service` |

KB ingestion itself needs only the standard library, and the release archive only `tarfile` and `gzip`.

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

- Only some parts of the gate load the candidate. The escalation cases and the checks on the candidate (the routes of contract 1.0.0, no case text in the logs, the LLM calls that the cases expect) run on the application of the candidate, with its manifest loaded. The guardrail tests do not load it: those of `ai-service` check the service token and the packaged egress allow-list, those of `backend` serve `ai-service` from fakes, and no asset of the manifest changes what they check. They run at the commit that the record names, those of `ai-service` in the image of the gate. This reads ADR-0021 (Release and the offline evaluation gate, statement 3) as "where a test depends on what the manifest serves", and `candidate_scope` in the record states the same split.
- CI checks only part of a published manifest, although ADR-0021 (Release and the offline evaluation gate, statement 2) asks CI to reject a manifest without a passing gate run or with a wrong checksum. The step for the pinned file checks that the manifest of the pinned release is a published manifest of its ID, with a gate run ([The check of the pinned file](#the-check-of-the-pinned-file)). No job checks the other manifests, the record of the run, or the checksums, because the files of a release are not in git. `publish-candidate` writes the manifest next to the record for that check.
- The six cases that rest on the real model were written without a run of model `v1.0.0` ([Limits of the set](../../data/benchmarks/escalation/interim-v1/README.md#limits-of-the-set)). In the first gate run, all six matched.
- The case format requires `without_kb_evidence`, which `interim-v1` uses to say how an outcome holds while the release serves no KB document. A set written for a KB with documents uses the same field to say why its outcome holds with that KB, so the name says the opposite of its use there. The reader keeps the field; the next format of the case set renames it.
- The formats of the spec and of the three outputs of ingestion are interim, and the readers of `ai-service` define the KB and mapping formats. A data contract replaces them ([ADR-0021, Follow-ups](../../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#follow-ups); [#21](https://github.com/ml-system-design-nhom-5/SupportIQ/issues/21)).
- Ingestion neither copies `last_reviewed_at` nor lists the versions without it, as the freshness rule of the [contracts v1 design, KB data contract](../../docs/design/contracts-v1.md#kb-data-contract-contractskb-contractmd) requires. KB v2 provides no `last_reviewed_at`, no policy area has a freshness rule yet, and ingestion admits no version of KB v2, so no output changes yet. The `tech-debt` issue for `source_review_overdue` adds both ([#22](https://github.com/ml-system-design-nhom-5/SupportIQ/issues/22)).
- `build-candidate` does not reserve the release ID. Until a gate run writes its record in `eval/releases/<release_id>/`, two candidates built with one ID and other sources can both exist; only one of them can then get a gate run.
- The acceptance of a quarantine names an issue, but it is not bound to the report it accepts, such as by the SHA-256 of the inputs, and a run with nothing to accept still records the URL.
- Sources are checked, then opened, so a link made in between would be followed. The candidate stays consistent, because the manifest lists the checksums of the bytes that were copied, and `verify_candidate` checks them.
- Release IDs are compared with their case, so on macOS two IDs that differ only in case name one folder of records.
- The rule of conflicts is a copy of the rule of `ai-service`. Their tests hold the same cases, but a change on one side needs the same change on the other.
- The intent labels are read from the layout of `contracts/schemas/IntentLabel.yaml` without a YAML library: one `enum:` line, then one line for each label, with two spaces before `- <label>`. A file with any other layout stops the run.
- `ai-service.yml` runs the checks of this project until `eval.yml` exists ([ADR-0021, CI](../../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#ci), statement 7). Its step for the pinned file moves there with issue [#34](https://github.com/ml-system-design-nhom-5/SupportIQ/issues/34).
- The release download ignores proxy settings and `.netrc` (`trust_env=False`), so it does not work where a proxy is the only way out.
- The download is the whole archive in one request, and it cannot resume: a failed run starts again. No request is retried.
- A process that is killed, not stopped with Ctrl+C, can leave a hidden entry in the cache: `.<release_id>.partial-<hex>` or `.<release_id>.tar.gz.partial-<hex>`. No command reads it. Remove it by hand.
- A cache hit hashes every file of the release, 385 MiB for `release-2026-11-18-02`.
