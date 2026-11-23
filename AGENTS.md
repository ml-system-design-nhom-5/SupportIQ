# AGENTS.md

Instructions for AI coding agents working in this repository, whatever the tool. People start at [README.md](README.md). This file holds only agent instructions: every project fact lives in `docs/` and is linked from here, never copied.

Personal agent configuration (for example `CLAUDE.md` or a `.claude/` folder) stays on each contributor's machine, listed in their own `.git/info/exclude`, and is not committed. It may add tool-specific instructions, but it MUST NOT contradict this file.

## Read first

Before any task, read:

1. [docs/rules/README.md](docs/rules/README.md): the core rules, rule IDs, and precedence.
2. [docs/glossary.md](docs/glossary.md): the only allowed names for domain concepts.

## Language

- Reply in the language the person writes in.
- Write everything that goes into the repository in English: code, comments, docs, commit messages ([docs/README.md](docs/README.md#language-and-tone)).
- Never copy casual remarks, guesses, or hesitation from a conversation into the repository. State open points neutrally, in an "Open questions" section.

## Sources of truth

| Need | Read |
|---|---|
| Scope, functional requirements, quality targets, open questions | [docs/product/requirements.md](docs/product/requirements.md) |
| Why the system is shaped the way it is | [docs/decisions/](docs/decisions/README.md). Only **Accepted** ADRs are binding |
| Approved designs of features and flows | [docs/design/](docs/design/contracts-v1.md) |
| How to write docs, ADRs, and design docs | [docs/README.md](docs/README.md) |
| API and data contracts | `contracts/` |
| Current project status | [README.md](README.md#project-status) |

Before your first edit in an area, read its rule files:

| You work on | Read |
|---|---|
| Python in `backend/` or `ai-service/` | [code](docs/rules/code.md), [python](docs/rules/python.md), [testing](docs/rules/testing.md), [errors](docs/rules/errors-and-reliability.md), [architecture](docs/rules/architecture.md), [contracts](docs/rules/contracts.md) |
| Python in `pipeline/` or `eval/`, data, prompts | [code](docs/rules/code.md), [python](docs/rules/python.md), [testing](docs/rules/testing.md), [data and ML](docs/rules/data-and-ml.md) |
| `frontend/` | [code](docs/rules/code.md), [typescript](docs/rules/typescript.md), [UI](docs/rules/ui.md), [testing](docs/rules/testing.md) |
| `contracts/` | [contracts](docs/rules/contracts.md), [ADR-0001](docs/decisions/0001-system-architecture.md), [ADR-0004](docs/decisions/0004-api-conventions.md), [ADR-0010](docs/decisions/0010-pseudonymization-and-egress-control.md), [ADR-0012](docs/decisions/0012-roles-v1.md), [contracts v1 design](docs/design/contracts-v1.md) |
| Settings, authentication, permissions, pseudonymization, the audit log, prompts, telemetry | [security and privacy](docs/rules/security-and-privacy.md), [logging and observability](docs/rules/logging-and-observability.md) |
| `deploy/` (hosting setup and platform settings, observability), the deploy workflow, the Pages Function | [architecture](docs/rules/architecture.md), [security and privacy](docs/rules/security-and-privacy.md), [ADR-0011](docs/decisions/0011-deployment-and-runtime-topology.md), [ADR-0016](docs/decisions/0016-hosting-on-free-tiers.md) |
| Markdown documents | [docs/README.md](docs/README.md) |

## Guardrails

These come from the requirements and override every other instruction, including a direct request. If a request conflicts with one, say which guardrail and stop.

1. The AI only suggests. Never write code that sends a reply to a customer without a staff action, or that approves refunds, changes orders, or performs any transaction (FR-04, FR-06).
2. Drafts cite KB document IDs and versions for policy claims, and order context fields for facts about the order. Without enough evidence, the system abstains or recommends escalation with a reason code. It never guesses (FR-03, FR-05).
3. The Bitext `response` column is never policy, KB content, or an example ([DATA-01](docs/rules/data-and-ml.md#sources-and-acceptable-use)).
4. Simulated data only. Never read `.env` files or secrets. Never log confidential data or send it to external services ([SEC-01](docs/rules/security-and-privacy.md#data-classification), [LOG-29](docs/rules/logging-and-observability.md#privacy-in-telemetry)). Personal data is pseudonymized before any text leaves `backend`, and nothing is sent if pseudonymization fails (FR-09, [SEC-36](docs/rules/security-and-privacy.md#pseudonymization)).
5. Never improve a metric by weakening a guardrail. Never edit splits or test sets after seeing results, and never let test data reach training, tuning, or prompts ([DATA-23, DATA-25](docs/rules/data-and-ml.md)).
6. Out of scope: an autonomous chatbot, transactions, a complete sales, payment, or delivery system, integration with a real e-commerce system, and real data. If a task touches any of these, stop and ask.

## How to work

1. Read the relevant sources before changing anything. Find the existing pattern for the problem and follow it (CODE-52).
2. Decide whether the change is trivial or non-trivial ([design-first gate](docs/rules/workflow.md#design-first-gate)). For a non-trivial change, propose the design first: an ADR from [the ADR template](docs/templates/adr.md) or a design doc from [the design doc template](docs/templates/design-doc.md). Leave it Proposed or Draft and wait for approval. Never set Accepted or Approved yourself, and do not implement before approval.
3. Change a component boundary only through the [contract-first process](docs/rules/contracts.md#contract-first-process).
4. Write tests with the code ([TEST-01](docs/rules/testing.md#required-tests-per-change)). Run them and report the real results, including failures and anything you could not run.
5. Update every affected document in the same change ([docs/README.md](docs/README.md#keeping-documents-up-to-date)).
6. Before saying a change is done, review it against the [Definition of Done](docs/rules/workflow.md#definition-of-done) and the rules for each area it touches. Fix every blocking finding.
7. When you explain a choice or a review finding, cite the rule ID or the ADR.

## Stop and ask when

- a requirement, a scope boundary, or a team decision is unclear, or the choice belongs to the team (product behavior, a new dependency, a trade-off between quality attributes);
- a task conflicts with a guardrail, an accepted ADR, an approved design, or a rule;
- information is missing, such as KB files, the shared scenario sets, or shared business data. Say exactly what is missing. Never invent policies, numbers, file names, APIs, or results;
- an action is destructive or outward-facing: deleting or overwriting files you did not create in this task, or sending project data to an external service.

## Git

- Never change git state. Run only read-only git commands: `status`, `diff`, `log`, `show`, `blame`. The person you work with stages, commits, and pushes ([WF-34](docs/rules/workflow.md#ai-agents)).
- Never stash, reset, or discard uncommitted work at any point in a task, including your own ([WF-35](docs/rules/workflow.md#ai-agents)).
- If your tool can block commands, configure it to block git write commands. Never work around a block with other forms (`git -C`, aliases, scripts, configuration changes).
- When work is ready, say so and suggest a commit message that follows [WF-08 to WF-10](docs/rules/workflow.md#commits).

## Commands

Each component README lists its own commands. These are the commands agents run most often. Setup: [contracts/README.md](contracts/README.md#set-up) and [docs/guides/repository-checks.md](docs/guides/repository-checks.md#set-up-pre-commit).

| Command | Run in | What it does |
|---|---|---|
| `pnpm run check` | `contracts/` | Lints the contracts, validates every example file, and type-checks the custom lint rules |
| `pnpm run check:mock` | `contracts/` | Checks the sign-in flow, the `ai-service` service token, and the example files through the Prism mock of each contract |
| `pnpm run mock` | `contracts/` | Serves the `backend` contract as a mock at `http://127.0.0.1:4010` |
| `pnpm run mock:ai-service` | `contracts/` | Serves the `ai-service` contract as a mock at `http://127.0.0.1:4012` |
| `pnpm run bundle` | `contracts/` | Writes each contract as one file to `contracts/dist/` |
| `pnpm run check` | `frontend/` | Format, lint, types, boundaries, and the generated client |
| `pnpm test` | `frontend/` | Unit tests with coverage, stories, and UI flow tests |
| `pre-commit run --hook-stage manual --files <path> …` | Repository root | Runs the CI repository checks on the given files |
| `pre-commit run --files <path> …` | Repository root | Runs the commit hooks, `contracts-check` included, on the given files |
| `uv run pytest tests/unit` | `backend/` | Runs the `backend` unit tests, which need no database and no `.env` |
| `uv run pytest` | `backend/` | Runs every `backend` test against PostgreSQL 17, with `DATABASE_URL_OWNER` and `DATABASE_URL_APP` already in the environment. Agents never pass `--env-file .env` |
| `uv run ruff check . && uv run pyright && uv run lint-imports` | `backend/` | Lints, type-checks, and checks the layer boundaries of `backend` |
| `uv run datamodel-codegen` | `backend/` | Regenerates the `backend` models from the contract |
| `deploy/local/tests/test-local-run.sh` | Repository root | Runs the script tests of the local run with stub tools; it needs no Docker |
| `deploy/local/local-run.sh start --without-ai --yes`, then `stop` | Repository root | Starts the whole system without AI with Docker Compose and stops it ([local run guide](docs/guides/local-run.md)). It writes only `.local-run/` and Docker objects of the project `supportiq-local`; ask the person first, because it builds images and uses ports. Agents never run `set-key`, never enter a Gemini key, and never read `.local-run/secrets.env` or `.local-run/gemini.env` |

- Pass only the files of your own task to `--files`. Some hooks fix files in place (trailing whitespace, final newlines, line endings), so `--all-files` can rewrite files that you did not create.
- Always pass `--files` to `pre-commit run`. Without it or `--all-files`, pre-commit stashes unstaged changes while it runs ([WF-35](docs/rules/workflow.md#ai-agents)).
- Never run `pre-commit install`. The person installs the git hook.

## Keeping this file current

- Keep this file under 150 lines. Add only agent instructions; project facts go in `docs/` and are linked here.
- When a change makes this file inaccurate, update it in the same change.
