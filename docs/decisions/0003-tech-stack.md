# ADR-0003: Technology stack

- **Status:** Accepted
- **Date:** 2026-10-23
- **Deciders:** Team
- **Related:** [ADR-0001](0001-system-architecture.md), [ADR-0004](0004-api-conventions.md), [ADR-0007](0007-observability-stack.md), [ADR-0008](0008-ui-design-system.md), [Python rules](../rules/python.md), [TypeScript rules](../rules/typescript.md)

## Context

- ML work (training, evaluation, inference) is practically bound to Python.
- No team member has deep expertise in a particular language. The team wants a reasonable, balanced, extensible stack and is ready to learn it.
- Contract-first development ([ADR-0001](0001-system-architecture.md)) needs code generation from OpenAPI, mock servers, and contract testing.
- Choices that are likely to change (LLM provider, vector store) must not block the start.

## Decision drivers

1. Fit for ML work.
2. Few languages and toolchains.
3. Strong support for contract-first development.
4. Popular, well-documented tools.
5. Volatile choices stay replaceable behind adapters.

## Considered options

- Backend: FastAPI (Python), Django (Python), NestJS (TypeScript).
- Frontend: React single-page application with Vite, Next.js.

## Decision

| Area | Choice |
|---|---|
| `backend` | Python, FastAPI, Pydantic, pydantic-settings, SQLAlchemy 2, Alembic, httpx |
| `backend` storage | PostgreSQL |
| `ai-service` | Python, FastAPI, Pydantic, pydantic-settings. Stateless; no database in v1 |
| `ml/` and `eval/` | Python, scikit-learn, pandas |
| `frontend` | TypeScript, React, Vite, shadcn/ui (Radix and Tailwind CSS), TanStack Query, React Router |
| Contracts | OpenAPI 3.1 written by hand; datamodel-code-generator for Python models; openapi-typescript and openapi-fetch for the TypeScript client; Prism for mocks; Schemathesis for provider tests |
| Python quality | uv, ruff, pyright (strict), pytest, Hypothesis, import-linter |
| TypeScript quality | pnpm, ESLint with typescript-eslint, Prettier, Vitest, Testing Library, dependency-cruiser |
| End-to-end tests | Playwright |
| Repository hygiene | pre-commit, gitleaks |
| Local runtime | Docker Compose: one command starts the whole system |

Decided in separate ADRs: observability ([ADR-0007](0007-observability-stack.md)) and the UI design system ([ADR-0008](0008-ui-design-system.md)).

Deferred, behind adapters, each to its own ADR when chosen from measurements: LLM provider, embedding model, vector store, second ML model, session mechanism, and artifact storage.

Exact versions are pinned when each component is scaffolded.

## Consequences

### Positive

- Two languages for the whole system. Three of four members share Python and one toolchain.
- Pydantic models generated from OpenAPI fit contract-first development.
- Async FastAPI suits `backend` calling `ai-service` in parallel with timeouts.

### Negative

- FastAPI does not bundle an admin, authentication, or an ORM. The team assembles them and keeps the structure defined in the [architecture rules](../rules/architecture.md).
- Two code-generation pipelines: Python and TypeScript.

### Follow-ups

- Configuration files for every tool are created at scaffold, matching the Python and TypeScript rules.
- One ADR for each deferred choice.

## Pros and cons of the options

### FastAPI

- Good, because it is type-first with Pydantic, async, and the same language as `ai-service`.
- Bad, because the ORM, migrations, and authentication must be assembled.

### Django

- Good, because admin, ORM, and authentication are included.
- Bad, because its Active Record ORM ties the domain to the framework, which works against ports and adapters.

### NestJS

- Good, because it shares a language with `frontend` and is structured by default.
- Bad, because it adds a second backend toolchain, and the backend engineer cannot easily help the AI engineers.

### React with Vite

- Good, because the build is simple and there is no server rendering to learn; it fits an internal tool.
- Bad, because it has no server rendering, which this project does not need.

### Next.js

- Good, because it is a full-stack framework with a large ecosystem.
- Bad, because server rendering and server components add concepts without value for an internal console.

## Validation

- One command starts the whole system locally.
- Code generation and contract tests run in CI for both contracts.
- Revisit if a deferred choice requires a different runtime.
