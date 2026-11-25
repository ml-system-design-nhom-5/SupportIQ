# Engineering rules

> **Status:** Active · **Owner:** team · **Last reviewed:** 2026-11-11

These rules make the codebase clean, consistent, easy to understand, and easy to extend for the life of the project. They apply to all code in the repository (`frontend`, `backend`, `ai-service`, `ml`, `eval`, `contracts`, scripts, and configuration) and to every contributor, human or AI agent. Documentation rules are in the [documentation handbook](../README.md).

## How to read the rules

- Keywords follow [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119):
  - **MUST** and **MUST NOT** are blocking. A PR that breaks one is not merged.
  - **SHOULD** and **SHOULD NOT** are strong defaults. Breaking one requires a written reason in the PR description, and the reviewer must agree.
  - **MAY** marks an option.
- Every normative rule has a stable ID, such as `CODE-12`. The prefix names the file.
- Rule text is normative. Examples illustrate it.

**RULE-01.** Review comments about a rule MUST cite its ID, for example `blocking: CODE-14`.

**RULE-02.** Rule IDs are never renumbered or reused. A removed rule's ID is retired.

## Precedence

When two rules conflict, follow the higher one and open a PR that removes the conflict.

1. Safety guardrails in the [requirements](../product/requirements.md#5-quality-requirements): staff approve every reply, no automatic transactions, no firm answers without evidence.
2. Accepted [ADRs](../decisions/README.md).
3. These rules.
4. Formatter and linter defaults.

## Principles behind the rules

1. **Optimize for the reader.** Code is read far more often than it is written.
2. **Consistency beats preference.** One way to do each thing, everywhere.
3. **Explicit beats implicit.** No hidden state, hidden I/O, or magic values.
4. **Extend by adding, not by editing.** New behavior arrives as a new module, adapter, or configuration entry, not as another branch in existing code.
5. **Fail loudly and safely.** Every failure is typed, handled, tested, and never turned into a firm answer without evidence.
6. **Prove it.** A behavior without a test, or a metric without a measurement, does not count.
7. **Leave no hidden debt.** Every known shortcut is recorded and owned.

## The ten core rules

1. **Design before code.** Non-trivial changes start with an approved design doc or ADR. ([workflow](workflow.md#design-first-gate))
2. **Contract before implementation.** Any change at a component boundary starts in `contracts/`. ([contracts](contracts.md))
3. **Components talk only through contracts.** No imports across components. ([architecture](architecture.md#component-boundaries))
4. **Business logic is independent** of frameworks, LLM providers, and databases. ([architecture](architecture.md#layers))
5. **One responsibility per module and function.** Names state meaning, not mechanics. ([code](code.md))
6. **No magic values and no secrets in code.** Configuration is typed and validated at startup. ([code](code.md#constants-and-configuration), [security](security-and-privacy.md))
7. **Errors are designed.** Every failure has a type, a contract mapping, and a test. ([errors](errors-and-reliability.md))
8. **Tests ship with code.** Metrics are re-measured, never assumed. ([testing](testing.md), [data and ML](data-and-ml.md))
9. **Docs ship with code.** ([documentation handbook](../README.md#keeping-documents-up-to-date))
10. **When unsure, ask.** Never invent policies, numbers, results, or APIs.

## Rule files

| File | Prefix | Covers |
|---|---|---|
| [workflow.md](workflow.md) | `WF` | Design-first gate, branches, commits, PRs, reviews, CI, Definition of Done, technical debt, dependencies |
| [architecture.md](architecture.md) | `ARCH` | Component boundaries, layers, feature modules, dependency injection, configuration, extension recipes |
| [contracts.md](contracts.md) | `CON` | Contract-first process, OpenAPI style, API conventions, evolution, contract tests |
| [code.md](code.md) | `CODE` | Naming, functions, modules, types, control flow, comments, constants, consistency |
| [python.md](python.md) | `PY` | Python toolchain, typing, errors, async, FastAPI, persistence, settings |
| [typescript.md](typescript.md) | `TS` | TypeScript toolchain, compiler options, types, React, API access |
| [errors-and-reliability.md](errors-and-reliability.md) | `ERR` | Error taxonomy, required failure behavior, timeouts, retries, degraded mode |
| [testing.md](testing.md) | `TEST` | Test layers, required tests per change, test design, determinism, coverage, guardrail tests |
| [logging-and-observability.md](logging-and-observability.md) | `LOG` | Log schema, events, traces, metrics, dashboards, the single observability screen |
| [security-and-privacy.md](security-and-privacy.md) | `SEC` | Data classification, LLM data rules, secrets, access control, prompt injection, incidents |
| [data-and-ml.md](data-and-ml.md) | `DATA` | Datasets, KB, splits, leakage, artifacts, prompts, evaluation, feedback, drift |
| [ui.md](ui.md) | `UI` | Design system, tokens, console interaction, states, content, accessibility, password fields, developer views |

## Enforcement

**RULE-03.** A rule that a tool can check MUST be checked by a tool, in pre-commit hooks and in CI. Rules that only a human can check are part of the [Definition of Done](workflow.md#definition-of-done).

| Concern | Tool | Runs in |
|---|---|---|
| Formatting | ruff format, Prettier | pre-commit, CI |
| Linting and complexity limits | ruff, ESLint | pre-commit, CI |
| Types | pyright (strict), tsc (strict) | CI |
| Layer and feature boundaries | import-linter, dependency-cruiser | CI |
| Tests and coverage | pytest, Vitest, Playwright | CI |
| Contracts | Redocly CLI with custom rules and example validation, Prism mocks, Schemathesis, generated-code freshness check | pre-commit, CI |
| Secrets | gitleaks | pre-commit, CI |
| Dependency vulnerabilities | pip-audit, pnpm audit | CI |
| Documentation: style, relative links, and anchors | markdownlint-cli2 with markdownlint-rule-relative-links | pre-commit, CI |
| Accessibility | axe (Storybook and Playwright) | CI |

Framework-level tool choices come from [ADR-0003](../decisions/0003-tech-stack.md) and [ADR-0008](../decisions/0008-ui-design-system.md) ([WF-29](workflow.md#dependencies)). Every other tool is justified where it is configured ([WF-27](workflow.md#dependencies)): the Tools table of [contracts/README.md](../../contracts/README.md#tools) and the checks table of [repository checks](../guides/repository-checks.md#what-runs-where). The repository-wide checks and the contract checks are configured in `.pre-commit-config.yaml` and `contracts/` ([repository checks](../guides/repository-checks.md)). Component configuration files are created when each component is scaffolded. External links are not checked yet ([repository checks, Open questions](../guides/repository-checks.md#open-questions)).

## Suppressions

**RULE-04.** A suppression MUST be inline, name the exact rule code, and give a reason on the same line, for example `# noqa: PLR0913  # mirrors the contract's six fields, #42`.

**RULE-05.** File-level or project-level disabling of a linter or type-checker rule MUST NOT happen without a PR that changes the shared configuration and explains why. Blanket suppressions (`# type: ignore`, `eslint-disable` without a rule name) are forbidden.

## Changing a rule

**RULE-06.** Rules change only through a PR that edits the rule file and explains why. A rule change that alters the architecture or a contract needs an ADR. Update **Last reviewed** in every file you touch.
