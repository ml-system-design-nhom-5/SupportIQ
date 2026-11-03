# Documentation handbook

> **Status:** Active · **Owner:** team · **Last reviewed:** 2026-10-28

This handbook tells you where each document lives and how to write it. It applies to every contributor, human or AI agent. A change is not done until its documentation is correct.

## Principles

1. **Docs as code.** Docs live in this repository, change in the same pull request (PR) as the behavior they describe, and are reviewed like code.
2. **Design before code.** Non-trivial work starts with a design doc or an ADR, not with code.
3. **One source of truth.** Every fact lives in one place. Other documents link to it.
4. **Accurate or absent.** A wrong document is worse than a missing one. Fix it or delete it.
5. **Reader first.** Every document states its audience and purpose and leads with what the reader needs.

## Where documents live

| Location | Contains | Owner |
|---|---|---|
| [`README.md`](../README.md) | Project entry point: what, why, status, where to go next | team |
| [`docs/product/`](product/requirements.md) | Requirements and scope | team |
| [`docs/decisions/`](decisions/README.md) | Architecture decision records (ADRs): why we chose what we chose | team |
| [`docs/design/`](design/contracts-v1.md) | Design docs: how a feature will work, written before code | feature owner |
| `docs/architecture/` | Living description of the system as it is today: components, flows, data | team |
| `docs/guides/` | How-to guides: set up, run, evaluate | component owner |
| [`docs/rules/`](rules/README.md) | Engineering rules every contributor follows | team |
| [`docs/templates/`](templates/adr.md) | Templates for ADRs and design docs | team |
| [`docs/glossary.md`](glossary.md) | Canonical domain terms | team |
| `contracts/` | API and data contracts, with examples and a changelog | contracts gatekeeper |
| `<component>/README.md` | How to run, test, and navigate one component | component owner |
| [`AGENTS.md`](../AGENTS.md) | Instructions for AI coding agents, whatever the tool. It links to these docs and never restates them. Personal agent configuration (for example `CLAUDE.md`, `.claude/`) is not committed | team |

Locations without a link do not exist yet. Create them when the first document of that type is written.

## Which document to write

| Situation | Write |
|---|---|
| You choose between options that are hard to reverse or affect more than one component | ADR |
| You plan a feature or a change that crosses a component boundary | Design doc |
| You change an API or a data contract | A change in `contracts/` plus a changelog entry |
| You describe how the system works now | Architecture doc |
| You explain how to complete a task | Guide |
| You add a rule contributors must follow | Rule in `docs/rules/` |
| You introduce a domain term | Glossary entry |

## Design before code

Non-trivial changes pass the design-first gate: design doc or ADR → review → contract change (if a boundary moves) → implementation with tests and docs. The definition of "non-trivial" and the full flow are in [rules/workflow.md](rules/workflow.md#design-first-gate). Implementation of a non-trivial change MUST NOT start before its design is approved.

## Writing rules

The keywords MUST, MUST NOT, SHOULD, SHOULD NOT, and MAY are used as defined in [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119).

### Language and tone

- Docs, code comments, commit messages, and identifiers MUST be in English (US spelling).
- Use plain language: short sentences, active voice, present tense.
- Lead with the conclusion. Background and details come after.
- Write steps in the imperative mood ("Run the tests"), one action per step.
- Use [glossary](glossary.md) terms exactly. Do not use synonyms for domain terms. A new term MUST be added to the glossary in the same PR.
- Define each acronym at its first use in a document, unless the glossary defines it.
- Be specific: numbers with units, exact names, exact paths. Avoid vague words such as "fast", "soon", "some", "simply", and "easy".

### Structure

- Every document under `docs/` starts with one H1 title, a metadata line, and one to three sentences stating its purpose and audience. Metadata line format:

  ```markdown
  > **Status:** Draft | Active | Deprecated · **Owner:** <component or role> · **Last reviewed:** YYYY-MM-DD
  ```

- ADRs and design docs use the header from their template instead. Templates themselves are exempt.
- The root README and component READMEs start with a one-paragraph summary instead of a metadata line.
- One H1 per file. Use sentence case for headings. Do not skip heading levels.
- One topic per document. Split a document when it covers two topics.
- Facts and open questions MUST NOT be mixed. Put unresolved points in an "Open questions" section.

### Flows and diagrams

- Every flow with more than two steps MUST have a diagram.
- Diagrams MUST be Mermaid code inside the Markdown file, so they are versioned, diffable, and rendered by GitHub. Use an image only when Mermaid cannot express the diagram, and commit its source next to it.
- Show failure paths, not only the happy path: timeouts, missing data, low confidence, unavailable components.
- Label every arrow with what moves along it: a request, data, or a decision.
- Use the same names in diagrams as in code and the glossary.

### Accuracy

- Describe what is true now. Mark anything planned as planned, or move it to a design doc.
- MUST NOT invent policies, numbers, results, file names, or APIs. If information is missing, say it is missing.
- Every reported number links to its source: an evaluation run, a requirement, or an ADR.
- Code samples MUST work as written, or be labeled as pseudo-code.

### Single source of truth

| Topic | Source |
|---|---|
| Scope and requirements | [product/requirements.md](product/requirements.md) |
| Terms | [glossary.md](glossary.md) |
| Decisions and their reasons | [decisions/](decisions/README.md) |
| API and data contracts | `contracts/` |
| Engineering rules | [rules/](rules/README.md) |

- A summary elsewhere is allowed only if it is short and links to its source.
- If a copy disagrees with its source, the source wins and the copy is a bug.

### Keeping documents up to date

- A PR that changes behavior, a contract, a configuration option, a command, or a rule MUST update every affected document in the same PR.
- Reviewers MUST request changes on a PR that leaves documentation stale.
- Update **Last reviewed** whenever you confirm a document is still correct, even if you changed nothing.
- Before each project milestone closes, owners review their documents. A document not reviewed since the previous milestone is reviewed or deleted.
- Never leave a "may be outdated" note. Fix the document or delete it.
- To retire a document, set its status to Deprecated and link its replacement. Delete it once nothing links to it.

### Files and formatting

- File names use `kebab-case.md`. ADRs use `NNNN-kebab-case-title.md`.
- Link to repository files with relative links. Do not paste bare URLs; use descriptive link text.
- Every code block has a language tag (`text` for directory trees and plain output).
- Use tables for comparisons, lists for items, and prose for reasoning.
- Once CI exists, it runs a Markdown linter and a link checker on `docs/` and every `README.md`.

## ADRs

Write an ADR when a decision is hard to reverse, affects more than one component, or chooses between options with different quality trade-offs.

- Use the [ADR template](templates/adr.md). Process and index: [decisions/README.md](decisions/README.md).
- One decision per ADR. Numbers are sequential and never reused.
- An ADR MUST state the context and constraints, ranked decision drivers, at least two considered options, the decision as verifiable statements, positive and negative consequences, and how the decision is validated or when to revisit it.
- Accepted ADRs are not edited except for typos, broken links, and the status change to Superseded. To change a decision, write a new ADR.

## Design docs

- Use the [design doc template](templates/design-doc.md). Save it as `docs/design/<kebab-case-feature>.md`.
- Status lifecycle: Draft → In review → Approved → Implemented, or Abandoned.
- To change an Approved design before it is implemented, write a revision: set the status back to In review, describe the revision and its date in the summary, keep the earlier decisions it replaces under "Alternatives considered", and get approval again from the same reviewers. A design that is already Implemented is not revised; write a new design doc instead.
- After implementation, update the living docs (`docs/architecture/`, component READMEs). The design doc stays as the record of what was planned and why.

## Review checklist for documentation

- [ ] Purpose and audience are stated at the top.
- [ ] Content matches the code and contracts in the same PR.
- [ ] Glossary terms are used; new terms are added to the glossary.
- [ ] Every multi-step flow has a Mermaid diagram that includes failure paths.
- [ ] Every number has a source; nothing is invented.
- [ ] Links work; status, owner, and last-reviewed date are current.
