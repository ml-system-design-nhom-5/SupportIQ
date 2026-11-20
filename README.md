# SupportIQ

SupportIQ is an AI copilot that helps e-commerce customer support staff handle tickets faster and more consistently. The AI only suggests. Staff review every draft and decide what is sent.

> Course project for *Machine Learning in Production* (VNU-UET). Prototype with simulated data only.

## What it does

- Classifies each customer message into one of 46 intents with a self-trained ML model and shows a calibrated confidence.
- Retrieves versioned policy documents from a knowledge base (KB) and drafts a reply with citations.
- Lets staff edit, approve, reject, or escalate. Managers decide refunds, disputes, and policy exceptions. Nothing reaches a customer without a staff action.
- Replaces personal data with pseudonyms before any text leaves `backend`.
- Records staff decisions, source versions, and an insert-only audit log for evaluation, reports, and monitoring.

Full scope and requirements: [docs/product/requirements.md](docs/product/requirements.md).

## Architecture

Three components talk only through versioned contracts ([ADR-0001](docs/decisions/0001-system-architecture.md)). `backend` replicas keep no state between requests, and all shared state lives in PostgreSQL, on any hosting platform ([ADR-0011](docs/decisions/0011-deployment-and-runtime-topology.md)). The demo runs on free plans: `frontend` on Cloudflare Pages behind a same-origin proxy, `backend` on Render, and PostgreSQL on Supabase ([ADR-0016](docs/decisions/0016-hosting-on-free-tiers.md)).

```mermaid
flowchart LR
    Customer(["Customer"]) -->|"/shop"| FE["frontend"]
    Staff(["Staff and managers"]) -->|"/console"| FE
    Admin(["Admin"]) -->|"/admin"| FE
    FE -->|"backend contract"| BE["backend"]
    BE -->|"ai-service contract:<br/>pseudonymized text only"| AI["ai-service"]
    BE -->|"SQL"| DB[("PostgreSQL")]
    AI -->|"loads at startup"| ART[("Release manifest:<br/>model, KB, prompts, routing")]
    AI -->|"allow-listed host only"| LLM["LLM provider"]
    ML["pipeline/ training"] -.->|"versioned artifact"| ART
```

| Component | Responsibility |
|---|---|
| `frontend` | Shop demo with a read-only catalog for simulated customers; review console for staff and managers; admin area for accounts and versions |
| `backend` | Ticket lifecycle, AI orchestration through a job queue, pseudonymization of personal data, permissions, the only path that sends replies, decision records and the audit log, reports, simulated commerce data |
| `ai-service` | Intent classification, retrieval, routing recommendation, drafts with citations, on pseudonymized text. Suggests only |

## Main flow

```mermaid
sequenceDiagram
    actor Customer
    actor Staff
    participant FE as frontend
    participant BE as backend
    participant AI as ai-service

    Customer->>FE: Submit a support request in /shop
    FE->>BE: Create ticket
    BE->>BE: Queue a suggestion job and pseudonymize the message
    par Analysis
        BE->>AI: Request analysis
        AI-->>BE: Intent distribution, documents, routing recommendation
    and Draft
        BE->>AI: Request draft
        AI-->>BE: Draft with citations, or abstain/escalate with reason codes
    end
    Staff->>FE: Review the ticket in /console
    Staff->>FE: Edit, approve, reject, or escalate
    FE->>BE: Record staff decision
    BE-->>Customer: Reply visible in /shop only after staff send it
    Note over BE,AI: If pseudonymization fails, or ai-service fails or times out, backend switches the ticket to manual handling and records the reason.
```

`backend` requests the analysis and the draft when a ticket is created ([contracts v1 design](docs/design/contracts-v1.md#suggestion-lifecycle)). Pipeline details: [ADR-0005](docs/decisions/0005-intent-independent-retrieval.md).

## Project status

The parts of `main` are kept at their paths, byte for byte, next to the components ([ADR-0028](docs/decisions/0028-repository-layout-for-the-pull-request-into-main.md)). Decisions are recorded in [docs/decisions/](docs/decisions/README.md), and contract changes in the [contracts changelog](contracts/CHANGELOG.md).

- `frontend`, `backend`, `ai-service`, `ml/`, `eval/`, `contracts/`, and `deploy/` exist, each with its README ([Repository layout](#repository-layout)).
- The first release of `ai-service`, `release-2026-11-18-02`, passed the offline evaluation gate. Its gate run record and its manifest are in [eval/releases/release-2026-11-18-02/](eval/releases/release-2026-11-18-02/). It serves no KB document, so no request gets a draft yet ([ai-service README, Known limits](ai-service/README.md#known-limits)).
- No release of `ai-service` is deployed: its Modal app and the download script of a release wait for [#41](https://github.com/ml-system-design-nhom-5/SupportIQ/issues/41) ([ADR-0018, Deploy](docs/decisions/0018-hosting-of-ai-service-on-modal.md#deploy)).
- Follow-ups are the [open issues labeled `tech-debt`](https://github.com/ml-system-design-nhom-5/SupportIQ/issues?q=is%3Aissue%20is%3Aopen%20label%3Atech-debt).

## Repository layout

| Path | Holds |
|---|---|
| `README.md` | This file |
| [`AGENTS.md`](AGENTS.md) | Instructions for AI coding agents |
| [`docs/`](docs/README.md) | Requirements, decisions, designs, rules, guides, templates, and the glossary |
| `.github/` | The CI workflows ([repository checks](docs/guides/repository-checks.md)) |
| [`contracts/`](contracts/README.md) | The API and data contracts between `frontend`, `backend`, and `ai-service`, with their examples, their changelog, and the tooling that checks them and serves them as mocks |
| [`frontend/`](frontend/README.md) | The web app: sign-in, the demo shop at `/shop`, the console at `/console`, and the admin area at `/admin`, with the Pages Function that is the ingress of the demo deployment |
| [`backend/`](backend/README.md) | Sign-in, the read-only shop, the ticket workflow behind `/console`, internal accounts, the simulated commerce data, the pseudonym maps, and the audit log |
| [`ai-service/`](ai-service/README.md) | The AI pipeline for `backend`: intent classification, retrieval of KB document versions, the routing recommendation, and LLM drafting with citations |
| [`ml/`](ml/README.md) | The run records of the intent model that `ai-service` serves, in `ml/runs/` |
| [`eval/`](eval/README.md) | The release command, the gate run records and published manifests of the releases in `eval/releases/`, and the output of KB ingestion |
| [`deploy/`](deploy/README.md) | The setup of the demo on free plans: the setup order, the settings of each platform, and the checks before and after the first deploy; and, in `deploy/local/`, the local run of the whole system ([local run guide](docs/guides/local-run.md)) |
| `data/` | Data committed unchanged: the KB versions in `data/raw/kb/<kb_version>/`, the interim escalation cases in `data/benchmarks/escalation/`, and the data of `main`: its other test and scenario sets in `data/benchmarks/`, and `data/business/`, `data/datasets/`, `data/intent/`, and `data/knowledge/`. Downloaded datasets, such as Bitext, are not committed ([DATA-06 to DATA-08](docs/rules/data-and-ml.md#data-layout)) |
| [`pipeline/`](pipeline/README.md) | The offline tools of `main`: the data preparation, the training, and the evaluation of the intent model and of the whole system, with the autoeval. Not on the serving path |
| `artifacts/` | The outputs of the runs of `main`: data preparation, training, evaluation, audits, browser tests, and the search index |
| [`tests/`](tests/README.md), `pytest.ini` | The tests of `pipeline/`, `scripts/`, and `apps/`, with their pytest configuration. Each component keeps its own tests |
| `scripts/` | 20 scripts of `main` for training, evaluation, and acceptance runs |
| `apps/` | The code of `main` that `pipeline/`, `tests/`, and `scripts/` import. Nothing deploys it, and `apps/backend/` and `apps/demo/` are frozen |

The rows from `pipeline/` to `apps/` are parts of `main`, kept at their paths byte for byte. They follow no engineering rule yet ([ADR-0028, Technical debt](docs/decisions/0028-repository-layout-for-the-pull-request-into-main.md#technical-debt)).

## Run and test on your machine

One command starts the whole system with Docker, on Linux, macOS, and WSL2 on Windows: PostgreSQL 17, `backend` with the simulated demo data, and `frontend` at <http://localhost:5173>. The [local run guide](docs/guides/local-run.md) gives the requirements, the demo accounts, the mode with AI, and how to stop it.

```bash
deploy/local/local-run.sh start
```

Each part also runs on its own. Set it up and run it as its README states; the commands below come from those READMEs.

- **`frontend`** ([Set up](frontend/README.md#set-up), [Run](frontend/README.md#run), [Test](frontend/README.md#test)): `pnpm run dev:mock` serves the app at <http://localhost:5173> against the Prism mock of the `backend` contract, on Linux, macOS, and WSL2 on Windows. The mock answers every sign-in with the customer of the examples, so a browser reaches the shop but not the console or the admin area. `pnpm run dev` proxies to the `backend` that `SUPPORTIQ_BACKEND_URL` names instead ([Settings](frontend/README.md#settings)). `pnpm test` runs every test.
- **`contracts/`** ([Set up](contracts/README.md#set-up), [Commands](contracts/README.md#commands)): `pnpm run check` checks both contracts. `pnpm run mock` serves the `backend` contract as a mock at `http://127.0.0.1:4010`, and `pnpm run mock:ai-service` serves the `ai-service` contract at `http://127.0.0.1:4012`, which `backend` can call during development ([The `ai-service` mock](contracts/README.md#the-ai-service-mock)).
- **`backend`** ([Set up](backend/README.md#set-up), [Run and test](backend/README.md#run-and-test)): one replica and every test run against PostgreSQL 17, with the settings of `backend/.env`, made from `.env.example`. The README sets up PostgreSQL 17 with Homebrew. The unit tests need no database: `uv run pytest tests/unit`.
- **`ai-service`** ([Set up](ai-service/README.md#set-up), [Run and test](ai-service/README.md#run-and-test)): `uv run pytest` runs the tests on Linux, macOS, and Windows; without torch, the tests that need it are skipped. `ai-service serve` loads the real model, so it runs only on Linux, because torch is locked for Linux only ([ADR-0021, Python and dependencies](docs/decisions/0021-repository-layout-and-ai-ml-migration.md#python-and-dependencies)). It also needs the files of a published release on the machine; without them it does not start.
- **The release command in `eval/release/`** ([Set up](eval/release/README.md#set-up), [Run and test](eval/release/README.md#run-and-test)): `uv run --project eval/release pytest eval/release` runs its tests from the repository root. The offline evaluation gate runs in Docker.
- **`pipeline/`, `tests/`, and `scripts/` of `main`** ([ADR-0028, Technical debt](docs/decisions/0028-repository-layout-for-the-pull-request-into-main.md#technical-debt)): they keep the requirements files of `main`, without a lockfile, and no workflow runs them except `.github/workflows/autoeval.yml`. Their live modes are not used, because they send messages to Gemini without `backend` and `ai-service` ([ADR-0028, Temporary rules](docs/decisions/0028-repository-layout-for-the-pull-request-into-main.md#temporary-rules), statement 3).

## Documentation

Start with [docs/README.md](docs/README.md): where every document lives and how to write one.

| Need | Go to |
|---|---|
| What we build and why | [Requirements](docs/product/requirements.md) |
| Why we chose what we chose | [Architecture decisions](docs/decisions/README.md) |
| How we write code | [Engineering rules](docs/rules/README.md) |
| What a term means | [Glossary](docs/glossary.md) |
| API contracts and the mock | [contracts/README.md](contracts/README.md) |
| How to run the whole system on your machine | [Local run](docs/guides/local-run.md) |
| How to run the repository checks | [Repository checks and CI](docs/guides/repository-checks.md) |
| Instructions for AI coding agents | [AGENTS.md](AGENTS.md) |

## Non-negotiable rules

1. Staff approve every reply. The system never sends replies or performs transactions on its own.
2. Every draft cites verifiable sources: a document ID and version for policy, and an order field for facts about the order. Without enough evidence, the AI abstains.
3. Simulated data only. Personal data is pseudonymized before it leaves `backend`. No secrets in the repository.
4. Design before code. Contracts before implementation.

Details: [docs/rules/](docs/rules/README.md). Team roles and ownership: [ADR-0001](docs/decisions/0001-system-architecture.md#team-allocation).
