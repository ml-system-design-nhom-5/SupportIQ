# Release command

`supportiq-release` builds what a release of `ai-service` serves, and is the release command of [ADR-0021, Release and the offline evaluation gate](../../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#release-and-the-offline-evaluation-gate). It has two commands:

- `ingest-kb` admits or quarantines the KB document versions of a raw KB folder ([KB ingestion](#kb-ingestion));
- `build-candidate` copies the six assets into a new folder and writes the manifest of a candidate release, which no replica serves until the offline evaluation gate passes ([Candidate release](#candidate-release)).

The gate itself is not part of this command yet ([Known limits](#known-limits)).

It is a project of its own, apart from the evaluation code that `eval/` took over from `main`:

- ADR-0021 (Where the code of `main` goes, statement 3) makes the release command new code that uses none of the moved evaluation code.
- ADR-0021 (CI, statement 7) holds it to the rule level of `ai-service` now, while the moved code waits for the interim level of statements 8 and 9.

It reaches `ai-service` only through the formats of the release manifest and its assets, and never imports the internals of `ai-service` (ADR-0021, Where the code of `main` goes, statement 1).

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
  --output <new folder>
```

```bash
uv run --project eval/release pytest eval/release
```

The tests need no network and no `.env`. They read `data/raw/kb/v2/`, `contracts/schemas/IntentLabel.yaml`, `eval/kb-ingestion/v2/`, and `ai-service/prompts/grounded-v4/` without changing them.

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
| Dependency vulnerabilities | `uv export --locked --all-groups --no-emit-project --no-emit-local --format requirements-txt --output-file <temporary file>`, then `uv run --locked pip-audit --strict --disable-pip --require-hashes --requirement <temporary file>`, as in `backend` CI. `--no-emit-local` leaves out the path dependency on `ai-service`, which has no hash; its own dependencies are in the export |

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

`ai-service` reads the first two formats (`ai-service/README.md`, Asset formats). A data contract in `contracts/` replaces all three (ADR-0021, Follow-ups). Each file is UTF-8 JSON with two-space indents, LF line ends, and a final newline, and the same input always gives the same bytes.

Both commands write their files into a new hidden folder next to the output, `.<name>.partial-<random>`, and move it to the output only once every file is written. A run that fails for any reason removes that folder, so the output is complete or absent, never half written. A process that is killed can leave the hidden folder behind; no command reads it.

A quarantined record is named by its position in the KB file, from 0, and by its document ID and version only when they are valid identifiers: any other value could hold text of the KB.

### KB v2

[`../kb-ingestion/v2/`](../kb-ingestion/v2/) holds the output for `data/raw/kb/v2/`. It admits 0 document versions and quarantines all 17 ([ADR-0021, KB ingestion](../../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#kb-ingestion), statement 5):

- the 14 `POL-…` documents: `missing_field` for `policy_key`. `POL-ORD-003` and `POL-SHIP-001` also get `unknown_intent`, because their `supported_intents` name `edit_order`, `change_shipping_address`, and `delivery_options`, which are not labels of the contract;
- the 3 `b1000000-…` documents: `not_in_release`, and `invalid_field` for `version`, which is a number.

The run fails until the issue that reviews the quarantine accepts it (DATA-13). A test checks that the committed files equal a new run, and that the raw folder keeps its SHA-256.

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

## Layout

| Path | Holds |
|---|---|
| `src/supportiq_release/kb_ingestion/domain/` | The rules of admission and of conflicts, with no file access |
| `src/supportiq_release/kb_ingestion/adapters/` | Reading the raw KB folder and the intent labels, and writing the output |
| `src/supportiq_release/candidate/domain/` | The spec of a candidate and the rules of its paths, with no file access |
| `src/supportiq_release/candidate/adapters/` | Reading the spec, checking the release ID, copying the sources, and writing and checking the manifest |
| `src/supportiq_release/files/` | Strict JSON files and new or empty output folders, for both commands |
| `src/supportiq_release/errors.py` | `ReleaseCommandError`, the root of every error that the command raises on purpose ([PY-20](../../docs/rules/python.md#errors)); the command line prints its message and exits with status 2 |
| `src/supportiq_release/composition_root/` | The command line |
| `tests/` | Unit tests of each module; the test of KB v2; a candidate from the files of the repository |

## Dependencies

Each dependency is justified here ([WF-27](../../docs/rules/workflow.md#dependencies)), and `uv.lock` pins every transitive dependency ([WF-28](../../docs/rules/workflow.md#dependencies)). The 78 packages that `uv.lock` shares with `ai-service/uv.lock` have the same versions.

### Runtime

| Name | Version | License | Why |
|---|---|---|---|
| supportiq-ai-service | The `ai-service/` of the same commit, as a path dependency | Not published | `verify_candidate` checks a candidate with the code that serves it. Only `supportiq_ai_service.release.manifest` is imported, which a contract of import-linter checks (ADR-0021, Where the code of `main` goes, statement 1) |

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

These transitive dependencies have a license outside the list of [WF-30](../../docs/rules/workflow.md#dependencies). Each one is also a dependency of `ai-service` or of `backend`:

- through `ai-service`: `certifi` (MPL-2.0), `numpy` (0BSD, Zlib, and CC0-1.0 for bundled parts), `regex` (Apache-2.0 AND CNRI-Python), `tqdm` (MPL-2.0 AND MIT), and `typing-extensions` (PSF-2.0). They wait for the approval of the project lead in the join PR, as `ai-service/README.md` (Dependencies) states;
- through `pip-audit`: `defusedxml` (PSF-2.0), which the project lead accepted for `backend`.

The build backend is `uv_build`, from the same release as uv (MIT or Apache-2.0).

## Known limits

- The offline evaluation gate is not part of the command yet: it waits for the routing values and the model of the first release, the interim escalation cases ([ADR-0021, Exception to TEST-26](../../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#exception-to-test-26)), and a way to build `ai-service` from a candidate in the same process. Until then, no candidate gets a gate run, `eval/releases/` does not exist, and `build-candidate` stops with `release_records_folder_missing` outside the tests.
- The formats of the spec and of the three outputs of ingestion are interim, and the readers of `ai-service` define the KB and mapping formats. A data contract replaces them ([ADR-0021, Follow-ups](../../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#follow-ups)).
- Ingestion neither copies `last_reviewed_at` nor lists the versions without it, as the freshness rule of the [contracts v1 design, KB data contract](../../docs/design/contracts-v1.md#kb-data-contract-contractskb-contractmd) requires. KB v2 provides no `last_reviewed_at`, no policy area has a freshness rule yet, and ingestion admits no version of KB v2, so no output changes yet. The `tech-debt` issue for `source_review_overdue` adds both.
- The issue that accepts the quarantine of KB v2 does not exist yet, so the committed report has no `quarantine_accepted_in`, and ADR-0021 (Validation) is not met yet. Once the issue exists, the report is written again with `--accepted-quarantine`, and `tests/integration/test_kb_v2.py` names the issue URL as a constant and expects exit status 0.
- `build-candidate` does not reserve the release ID. Until a gate run writes its record in `eval/releases/<release_id>/`, two candidates built with one ID and other sources can both exist; only one of them can then get a gate run.
- The acceptance of a quarantine names an issue, but it is not bound to the report it accepts, such as by the SHA-256 of the inputs, and a run with nothing to accept still records the URL.
- Sources are checked, then opened, so a link made in between would be followed. The candidate stays consistent, because the manifest lists the checksums of the bytes that were copied, and `verify_candidate` checks them.
- Release IDs are compared with their case, so on macOS two IDs that differ only in case name one folder of records.
- The rule of conflicts is a copy of the rule of `ai-service`. Their tests hold the same cases, but a change on one side needs the same change on the other.
- The intent labels are read from the layout of `contracts/schemas/IntentLabel.yaml` without a YAML library: one `enum:` line, then one line for each label, with two spaces before `- <label>`. A file with any other layout stops the run.
- `ai-service.yml` runs the checks of this project until `eval.yml` exists ([ADR-0021, CI](../../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#ci), statement 7).
