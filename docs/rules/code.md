# Code rules

> **Status:** Active · **Owner:** team · **Last reviewed:** 2026-10-23

Language-independent rules for code that is easy to read, consistent, and easy to extend. Language-specific rules build on these: [python.md](python.md) and [typescript.md](typescript.md). Examples use Python; the same rules apply in TypeScript with its own casing.

## Principles

1. Optimize for the reader. A new teammate understands a function without opening other files.
2. Consistency beats preference. Follow the existing pattern; change a pattern everywhere at once.
3. Explicit beats implicit. No hidden state, hidden I/O, or magic.
4. Small, pure, and boring beats large, clever, and surprising.
5. A pure core with an impure shell: domain logic computes, adapters do I/O.

## Naming

**CODE-01.** Identifiers MUST be in English and use [glossary](../glossary.md) terms exactly: `ticket`, `draft`, `citation`, `staff`. Synonyms (`case`, `answer`, `agent`) are forbidden for glossary concepts.

**CODE-02.** Names state meaning, not mechanics or types: `retrieve_valid_documents`, not `do_search2`; `tickets`, not `ticket_list`.

**CODE-03.** A value with a unit carries the unit in its name. Durations are always milliseconds (`timeout_ms`). Money is always minor units (`amount_minor`). Ratios in [0, 1] say so in the type or docstring.

**CODE-04.** Booleans are positive questions: `is_valid`, `has_citation`, `can_send_reply`. Negated names (`is_not_valid`, `disable_check`) are forbidden.

**CODE-05.** Collections are plural (`citations`). Mappings are named `<value>_by_<key>` (`document_by_id`). Counts are `<thing>_count`.

**CODE-06.** Each verb has one meaning across the codebase:

| Prefix | Meaning | Example |
|---|---|---|
| `get_` | Return a value already in memory; no I/O | `get_primary_citation` |
| `load_` | Read from disk or a database | `load_kb_version` |
| `fetch_` | Read over the network | `fetch_order_context` |
| `save_` | Persist an existing or new object | `save_staff_decision` |
| `build_` | Construct an object in memory | `build_prompt` |
| `compute_` | Pure calculation | `compute_rerank_score` |
| `parse_` | Turn untrusted input into a domain type, or raise | `parse_intent_label` |
| `validate_` | Check a domain rule, or raise | `validate_effective_period` |
| `to_` / `from_` | Convert between representations | `to_contract_model` |
| `is_` / `has_` / `can_` / `should_` | Answer a yes/no question | `is_expired` |
| `handle_` | Interface-layer entry point for a request or event | `handle_create_ticket` |

**CODE-07.** Vague names are forbidden: `data`, `info`, `item`, `obj`, `thing`, `stuff`, `temp`, `tmp`, `val`, `res`, `manager`, `processor`, `helper`, `util`, `do_*`, and `process_*` without an object. Single-letter names are allowed only for loop indexes in loops of three lines or fewer and for standard math notation.

**CODE-08.** No abbreviations except glossary acronyms (`kb`, `llm`) and universal ones (`id`, `url`, `http`, `api`).

**CODE-09.** Name length matches scope: short for a three-line loop, fully descriptive for module-level and public names.

```python
# Bad
def proc(d, f=True):
    res = []
    for x in d:
        if f and x.exp < now():
            res.append(x)
    return res

# Good
def select_expired_documents(documents: Sequence[KbDocumentVersion], as_of: datetime) -> tuple[KbDocumentVersion, ...]:
    return tuple(document for document in documents if document.is_expired(as_of))
```

## Functions

**CODE-10.** A function does one thing at one level of abstraction. If its description needs "and", split it.

**CODE-11.** Size and complexity limits, enforced by linters where supported:

| Measure | SHOULD | MUST |
|---|---|---|
| Body length (excluding docstring and blank lines) | ≤ 20 lines | ≤ 40 lines |
| Cyclomatic complexity | ≤ 5 | ≤ 8 |
| Nesting depth | ≤ 2 | ≤ 3 |
| Parameters | ≤ 3 | ≤ 5 |
| Return statements | ≤ 3 | ≤ 4 |

React components follow the component limits in [typescript.md](typescript.md#react).

**CODE-12.** Beyond three parameters, optional parameters are keyword-only, or the parameters are grouped into a named parameter object.

**CODE-13.** Boolean flag parameters that switch behavior are forbidden. Split the function or pass an enum.

```python
# Bad
def record_decision(ticket_id: TicketId, decision: StaffDecision, notify: bool) -> None: ...

# Good
def record_decision(ticket_id: TicketId, decision: StaffDecision) -> None: ...
def record_decision_and_notify(ticket_id: TicketId, decision: StaffDecision) -> None: ...
```

**CODE-14.** A function either changes state (a command) or returns information (a query), not both, unless its name makes both explicit (`pop_next_ticket`).

**CODE-15.** Functions MUST NOT mutate their arguments. Return a new value instead.

**CODE-16.** Guard clauses come first and return early. No `else` after `return`, `raise`, `continue`, or `break`.

```python
# Bad
def route(analysis: Analysis) -> Routing:
    if analysis.has_valid_documents:
        if analysis.confidence >= threshold:
            return Routing.DRAFT
        else:
            return Routing.ABSTAIN
    else:
        return Routing.ABSTAIN

# Good
def route(analysis: Analysis, threshold: Confidence) -> Routing:
    if not analysis.has_valid_documents:
        return Routing.ABSTAIN
    if analysis.confidence < threshold:
        return Routing.ABSTAIN
    return Routing.DRAFT
```

**CODE-17.** A function named as a query or computation performs no I/O. Logging is the only allowed side effect outside commands and adapters.

**CODE-18.** Domain code never calls the current time, a random generator, or an ID generator directly. It receives a `Clock`, a random generator, or an ID factory ([architecture.md](architecture.md#state-time-and-side-effects)).

## Modules and classes

**CODE-19.** A module has one responsibility and one reason to change. A module SHOULD stay under 300 lines and MUST stay under 500 lines.

**CODE-20.** Everything is private by default. Each module or package exposes an explicit public API (`__all__`, `index.ts`). Other modules import only that API.

**CODE-21.** Prefer composition over inheritance. Inheritance is allowed only for true "is-a" relationships, at most one level below a framework or port base type.

**CODE-22.** A class SHOULD have at most seven public methods. More means more than one responsibility.

**CODE-23.** Import cycles are forbidden at every level (enforced by tools).

**CODE-24.** Global mutable state and globally accessed singletons are forbidden. Dependencies are wired in the composition root.

**CODE-25.** Importing a module has no side effects: no I/O, no network, no environment reads, no registration.

## Types and data

**CODE-26.** Public functions, methods, and module-level values have complete type annotations. Type checkers run in strict mode and MUST pass with zero errors.

**CODE-27.** No type escape hatches: no `Any` or `any`, no unchecked casts, no type-ignore comments. The only exception is a validated boundary, with the exact error code and a reason on the same line ([RULE-04](README.md#suppressions)).

**CODE-28.** Model the domain with named types instead of primitives: identifiers (`TicketId`), quantities (`Confidence`), versions (`KbVersion`). A function that takes three plain strings is a defect.

**CODE-29.** Make invalid states unrepresentable. Model variants as tagged unions, not as one object with optional fields.

```python
# Bad: nothing stops status="draft_ready" with draft=None
@dataclass
class DraftResult:
    status: str
    draft: Draft | None
    reason_codes: list[str] | None

# Good: each outcome carries exactly the data it needs
@dataclass(frozen=True, slots=True)
class DraftReady:
    draft: Draft

@dataclass(frozen=True, slots=True)
class DraftAbstained:
    reason_codes: tuple[ReasonCode, ...]

type DraftOutcome = DraftReady | DraftAbstained
```

**CODE-30.** Every closed set (status, reason code, role, intent label) is an enum or a literal union. Comparing against string literals outside boundary parsing is forbidden.

**CODE-31.** Every match over an enum or union handles all cases explicitly, and the type checker proves exhaustiveness (`assert_never`, `never`). A catch-all branch that hides new cases is forbidden inside a component; unknown values from other components are mapped to safe values at the boundary ([CON-22](contracts.md#evolution)).

**CODE-32.** Parse, don't validate: untrusted input becomes a domain type once, at the boundary. Inner code never receives raw input and never re-checks it.

**CODE-33.** Value objects are immutable. Domain collections are immutable (tuples, frozen sets, read-only arrays).

**CODE-34.** Absence is explicit. Use an optional type only when "missing" is a meaningful state. `None`, `null`, `""`, `0`, and `-1` never signal an error or "unknown".

## Control flow

**CODE-35.** No nested conditional expressions (ternaries). One level is allowed when it fits on one line.

**CODE-36.** Complex conditions are extracted into well-named variables or functions, so each `if` reads as a sentence.

**CODE-37.** Transformations use comprehensions or `map`/`filter`; loops with side effects use explicit loops. Comprehensions never have side effects.

**CODE-38.** Every loop has a clear bound. `while True` requires an explicit exit condition and a maximum iteration count or timeout.

## Errors

**CODE-39.** Failures are signaled with specific error types, never with return codes, `None`, booleans, or error strings ([errors-and-reliability.md](errors-and-reliability.md)).

**CODE-40.** Broad catches (`except Exception`, `catch (e)` without narrowing) are allowed only in the interface layer's error handler. Re-raised errors keep their cause.

## Comments and docstrings

**CODE-41.** Comments explain why: intent, constraints, trade-offs, and links. A comment that explains what the next line does means the code needs better names.

**CODE-42.** Every public module, class, and function has a docstring: a one-line summary in the imperative mood, details when needed, parameters, return value, raised errors, and guarantees. Format per language.

```python
def compute_rerank_score(
    retrieval_score: float, intent_probability: Probability, weight: RerankWeight
) -> float:
    """Combine retrieval relevance with the intent prior.

    The weight is tuned on the validation split, never on test data (ADR-0005).

    Args:
        retrieval_score: Relevance from the content retriever, in [0, 1].
        intent_probability: Calibrated probability of the document's intent.
        weight: Contribution of the intent prior to the final score.

    Returns:
        The final ranking score. Higher scores rank first.
    """
```

**CODE-43.** Forbidden comments: commented-out code, change history, author names, dates, restatements of the code, and apologies or alarms (`hack`, `sorry`, `don't touch`).

**CODE-44.** The only allowed marker is `TODO(#<issue>): <what and why>`. `FIXME`, `XXX`, and `HACK` are forbidden. A `TODO` without an issue fails review ([WF-22](workflow.md#technical-debt)).

**CODE-45.** Non-obvious values and decisions link their source: an ADR, an issue, or an evaluation run.

## Constants and configuration

**CODE-46.** No magic numbers or strings. Allowed literals are `0` and `1` in obvious arithmetic, empty collections, and human-readable messages.

**CODE-47.** A constant lives next to the code that owns it. A constant shared across modules is exported from its owner's public API. A value that may differ per environment or experiment is configuration ([architecture.md](architecture.md#configuration)).

**CODE-48.** A value used in more than one place is defined exactly once.

## Formatting and file layout

**CODE-49.** The formatter's output is final. Line length is 100 characters in every language.

**CODE-50.** Every source file follows this order: module docstring, imports (sorted by the linter), constants, types, public functions and classes, private helpers.

**CODE-51.** Imports are absolute (Python) or use path aliases (TypeScript). Wildcard imports are forbidden.

## Consistency and change

**CODE-52.** Solve the same problem the same way. Before writing new code, look for the existing pattern and follow it.

**CODE-53.** Introducing a new pattern for an existing problem requires migrating all existing uses in the same PR, or a `tech-debt` issue linked from the PR. Two ways of doing the same thing is a defect.

**CODE-54.** Dead code, unused parameters, unused exports, and unused dependencies are deleted in the PR that makes them unused.

**CODE-55.** Duplicate knowledge is forbidden, but similar-looking code is not merged unless it changes for the same reason. Wrong abstractions are worse than duplication.

## Review checklist for code

- [ ] Names use glossary terms, state meaning, carry units, and follow the verb table.
- [ ] Functions and modules are within the size and complexity limits.
- [ ] Types are complete; no escape hatches; invalid states cannot be represented.
- [ ] Every enum and union match is exhaustive.
- [ ] Untrusted input is parsed at the boundary.
- [ ] Errors are specific types with preserved causes.
- [ ] No hidden I/O, global state, or import-time side effects.
- [ ] No magic values; tunables are configuration with documented origin.
- [ ] Docstrings exist for every public symbol; comments explain why.
- [ ] The change follows existing patterns, or migrates them.

## Smells that block review

- You must read several files to understand one function.
- Changing the LLM provider or the vector store requires changes in business logic.
- A contract changes and no test fails.
- Abstention or escalation logic sits in a prompt, a handler, or the UI.
- The same threshold or rule appears in two places.
- An error is swallowed, or a free-text string is returned instead of a reason code.
- A function takes a boolean flag that changes what it does.
- A class or module has grown a second responsibility.
