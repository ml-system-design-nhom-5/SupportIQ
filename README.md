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

Three components talk only through versioned contracts ([ADR-0001](docs/decisions/0001-system-architecture.md)). They run as one Docker Compose project behind an Nginx ingress, with two replicas of `backend` and of `ai-service` ([ADR-0011](docs/decisions/0011-deployment-and-runtime-topology.md)).

```mermaid
flowchart LR
    Customer(["Customer"]) -->|"/shop"| FE["frontend"]
    Staff(["Staff and managers"]) -->|"/console"| FE
    Admin(["Admin"]) -->|"/admin"| FE
    FE -->|"backend contract"| BE["backend"]
    BE -->|"ai-service contract:<br/>pseudonymized text only"| AI["ai-service"]
    BE -->|"SQL"| DB[("PostgreSQL")]
    AI -->|"loads at startup"| ART[("Release manifest:<br/>model, KB, prompts, routing")]
    AI -->|"egress proxy,<br/>allow-listed host only"| LLM["LLM provider"]
    ML["ml/ training"] -.->|"versioned artifact"| ART
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

Design phase. Decisions are recorded in [docs/decisions/](docs/decisions/README.md). Revision 2 of the contracts v1 design ([docs/design/contracts-v1.md](docs/design/contracts-v1.md)) aligns the design with the team's specification and is in review, together with ADR-0010 to ADR-0013. Writing the contracts follows their approval. There is no runnable code yet; setup instructions are added here when the first component is scaffolded.

## Target repository layout

```text
supportiq-ecom/
├── README.md        # This file
├── AGENTS.md        # Instructions for AI coding agents
├── docs/            # Requirements, decisions, rules, glossary
├── contracts/       # API and data contracts (created during contract design)
├── frontend/        # /shop and /console (created at scaffold)
├── backend/         # Created at scaffold
├── ai-service/      # Created at scaffold
├── ml/              # Training and offline evaluation (created at scaffold)
├── eval/            # Shared test sets and evaluation runs (created at scaffold)
├── deploy/          # Docker Compose, Nginx, egress proxy, observability (created at scaffold)
└── data/            # Local datasets; large files are not committed
```

## Documentation

Start with [docs/README.md](docs/README.md): where every document lives and how to write one.

| Need | Go to |
|---|---|
| What we build and why | [Requirements](docs/product/requirements.md) |
| Why we chose what we chose | [Architecture decisions](docs/decisions/README.md) |
| How we write code | [Engineering rules](docs/rules/README.md) |
| What a term means | [Glossary](docs/glossary.md) |
| Instructions for AI coding agents | [AGENTS.md](AGENTS.md) |

## Non-negotiable rules

1. Staff approve every reply. The system never sends replies or performs transactions on its own.
2. Every draft cites verifiable sources (document ID and version). Without enough evidence, the AI abstains.
3. Simulated data only. Personal data is pseudonymized before it leaves `backend`. No secrets in the repository.
4. Design before code. Contracts before implementation.

Details: [docs/rules/](docs/rules/README.md). Team roles and ownership: [ADR-0001](docs/decisions/0001-system-architecture.md#team-allocation).
