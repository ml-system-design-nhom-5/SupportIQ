# ai-service

`ai-service` is the SupportIQ component that runs the AI pipeline for `backend`: intent classification, retrieval of KB document versions, the routing recommendation, and LLM drafting with citations ([ADR-0001](../docs/decisions/0001-system-architecture.md), [ADR-0005](../docs/decisions/0005-intent-independent-retrieval.md)). It serves [`contracts/ai-service.openapi.yaml`](../contracts/ai-service.openapi.yaml) 1.0.0. It is stateless: it has no database and owns no tickets, sessions, accounts, orders, or per-ticket state. `backend` is its only caller and sends it pseudonymized text and order context without identifiers ([ADR-0010](../docs/decisions/0010-pseudonymization-and-egress-control.md)). The AI only suggests: `ai-service` never sends a reply and never performs a transaction (FR-04, FR-06). It runs on Modal ([ADR-0018](../docs/decisions/0018-hosting-of-ai-service-on-modal.md)). The join with the AI and ML code of `main` builds it from that code ([ADR-0021, Where the code of `main` goes](../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#where-the-code-of-main-goes)). This README fixes its layout ([ARCH-16](../docs/rules/architecture.md)); the features of the pipeline wait for its design ([Open questions](#open-questions)).

## Run and test

Run every command in `ai-service/`, after [Set up](#set-up).

```bash
uv run --env-file .env ai-service serve --host 127.0.0.1 --port 8001
```

```bash
uv run pytest
```

The tests need no network, no `.env`, and no model weights. Without torch, the tests that need it are skipped ([Tests](#tests)).

## Set up

These steps work from a fresh clone, on Linux, macOS, and Windows. Only Linux gets torch.

1. Install [uv](https://docs.astral.sh/uv/) 0.11.11 or later. It installs the Python version of [`../.python-version`](../.python-version).

2. Install the locked dependencies:

   ```bash
   uv sync --locked
   ```

   This installs everything except torch. The tests that need torch are skipped without it, and CI runs them on Linux ([ADR-0021, CI](../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#ci), statement 4).

3. On Linux only, add torch from the PyTorch CPU index, for the image and for the tests that use torch:

   ```bash
   uv sync --locked --group torch
   ```

   torch is locked for Linux only, so this group installs nothing on macOS or Windows ([ADR-0021, Python and dependencies](../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#python-and-dependencies), statement 2).

4. Create your settings. `.env` is ignored by git, and its values never leave your machine. Replace every placeholder; `SERVICE_TOKEN` is the same value as the `backend` setting `AI_SERVICE_TOKEN`, `RELEASE_MANIFEST_PATH` names the manifest of a release whose files are on your machine ([Release manifest](#release-manifest)), and the two `LLM_*_PRICE_MICRO_USD_PER_MILLION_TOKENS` settings take the prices of `GEMINI_MODEL` from the price list of the provider: they have no default, so `ai-service` does not start until they are filled in ([LLM call](#llm-call)).

   ```bash
   cp .env.example .env
   ```

`ai-service serve` validates the settings first. A missing or invalid setting stops it with exit status 2 and a `settings.invalid` line that names the setting, never its value ([ARCH-34](../docs/rules/architecture.md)). It then reads the egress allow-list, and a missing or invalid file stops it the same way, with an `egress_allow_list.invalid` line that names the file ([Egress and secrets](#egress-and-secrets)). It then checks the release, and a missing, incomplete, or changed release stops it the same way, with a `release.invalid` line that names the reason ([Release manifest](#release-manifest)). There is no fallback model, so without a release whose files are on the machine, `ai-service serve` does not start.

Docker is not part of local development. CI builds the [`Dockerfile`](Dockerfile), which installs the `torch` group.

## Commands

| Check | Command |
|---|---|
| Format | `uv run ruff format --check .` |
| Lint | `uv run ruff check .` |
| Types | `uv run pyright` |
| Layer and feature boundaries | `uv run lint-imports` |
| Unit tests only | `uv run pytest tests/unit` |
| Tests of the tiny models, on Linux with the `torch` group | `uv run --locked --group torch pytest -m torch` |
| Tests with the real weights, on Linux with the release assets | `uv run --group torch pytest -m real_model` |
| Coverage | `uv run pytest --cov --cov-report=`, then the two reports below |

```bash
uv run coverage report --fail-under=80
uv run coverage report --fail-under=90 --include="*/supportiq_ai_service/*/domain/*,*/supportiq_ai_service/*/application/*"
```

The models in `generated/` are written by one command, and CI fails when the committed file differs ([CON-26](../docs/rules/contracts.md)):

```bash
uv run datamodel-codegen
```

## Layout

```text
ai-service/
├── src/supportiq_ai_service/
│   ├── platform/           # Clock, errors, events, settings, logging, trace context, egress, the service token, web
│   ├── release/            # The release manifest: loading, checksums, the asset versions, readiness
│   ├── suggestions/        # For now createAnalysis and createDraft: use cases, results, the pipeline port
│   ├── intent/             # The 46 intent labels, the intent distribution and its port, and the DistilBERT model
│   ├── retrieval/          # getKbDocumentVersion, and the search of the KB: chunking, the index, and the BGE encoder
│   ├── drafting/           # One LLM call and its cost, the Gemini client, and the budget of the LLM step
│   ├── composition_root/   # The only place that wires everything: the app and its command
│   └── generated/          # Models generated from the contract; never edited by hand
├── tests/
│   ├── unit/               # Domain and application, with fakes; the network is blocked
│   ├── integration/        # The app over HTTP with fakes, and guardrails/
│   └── contract/           # Schemathesis and every documented outcome of contract 1.0.0
├── Dockerfile
└── pyproject.toml          # Dependencies and the configuration of every tool
```

`platform/`, `release/`, `composition_root/`, `generated/`, and the test folders are fixed. `suggestions/` is an interim feature named after the tag of its two operations in the contract: it holds their use cases, the types of their results in the shape of the contract, and the port of the pipeline, which computes nothing itself. `intent/`, `retrieval/`, and `drafting/` hold the adapters taken over from `main`. The pipeline design decides the features of the pipeline and replaces this split ([Open questions](#open-questions)).

Each feature has the layers of [ARCH-16](../docs/rules/architecture.md):

| Layer | Holds | May use |
|---|---|---|
| `domain/` | Types, rules, errors, and ports as `Protocol` classes | The standard library, the public API of `platform` for the root error of [PY-20](../docs/rules/python.md) and for shared errors, types, and pure functions, and the public API of a feature below it for its identifiers and errors ([ARCH-11](../docs/rules/architecture.md)). No third-party package is reachable from it |
| `application/` | Use cases | `domain/` and public APIs |
| `adapters/` | Implementations of the ports, such as the intent model, the encoder, the index, and the LLM client | `domain/` of the feature, and public APIs |
| `api/` | Routes and the mapping between contract models and domain types | `application/`, `domain/`, and `generated/` |

Features depend on each other in one direction and only through the `__init__.py` of the feature, its public API (ARCH-17, ARCH-18). `uv run lint-imports` enforces this with the contracts in [`pyproject.toml`](pyproject.toml). `platform` has a second public entry point, `platform.web`, for the interface layers and the composition root, and `release` has three: `release.api`, for the asset versions that every result embeds; `release.manifest`, the interim format of the release manifest and its checks, for the composition root and for `eval/`; and `release.assets`, the checked files of each asset and their strict reading, for the adapters that read an asset. `ml/` and `eval/` use only the HTTP contract of `ai-service`, the public interface of `supportiq_ai_service`, and the formats of the model artifact and the release manifest; they never import its internals ([ADR-0021, Where the code of `main` goes](../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#where-the-code-of-main-goes), statement 1).

## Egress and secrets

- `ai-service` calls outside the system only the hosts of the egress allow-list ([ADR-0010, Egress control](../docs/decisions/0010-pseudonymization-and-egress-control.md#egress-control)). The list is [`egress-allow-list.v1.json`](src/supportiq_ai_service/platform/adapters/egress-allow-list.v1.json), version `1`, and holds only `generativelanguage.googleapis.com`. It ships inside the package and is read with `importlib.resources`. It is not a setting, so no environment can change it: only a change in the repository with the approval of [SEC-35](../docs/rules/security-and-privacy.md#security-review) can. At startup it is read strictly: an unknown field, another version, an empty or repeated host, or a host that is not a lowercase DNS name stops the replica.
- Egress is enforced in code, because the hosting has no outbound filter ([ADR-0018, Egress](../docs/decisions/0018-hosting-of-ai-service-on-modal.md#egress)). [`platform/adapters/egress.py`](src/supportiq_ai_service/platform/adapters/egress.py) is the only module that creates an HTTP client or transport ([ARCH-19](../docs/rules/architecture.md)). Its `AllowListedTransport` refuses, before it connects, every request that is not HTTPS on the default port to an allow-listed host, and the LLM client handles a refusal like any failed call: `llm_unavailable` ([ADR-0010, Failure handling](../docs/decisions/0010-pseudonymization-and-egress-control.md#failure-handling)). The client reads no proxy setting from the environment (`trust_env=False`) and follows no redirect (`follow_redirects=False`). `ai-service serve` creates the one client in the composition root, right after it reads the allow-list and before the server starts, which does no I/O; the lifespan of the app closes it at shutdown ([ARCH-21](../docs/rules/architecture.md), [ARCH-24](../docs/rules/architecture.md)). No other place creates one.
- The guardrail [`tests/integration/guardrails/test_egress_allow_list.py`](tests/integration/guardrails/test_egress_allow_list.py) fails when the packaged list holds another host, when the client of a replica sends a request outside the list or stays open after shutdown, and when another module of `src/` does one of these, in any import form:
  - calls `httpx.Client`, `httpx.AsyncClient`, `httpx.HTTPTransport`, `httpx.AsyncHTTPTransport`, or one of the request functions of `httpx` (`get`, `post`, `put`, `patch`, `delete`, `head`, `options`, `request`, `stream`);
  - calls `socket.socket` or `socket.create_connection`;
  - imports `urllib.request`, `http.client`, `requests`, `urllib3`, `httpcore`, `aiohttp`, or `huggingface_hub`, which downloads models while `ai-service` downloads nothing when it runs.

  Type annotations do not count ([SEC-40](../docs/rules/security-and-privacy.md#transport-and-runtime)).
- The intent model and the BGE encoder ship with each release, and Hugging Face runs offline, so `ai-service` downloads nothing when it starts. Both load with `local_files_only=True` from their folder in the release only, so a missing file stops startup instead of starting a download ([ADR-0018, Egress](../docs/decisions/0018-hosting-of-ai-service-on-modal.md#egress)).
- Every operation except `/health/live` and `/health/ready` checks the service token ([ADR-0018, Access](../docs/decisions/0018-hosting-of-ai-service-on-modal.md#access)).
- Provider responses, prompts, and keys are never logged ([LOG-29](../docs/rules/logging-and-observability.md#privacy-in-telemetry)). The Gemini API key and the service token are Modal Secrets ([ADR-0018, Secrets](../docs/decisions/0018-hosting-of-ai-service-on-modal.md#secrets)).

## LLM call

Drafting calls Gemini once per draft step, with the one client of the egress allow-list ([Egress and secrets](#egress-and-secrets)). [`drafting/adapters/gemini.py`](src/supportiq_ai_service/drafting/adapters/gemini.py) makes one attempt, and [`drafting/adapters/budgeted_draft_client.py`](src/supportiq_ai_service/drafting/adapters/budgeted_draft_client.py) decides the retries.

- The instructions are the two prompt files of the release ([Asset formats](#asset-formats)). Their sources are [`prompts/grounded-v4/`](prompts/grounded-v4/), versioned and reviewed like code, and a change of a prompt needs the two approvals of [SEC-35](../docs/rules/security-and-privacy.md#security-review) ([DATA-38](../docs/rules/data-and-ml.md#prompts-and-llm-output)). They hold no policy and no company name: policy comes only from cited KB document versions. `grounded-v4` comes from `grounded-v3` of `main`, without its sentences about particular policies.
- When authority is required, the instructions of `drafting-requires-authority.txt` follow the system prompt: the draft holds supporting information only and decides, approves, or promises nothing ([ESC-03](../docs/product/requirements.md#41-escalation-and-fallback-rules)).
- The message, the passages of the KB, and the order facts go in one JSON document apart from the instructions, which state that it is data ([SEC-24](../docs/rules/security-and-privacy.md#prompt-injection)). Each order fact is a source of its own, so a draft cites the field of a fact ([ADR-0014](../docs/decisions/0014-citations-to-order-context.md)).
- The output follows a JSON schema that the request sends ([SEC-25](../docs/rules/security-and-privacy.md#prompt-injection)). An output that breaks it, or a blocked or unfinished answer, is `llm_invalid_output`, and its tokens still count.
- The budget of the step is `LLM_BUDGET_MS`, at most 10 seconds, retries and waits included, checked before each attempt and each wait ([Known limits](#known-limits)) (NFR-07, [ERR-10](../docs/rules/errors-and-reliability.md#timeouts-and-latency-budget)). Each attempt gets the smaller of `LLM_ATTEMPT_TIMEOUT_MS` and the rest of the budget. Only a timeout, a connection error, a `502`, `503`, or `504`, or a `429` with a delay to wait is retried ([ERR-12](../docs/rules/errors-and-reliability.md#retries)); unlike `main`, a `408` and a `500` are final. A retry waits the delay that Gemini asked for, or a random part of an exponential backoff (ERR-13). A refusal of the egress allow-list, a hard quota, or a delay that cannot be read is final.
- The tokens of every answered attempt are added, thinking tokens as output tokens, and their cost uses the two price settings, rounded up to a micro-dollar (contract `LlmUsage`).

## Release manifest

A replica serves exactly one release, which it checks at startup ([DATA-56](../docs/rules/data-and-ml.md#models-and-artifacts)). A release is one folder: the manifest file and every asset file that it names, by a path relative to that folder. `RELEASE_MANIFEST_PATH` names the manifest. On Modal, the folder is the one that `modal deploy` adds to the image ([ADR-0018, Deploy](../docs/decisions/0018-hosting-of-ai-service-on-modal.md#deploy)).

The format is interim. `ReleaseManifest` in [`release/adapters/manifest_file.py`](src/supportiq_ai_service/release/adapters/manifest_file.py) defines it, and `supportiq_ai_service.release.manifest` exports it with its checks. A data contract in `contracts/` replaces it ([Open questions](#open-questions)). The manifest is read strictly: a missing field, an unknown field, or a value of the wrong type refuses it.

| Field | Holds |
|---|---|
| `format` | Always `supportiq-release-manifest/interim-1` |
| `release_id` | The unique, immutable identifier of the release, with the pattern of `release_id` in the contract. It is never reused, not even after a candidate fails the gate ([ARCH-40](../docs/rules/architecture.md#versioned-assets)) |
| `assets` | Exactly six assets: `model`, `kb`, `mapping`, `prompts`, `routing`, and `index` |
| `assets.<asset>.version` | The version that results report, with the pattern of `AssetVersion` in the contract |
| `assets.<asset>.files` | At least one file, each with its `path`, its `sha256` in lowercase hexadecimal, and its `size_bytes`. A path is relative, uses `/`, has no `.` or `..` segment, and belongs to one asset only |
| `assets.routing.model_version` | The model version that the routing configuration was tuned for. It must be the version of `assets.model` ([DATA-58](../docs/rules/data-and-ml.md#models-and-artifacts)) |
| `gate_run` | The passing run of the offline evaluation gate: `run_id`, `outcome` (always `passed`), `record` (the path of its record in the repository), and `record_sha256`. It is `null` only in a candidate ([DATA-57](../docs/rules/data-and-ml.md#models-and-artifacts)) |

- `index` holds the files of the encoder too, because an index is valid only with the encoder that built it, and the encoder also embeds each query.
- The first release holds a `kb` without any document, and a `mapping` and an `index` built from it, because KB ingestion admits no document of KB v2 ([ADR-0021, KB ingestion](../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#kb-ingestion)). The format sets no minimum number of documents.
- Every result reports the versions of the manifest ([ARCH-39](../docs/rules/architecture.md#versioned-assets)). `prompt_version` is the version of `prompts`, because the contract has one version for the set of prompts.
- The release command of `eval/` writes the manifest. `ai-service serve`, the release command, the download script before `modal deploy`, and CI read it. Nobody edits a published manifest.
- A release folder holds only regular files and folders. The release command and the download script never write a symbolic link into it.

`ai-service serve` refuses a release, in this order, and stops with exit status 2 and a `release.invalid` line that names the reason, the asset, and the path, never the content of a file:

1. the manifest is unreadable, is not JSON in UTF-8, or breaks the format;
2. it links no passing gate run;
3. `assets.routing.model_version` is not the version of `assets.model`;
4. a file resolves outside the folder, through a symbolic link too, or is not a readable regular file;
5. the folder holds a symbolic link, even one that the manifest names, another entry that is not a folder and that the manifest does not name, or a folder that cannot be listed. A model library reads a whole folder, so a link or an extra file would change what is served without a checksum ([ADR-0018, Decision drivers](../docs/decisions/0018-hosting-of-ai-service-on-modal.md#decision-drivers));
6. a file has another size or another SHA-256 than the manifest states.

The release command checks a candidate with `verify_candidate`, which accepts `"gate_run": null`, and runs the gate in its own process on exactly that candidate ([ADR-0021, Release and the offline evaluation gate](../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#release-and-the-offline-evaluation-gate)). `ai-service serve` always calls `verify_release` and has no option to serve a candidate.

### Asset formats

After the checksums match, the adapter of each asset reads its files in an interim format, as strictly as the manifest. A file that breaks its format, or a version that differs from the manifest, is refused with the reason `asset_invalid`, the asset, and the path. The data contract replaces these formats too ([Open questions](#open-questions)).

| Asset | Files | Read by | Holds and checks |
|---|---|---|---|
| `model` | One folder: `artifact.json`, `config.json`, `model.safetensors`, `tokenizer.json`, `tokenizer_config.json`, and the other tokenizer files, and no file of another asset. `tokenizer_config.json` fixes the tokenizer class and its options, which the model library would otherwise guess | [`intent/adapters/model_artifact.py`](src/supportiq_ai_service/intent/adapters/model_artifact.py) | `artifact.json` (`supportiq-model-artifact/interim-1`) states what [DATA-35](../docs/rules/data-and-ml.md#models-and-artifacts) requires and the model library does not hold: `model_version`, equal to the version of the asset; `preprocessing` (`max_length` up to 512, `padding` `max_length`, `truncation` `true`); `training_data_manifest_sha256`; `metrics_summary`, the `run_id` of `ml/runs/` and at least one metric; and `calibration`, always `null` ([Known limits](#known-limits)). The `id2label` of `config.json` names each of the 46 intents of `IntentLabel` once, for the outputs 0 to 45 |
| `kb` | One file | [`retrieval/adapters/kb_file.py`](src/supportiq_ai_service/retrieval/adapters/kb_file.py) | `supportiq-kb/interim-1`: the `kb_version`, equal to the version of the asset, and the KB document versions with the fields, patterns, and lengths of `KbDocumentVersion` in the contract. Each version appears once and ends after it starts |
| `mapping` | One file | [`suggestions/adapters/mapping_file.py`](src/supportiq_ai_service/suggestions/adapters/mapping_file.py) | `supportiq-document-intents/interim-1`: its `version`, the `kb_version` it was built from, and the intents of each KB document version, each one of the 46 labels. It names only versions of the KB of the same release ([ADR-0005](../docs/decisions/0005-intent-independent-retrieval.md), statement 6) |
| `prompts` | `drafting-system.txt` and `drafting-requires-authority.txt`, nothing else | [`drafting/adapters/prompt_files.py`](src/supportiq_ai_service/drafting/adapters/prompt_files.py) | UTF-8 text with at least one character other than a space. Their sources are versioned files in `ai-service/prompts/<prompt_version>/`, reviewed like code ([DATA-38](../docs/rules/data-and-ml.md#prompts-and-llm-output)) |
| `routing` | One file | [`suggestions/adapters/routing_file.py`](src/supportiq_ai_service/suggestions/adapters/routing_file.py) | `supportiq-routing-configuration/interim-1` ([DATA-58](../docs/rules/data-and-ml.md#models-and-artifacts)): its `version`; the `model_version` it was tuned for, equal to the model of the release; τ as `min_top_probability` and δ as `min_top_two_gap`, from 0 to 1; λ as `rerank_weight`, from 0; `high_band_min_probability`, from τ to 1; `sensitive_intents`, which hold `request_refund` ([contracts v1 design, Authority rule](../docs/design/contracts-v1.md#authority-rule-fr-06)); `sensitive_intent_min_probability`; and `sensitive_terms`, each lowercase whole words with a category of FR-06, with at least one `legal_claim` term and one `suspected_fraud` term, because the list detects both ([contracts v1 design, Authority rule](../docs/design/contracts-v1.md#authority-rule-fr-06)) |
| `index` | `index.json` and one folder of the encoder with `config.json`, `model.safetensors`, `tokenizer.json`, `tokenizer_config.json`, and its other files, and no file of another asset | [`retrieval/adapters/index_file.py`](src/supportiq_ai_service/retrieval/adapters/index_file.py) | `supportiq-retrieval-index/interim-1`: its `version`; the `kb_version` it indexes; the encoder's name, folder, query prefix, and `max_length`; the chunking in tokens; and `relevance_min_score`, from 0 to 1. `ai-service` builds the index at startup from the KB of the release, as `main` did |

## Events

Every log line is one JSON object on standard output, with the attributes of an allow-list; every string in it is redacted for email addresses and long tokens. The catalog is [`platform/domain/events.py`](src/supportiq_ai_service/platform/domain/events.py) ([LOG-12](../docs/rules/logging-and-observability.md)).

| Event | When |
|---|---|
| `startup.completed`, `shutdown.started` | A replica starts or stops |
| `settings.loaded`, `settings.invalid` | The settings are read; `settings.invalid` names the settings, never a value |
| `egress_allow_list.invalid` | The egress allow-list is missing or invalid, so the replica stops; it names the file, never its content |
| `release.loaded` | The release manifest and every file it names pass the check, with the `release_id` |
| `release.invalid` | The release manifest or a file it names fails the check, so the replica stops; it names the reason, the asset, and the path of the file, never its content |
| `request.completed` | Every request ends, with the route template, the method, the status, and the duration |
| `request.failed` | A request fails unexpectedly, with the error type |
| `request.refused` | A request answers `503 not-ready`, because no verified release is loaded |
| `service_token.rejected` | A request has no valid service token and answers `401` |
| `log.forwarded` | A library logs at `warning` or above; the message is redacted |

Every request continues the trace of a valid `traceparent` or starts a new one, and its log lines and error bodies carry that trace ID ([LOG-04](../docs/rules/logging-and-observability.md), LOG-05). `ai-service` uses only the OpenTelemetry API: no span leaves the process, because a telemetry destination needs a change of ADR-0010 first ([ADR-0018, Follow-ups](../docs/decisions/0018-hosting-of-ai-service-on-modal.md#follow-ups)).

## Tests

| Layer | Folder | What it proves |
|---|---|---|
| Unit | `tests/unit/` | Domain and application logic with a fake for every port |
| Integration | `tests/integration/` | The app over HTTP with fakes: the service token, the error bodies, and readiness |
| Guardrails | `tests/integration/guardrails/` | The cases of [TEST-26](../docs/rules/testing.md#guardrail-tests) that apply here, such as egress only to the allow-listed host ([SEC-40](../docs/rules/security-and-privacy.md#transport-and-runtime)) |
| Contract | `tests/contract/` | Schemathesis over the six operations of contract 1.0.0, and one test for each documented status |

- Every test runs with `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`, and an empty `HF_HOME`, so no test downloads a model or reads a cached one.
- Unit tests have no network. Integration tests may open only loopback connections.
- No test reads `.env` or uses an API key from the environment, and no test calls an LLM: a fake LLM adapter replaces Gemini ([ADR-0021, CI](../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#ci), statement 2).
- Tests that load real model weights carry the marker `real_model`. An empty `HF_HOME` does not stop a test from loading weights from a local path, so every test that needs real weights carries the marker, without exception. They are skipped by default and in CI, and run only with `-m real_model` on a machine that holds the release assets. The real model is otherwise tested on the Modal deployment ([ADR-0021, Python and dependencies](../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#python-and-dependencies), statement 3).
- CI runs the tests on Linux twice: without torch, with fakes, and with torch from the CPU index (ADR-0021, CI, statement 4).
- Tests that build and run models carry the marker `torch` and skip, with their reason, where torch is not installed. They build tiny models with random weights from a vocabulary of a few words, so they download nothing and need no release assets. Only the two adapters that load a model need torch; the softmax, the chunking, the index, and the search are tested everywhere with fakes.

## Known limits

- The pipeline of `main` is not wired in yet. A replica checks the checksums of its release but does not read its assets yet. With a verified release it answers ready, but `createAnalysis` and `createDraft` answer `503 not-ready`, and `getKbDocumentVersion` finds no document.
- The model weights and the encoder are not in git. They are assets of GitHub Releases, named with their checksums in the release manifest ([ADR-0018, Artifact store](../docs/decisions/0018-hosting-of-ai-service-on-modal.md#artifact-store)). `ai-service` has no fallback model: without a verified release it does not start, and `backend` falls back to manual handling.
- The model artifact holds every part that [DATA-35](../docs/rules/data-and-ml.md#models-and-artifacts) requires except calibration: its interim format requires `"calibration": null`, so the intent model of `main` reports uncalibrated softmax scores. Calibrated probabilities (FR-01, DATA-34) wait for a calibration fitted on validation data and a new format of the artifact ([contracts v1 design, Work for the join](../docs/design/contracts-v1.md#work-for-the-join-with-the-ai-and-ml-code)).
- The first release serves no KB document, so every policy question leads to abstention (ESC-04) until a new KB version arrives ([ADR-0021, KB ingestion](../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#kb-ingestion)).
- The masks that `ai-service` writes before an LLM call come from patterns. A personal value that no pattern matches, such as an address written in slang, can remain ([ADR-0010, Detection](../docs/decisions/0010-pseudonymization-and-egress-control.md#detection)).
- No adapter sends a request with the client of the egress allow-list yet: the pipeline of `main` is not wired into the app.
- The static scan of the egress guardrail covers only the code of `ai-service`. A dependency that opens its own connection is caught only when a test runs it under the network block of pytest-socket ([ADR-0018, Consequences](../docs/decisions/0018-hosting-of-ai-service-on-modal.md#consequences)).
- The Gemini API has rate limits. When a call fails or the budget runs out, a draft returns `llm_unavailable` with a reason code, and staff handle the ticket manually (ESC-05).
- httpx applies the timeout of an LLM attempt to each phase of the request (connect, write, read, and pool), not to the whole request. The budget is checked only before each attempt and before each wait, so in the worst case one attempt, and so the whole LLM step, runs past `LLM_BUDGET_MS`; `main` stated the same limit ([ERR-10, ERR-11](../docs/rules/errors-and-reliability.md#timeouts-and-latency-budget)).
- No circuit breaker stops the calls of a failing provider yet ([ERR-14](../docs/rules/errors-and-reliability.md#retries), a SHOULD): each draft step tries again within its own budget.
- The latency budget of the whole suggestion, and with it the reason code `budget_exceeded`, waits for the `ai-service` design that ERR-10 asks for; the project lead deferred it on 2026-11-15 ([ERR-11](../docs/rules/errors-and-reliability.md#timeouts-and-latency-budget)). Until then, the LLM step keeps its own budget.
- Placeholders are not mapped to their type before the classifier and the encoder, because the model of `main` was trained without that step; the project lead deferred [DATA-59](../docs/rules/data-and-ml.md#models-and-artifacts) to the next training on 2026-11-15.
- `ai-service` never returns `source_review_overdue`, because the KB has no freshness rules yet.
- Each paragraph of a draft is one segment, and the grounding check reads a segment as a whole, as `main` did. A sentence without a citation passes when its paragraph cites a source, such as "Your order is in transit [S1]. You will get a refund in 5 days." A check sentence by sentence follows the merge, with its own issue, because the limit of 40 characters applies to a whole paragraph.
- The grounding check refuses a segment that cites only order fields and words a policy, such as `eligible`, `policy`, `fee`, or `within 5 days`, because an order field never supports a policy ([ADR-0014](../docs/decisions/0014-citations-to-order-context.md), statement 2). The word list is a heuristic: a policy in other words can pass, and staff check every claim (FR-04).
- `signal_disagreement` is a warning and lowers the band to `medium` at most; it never lowers the probability below τ, because no factor for that is tuned yet ([contracts v1 design, Reason codes](../docs/design/contracts-v1.md#reason-codes)). The `ai-service` pipeline design decides it.
- A token count above the cap of the contract (1 000 000) refuses the output as `llm_invalid_output`, and the outcome carries no `llm_usage`, so no number outside the contract is sent.
- Structural checks on a draft, such as citation identity and placeholder provenance, do not prove that a cited source supports a claim. Staff verify every claim before they send a reply (FR-04).
- The cold start, the latency from `backend`, and the memory in use are not measured yet ([ADR-0018, Validation](../docs/decisions/0018-hosting-of-ai-service-on-modal.md#validation)).

## Dependencies

Each direct dependency, with why it is here ([WF-27](../docs/rules/workflow.md#dependencies)). `uv.lock` pins every transitive dependency. numpy, torch, and transformers keep the versions that the real model of `main` was evaluated with on 2026-11-04.

### Runtime

| Name | Version | License | Why |
|---|---|---|---|
| fastapi | 0.162.0 | MIT | The web framework ([ADR-0003](../docs/decisions/0003-tech-stack.md)) |
| pydantic | 2.14.3 | MIT | Contract models and validation (ADR-0003) |
| pydantic-core | 2.50.4 | MIT | `from_json` and `to_json`, which read a request body strictly while integral numbers stay integers, imported directly, as in `backend` |
| pydantic-settings | 2.16.2 | MIT | Typed settings, validated at startup (ADR-0003, ARCH-34) |
| starlette | 1.10.0 | BSD-3-Clause | The ASGI types and routing classes under FastAPI, imported directly by the middleware and the exception handler, as in `backend` |
| uvicorn | 0.54.0 | BSD-3-Clause | The ASGI server that runs a replica, as in `backend`. The standard library has none |
| httpx | 0.28.1 | BSD-3-Clause | The HTTP client of the LLM call, whose transport enforces the egress allow-list (ADR-0003, [ADR-0018, Egress](../docs/decisions/0018-hosting-of-ai-service-on-modal.md#egress)) |
| opentelemetry-api | 1.45.2 | Apache-2.0 | Reads and propagates `traceparent` ([ADR-0007](../docs/decisions/0007-observability-stack.md), LOG-05). No SDK and no exporter: a telemetry destination needs a change of ADR-0010 first ([ADR-0018, Follow-ups](../docs/decisions/0018-hosting-of-ai-service-on-modal.md#follow-ups)) |
| transformers | 5.22.1 | Apache-2.0 | Loads and runs the DistilBERT intent model and the BGE encoder that `ai-service` takes over from `main` ([ADR-0021, Where the code of `main` goes](../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#where-the-code-of-main-goes)). The choice of both models waits for its own ADR (ADR-0021, Python and dependencies, statement 4) |
| numpy | 2.5.4 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | The vectors of the encoder and the in-memory index taken over from `main` (ADR-0021, Where the code of `main` goes) |

### The `torch` group

| Name | Version | License | Why |
|---|---|---|---|
| torch | 2.15.0+cpu | Apache-2.0 AND Apache-2.0 WITH LLVM-exception AND BSD-2-Clause AND BSD-3-Clause AND BSL-1.0 AND ISC AND MIT AND Zlib | Runs the intent model and the encoder. From the PyTorch CPU index, on Linux only (ADR-0021, Python and dependencies, statement 2) |

### Development

| Name | Version | License | Why |
|---|---|---|---|
| pytest | 9.2.0 | MIT | The test runner (ADR-0003) |
| pytest-xdist | 3.8.0 | MIT | Parallel runs (TEST-15) |
| pytest-randomly | 5.0.0 | MIT | Random order (TEST-15) |
| pytest-socket | 0.8.1 | MIT | Blocks the network in unit tests (TEST-16) |
| pytest-cov | 7.1.0 | MIT | Coverage from pytest (TEST-21) |
| coverage | 7.17.2 | Apache-2.0 | Branch coverage and its floors (TEST-21) |
| anyio | 4.16.0 | MIT | The pytest plugin of async tests |
| hypothesis | 6.170.15 | MPL-2.0 | Property-based tests (ADR-0003, TEST-13) |
| schemathesis | 4.33.1 | MIT | Contract tests (ADR-0003, CON-27) |
| datamodel-code-generator | 0.90.0 | MIT | Generates the models from the contract (ADR-0003, CON-25) |
| ruff | 0.17.4 | MIT | Format and lint (ADR-0003) |
| pyright (with the `nodejs` extra) | 1.1.414 | MIT | Strict types (ADR-0003) |
| import-linter | 2.16 | BSD-2-Clause | Layer and feature boundaries (ADR-0003, ARCH-11) |
| pip-audit | 2.10.1 | Apache-2.0 | Dependency vulnerabilities ([rules](../docs/rules/README.md#enforcement)) |

These dependencies have a license outside the list of [WF-30](../docs/rules/workflow.md#dependencies) and wait for the approval of the project lead in the join PR. The project lead already accepted `certifi`, `typing-extensions`, `defusedxml`, `hypothesis`, and `pathspec` for `backend`.

- Runtime: `certifi` (MPL-2.0), through `httpx`; `numpy` (0BSD, Zlib, and CC0-1.0 for bundled parts), a direct dependency; `regex` (Apache-2.0 AND CNRI-Python), through `transformers`; `tqdm` (MPL-2.0 AND MIT), through `transformers` and `huggingface-hub`; `typing-extensions` (PSF-2.0), through `pydantic` and other packages; `torch` (BSL-1.0, Zlib, and Apache-2.0 WITH LLVM-exception for bundled parts), a direct dependency of the `torch` group.
- Development: `defusedxml` (PSF-2.0), through `py-serializable`, which `pip-audit` needs; `hypothesis` (MPL-2.0), a direct dependency; `pathspec` (MPL-2.0), through `black`, which `datamodel-code-generator` needs.

The build backend is `uv_build`, from the same release as uv (MIT or Apache-2.0).

## Open questions

- **Pipeline design.** The [contracts v1 design](../docs/design/contracts-v1.md#work-for-the-join-with-the-ai-and-ml-code) refers to an `ai-service` pipeline design, which does not exist yet. It decides the features of the pipeline and where the interim use cases of `suggestions/` go, the domain of routing, the calibration of the intent probabilities, and the high-band threshold of `ConfidenceBand`.
- **Release manifest format.** The format of [Release manifest](#release-manifest) and the formats of its assets are interim. A data contract in `contracts/` for the release manifest and the model artifact format, written by the contract owners, replaces them ([ADR-0021, Follow-ups](../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#follow-ups)). Until then, `eval/` writes and checks manifests only through `supportiq_ai_service.release.manifest`.
