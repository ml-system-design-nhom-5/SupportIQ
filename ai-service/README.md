# ai-service

`ai-service` is the SupportIQ component that runs the AI pipeline for `backend`: intent classification, retrieval of KB document versions, the routing recommendation, and LLM drafting with citations ([ADR-0001](../docs/decisions/0001-system-architecture.md), [ADR-0005](../docs/decisions/0005-intent-independent-retrieval.md)). It serves [`contracts/ai-service.openapi.yaml`](../contracts/ai-service.openapi.yaml) 1.0.0. It is stateless: it has no database and owns no tickets, sessions, accounts, orders, or per-ticket state. `backend` is its only caller and sends it pseudonymized text and order context without identifiers ([ADR-0010](../docs/decisions/0010-pseudonymization-and-egress-control.md)). The AI only suggests: `ai-service` never sends a reply and never performs a transaction (FR-04, FR-06). It runs on Modal ([ADR-0018](../docs/decisions/0018-hosting-of-ai-service-on-modal.md)). The join with the AI and ML code of `main` builds it from that code ([ADR-0021, Where the code of `main` goes](../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#where-the-code-of-main-goes)). This README fixes its layout ([ARCH-16](../docs/rules/architecture.md)); the features of the pipeline wait for its design ([Open questions](#open-questions)).

## Run and test

Run every command in `ai-service/`, after [Set up](#set-up).

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

Docker is not part of local development. CI builds the [`Dockerfile`](Dockerfile), which installs the `torch` group.

## Commands

| Check | Command |
|---|---|
| Format | `uv run ruff format --check .` |
| Lint | `uv run ruff check .` |
| Types | `uv run pyright` |
| Layer and feature boundaries | `uv run lint-imports` |
| Unit tests only | `uv run pytest tests/unit` |
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
│   ├── platform/           # Settings, errors as Problem Details, the service token, trace context, logging, web
│   ├── release/            # The release manifest: loading, checksums, the asset versions, readiness
│   ├── intent/             # For now only the adapters of the intent model
│   ├── retrieval/          # For now only the adapters of the encoder, the index, and the KB
│   ├── drafting/           # For now only the adapters of the LLM client and its budget
│   ├── composition_root/   # The only place that wires everything: the app and its command
│   └── generated/          # Models generated from the contract; never edited by hand
├── config/                 # Versioned configuration files, such as the egress allow-list
├── tests/
│   ├── unit/               # Domain and application, with fakes; the network is blocked
│   ├── integration/        # The app over HTTP with fakes, and guardrails/
│   └── contract/           # Schemathesis and every documented outcome of contract 1.0.0
├── Dockerfile
└── pyproject.toml          # Dependencies and the configuration of every tool
```

`platform/`, `release/`, `composition_root/`, `generated/`, `config/`, and the test folders are fixed. `intent/`, `retrieval/`, and `drafting/` hold the adapters taken over from `main` until the pipeline design decides the features of the pipeline.

Each feature has the layers of [ARCH-16](../docs/rules/architecture.md):

| Layer | Holds | May use |
|---|---|---|
| `domain/` | Types, rules, errors, and ports as `Protocol` classes | The standard library, the public API of `platform` for the root error of [PY-20](../docs/rules/python.md) and for shared errors, types, and pure functions, and the public API of a feature below it for its identifiers and errors ([ARCH-11](../docs/rules/architecture.md)). No third-party package is reachable from it |
| `application/` | Use cases | `domain/` and public APIs |
| `adapters/` | Implementations of the ports, such as the intent model, the encoder, the index, and the LLM client | `domain/` of the feature, and public APIs |
| `api/` | Routes and the mapping between contract models and domain types | `application/`, `domain/`, and `generated/` |

Features depend on each other in one direction and only through the `__init__.py` of the feature, its public API (ARCH-17, ARCH-18). `ml/` and `eval/` use only the HTTP contract of `ai-service`, the public interface of `supportiq_ai_service`, and the formats of the model artifact and the release manifest; they never import its internals ([ADR-0021, Where the code of `main` goes](../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#where-the-code-of-main-goes), statement 1).

## Egress and secrets

- `ai-service` calls outside the system only the hosts of the egress allow-list, a versioned file in `config/` that holds only the Gemini host ([ADR-0010, Egress control](../docs/decisions/0010-pseudonymization-and-egress-control.md#egress-control)). The LLM client enforces it with `AllowListedTransport`, which allows only HTTPS to an allow-listed host and refuses every other host before it connects ([ADR-0018, Egress](../docs/decisions/0018-hosting-of-ai-service-on-modal.md#egress)).
- The intent model and the BGE encoder ship with each release, and Hugging Face runs offline, so `ai-service` downloads nothing when it starts.
- Every operation except `/health/live` and `/health/ready` checks the service token ([ADR-0018, Access](../docs/decisions/0018-hosting-of-ai-service-on-modal.md#access)).
- Provider responses, prompts, and keys are never logged ([LOG-29](../docs/rules/logging-and-observability.md#privacy-in-telemetry)). The Gemini API key and the service token are Modal Secrets ([ADR-0018, Secrets](../docs/decisions/0018-hosting-of-ai-service-on-modal.md#secrets)).

## Tests

| Layer | Folder | What it proves |
|---|---|---|
| Unit | `tests/unit/` | Domain and application logic with a fake for every port |
| Integration | `tests/integration/` | The app over HTTP with fakes: the service token, the error bodies, and readiness |
| Guardrails | `tests/integration/guardrails/` | The cases of [TEST-26](../docs/rules/testing.md#guardrail-tests) that apply here, such as egress only to the allow-listed host ([SEC-40](../docs/rules/security-and-privacy.md#transport-and-runtime)) |
| Contract | `tests/contract/` | Schemathesis over the six operations of contract 1.0.0, and one test for each documented status |

- Every test runs with `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1`, so no test downloads from Hugging Face.
- Unit tests have no network. Integration tests may open only loopback connections.
- No test reads `.env` or uses an API key from the environment, and no test calls an LLM: a fake LLM adapter replaces Gemini ([ADR-0021, CI](../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#ci), statement 2).
- Tests that load real model weights carry the marker `real_model`. They are skipped by default and in CI, and run only with `-m real_model` on a machine that holds the release assets. The real model is otherwise tested on the Modal deployment ([ADR-0021, Python and dependencies](../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#python-and-dependencies), statement 3).
- CI runs the tests on Linux twice: without torch, with fakes, and with torch from the CPU index (ADR-0021, CI, statement 4).

## Known limits

- The model weights and the encoder are not in git. They are assets of GitHub Releases, named with their checksums in the release manifest ([ADR-0018, Artifact store](../docs/decisions/0018-hosting-of-ai-service-on-modal.md#artifact-store)). `ai-service` has no fallback model: without a valid release it is not ready and answers `503`, and `backend` falls back to manual handling.
- The intent model of `main` reports uncalibrated softmax scores. Calibrated probabilities (FR-01) wait for the pipeline design and a calibration on validation data ([contracts v1 design, Work for the join](../docs/design/contracts-v1.md#work-for-the-join-with-the-ai-and-ml-code)).
- The first release serves no KB document, so every policy question leads to abstention (ESC-04) until a new KB version arrives ([ADR-0021, KB ingestion](../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#kb-ingestion)).
- The masks that `ai-service` writes before an LLM call come from patterns. A personal value that no pattern matches, such as an address written in slang, can remain ([ADR-0010, Detection](../docs/decisions/0010-pseudonymization-and-egress-control.md#detection)).
- The Gemini API has rate limits. When a call fails or the budget runs out, a draft returns `llm_unavailable` with a reason code, and staff handle the ticket manually (ESC-05).
- Structural checks on a draft, such as citation identity and placeholder provenance, do not prove that a cited source supports a claim. Staff verify every claim before they send a reply (FR-04).
- The cold start, the latency from `backend`, and the memory in use are not measured yet ([ADR-0018, Validation](../docs/decisions/0018-hosting-of-ai-service-on-modal.md#validation)).

## Dependencies

Each direct dependency, with why it is here ([WF-27](../docs/rules/workflow.md#dependencies)). `uv.lock` pins every transitive dependency. numpy, torch, and transformers keep the versions that the real model of `main` was evaluated with on 2026-11-04.

### Runtime

| Name | Version | License | Why |
|---|---|---|---|
| fastapi | 0.162.0 | MIT | The web framework ([ADR-0003](../docs/decisions/0003-tech-stack.md)) |
| pydantic | 2.14.3 | MIT | Contract models and validation (ADR-0003) |
| pydantic-settings | 2.16.2 | MIT | Typed settings, validated at startup (ADR-0003, ARCH-34) |
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

- **Pipeline design.** The [contracts v1 design](../docs/design/contracts-v1.md#work-for-the-join-with-the-ai-and-ml-code) refers to an `ai-service` pipeline design, which does not exist yet. It decides the features of the pipeline, the use cases of `createAnalysis` and `createDraft` and their handlers, the domain of routing, the calibration of the intent probabilities, and the high-band threshold of `ConfidenceBand`.
- **Release manifest format.** The data contract for the release manifest and the model artifact format is not written yet ([ADR-0021, Follow-ups](../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#follow-ups)). `release/` loads the manifest in that format once it exists ([DATA-56](../docs/rules/data-and-ml.md#models-and-artifacts)).
