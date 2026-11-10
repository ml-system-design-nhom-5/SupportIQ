# Testing rules

> **Status:** Active · **Owner:** team · **Last reviewed:** 2026-11-08

Tests are executable specifications. They catch hidden bugs early, protect the guardrails, and keep technical debt from accumulating unseen. A behavior without a test does not exist.

## Test layers

| Layer | Purpose | Location | Tools | Rules |
|---|---|---|---|---|
| Unit | Domain and application logic: routing, abstention, validity checks, reranking, ticket state | `tests/unit/`, `*.test.ts` | pytest, Hypothesis, Vitest | No network, no database, no file system; fakes only |
| Component (UI) | Design-system and feature components in every state | `*.test.tsx`, stories | Vitest, Testing Library, Storybook with axe | Interact like a user; select by role and label |
| Adapter and integration | Database, retriever, LLM, and HTTP adapters | `tests/integration/` | pytest | Local instances or fakes; default CI never calls a real LLM |
| Contract | Each component matches `contracts/` | `tests/contract/` | Schemathesis, Prism mocks | Every outcome of every operation ([contracts.md](contracts.md#contract-tests)) |
| UI flow | Main flows of one component against its mock | `frontend/e2e/` | Playwright with axe | The production build against Prism |
| End-to-end | Main staff and customer flows across all components | `e2e/` | Playwright with axe | Few tests, covering the main flow and the main failures |
| Evaluation | Macro-F1, Recall@3, groundedness, robustness, escalation | `eval/` | Python | Reproducible; reported against the baseline ([data-and-ml.md](data-and-ml.md#evaluation-and-reporting)) |

## Required tests per change

**TEST-01.** Each kind of change requires these tests in the same PR:

| Change | Required tests |
|---|---|
| New or changed domain rule | Unit tests for the normal case, every edge case in [Edge cases](#edge-cases), and every error; a property-based test when the rule has an invariant |
| New or changed use case | Unit tests with fakes for every port outcome, including each port failure |
| New or changed endpoint | Handler tests for every outcome, plus provider contract tests |
| New or changed adapter | Integration tests, including timeout, connection error, malformed response, and error mapping |
| New or changed UI component | Component tests for every state and variant, a story per state, and an accessibility check |
| New or changed user flow | An end-to-end test of the main path and its main failure |
| Bug fix | A regression test that fails before the fix and passes after it, in the same PR |
| Change to AI behavior (model, threshold, prompt, routing, retrieval) | An evaluation run compared with the previous version and the baseline |

## Writing tests

**TEST-02.** One behavior per test. A test follows Arrange, Act, Assert, with the three parts visually separated.

**TEST-03.** Test names state the unit, the scenario, and the expected result:

```python
def test_route_abstains_when_all_documents_are_expired() -> None: ...
def test_record_decision_is_idempotent_for_repeated_key() -> None: ...
```

```typescript
describe("DraftEditor", () => {
  it("disables Send reply until every warning is acknowledged", () => { ... });
});
```

**TEST-04.** Tests contain no logic: no loops, no conditionals, no try/except. Use parametrized tests for tables of cases.

**TEST-05.** Test data is built with builders or factories that set sensible defaults; a test overrides only the fields that matter to it. Magic values in tests have names.

**TEST-06.** Tests assert outcomes (returned values, state, emitted events, rendered output), not implementation details (private calls, call order) unless the call itself is the behavior, such as "no reply is sent".

**TEST-07.** Every assertion is specific. Asserting only "no exception" or "result is not None" is forbidden.

**TEST-08.** Test code follows the same rules as production code: naming, types, no duplication of knowledge, no dead code.

## Test doubles

**TEST-09.** Prefer fakes (working in-memory implementations of ports) over mocks. Mocks are allowed only at ports, and only to verify that a command was issued or not issued.

**TEST-10.** Never mock what you do not own. Wrap third-party libraries in an adapter and fake the port.

**TEST-11.** Cross-component tests use mocks generated from `contracts/`, never hand-written imitations.

## Edge cases

**TEST-12.** Tests for domain rules and boundaries consider at least:

- empty, single-element, and maximum-size inputs;
- whitespace-only text, very long text, and non-ASCII text;
- typos and unusual phrasing (Bitext `tags` slices);
- values exactly at, just below, and just above every threshold;
- validity boundaries: `effective_from == as_of`, `effective_to == as_of`, overlapping versions;
- unknown enum values and missing optional fields;
- duplicate requests with the same idempotency key;
- timeouts, retries, and partial results.

## Property-based tests

**TEST-13.** Pure domain logic with invariants has property-based tests (Hypothesis, fast-check). Required invariants include:

- routing never returns a draft unless a valid KB document version supports it, apart from a draft that states the missing information (ESC-04);
- reranking never returns an expired document in the top-k;
- a recorded decision always references the suggestion version staff saw.

## Determinism and isolation

**TEST-14.** Tests are deterministic: fixed seeds, a frozen or fake clock, no real time waits (`sleep` is forbidden in tests).

**TEST-15.** Tests run in random order and in parallel. A test that depends on another test or on execution order is a defect.

**TEST-16.** Unit tests cannot open network connections; the test runner blocks them.

**TEST-17.** Each test creates and cleans up its own data. Shared mutable fixtures are forbidden.

**TEST-18.** Test data is synthetic. Real personal or transaction data is forbidden.

## Flaky and skipped tests

**TEST-19.** A flaky test is a defect. It is quarantined within one working day with a `tech-debt` issue and fixed within the milestone. Automatic reruns to hide flakiness are forbidden.

**TEST-20.** A skipped or expected-to-fail test MUST reference an issue and a removal condition. Skips without an issue fail CI. Commented-out tests are forbidden.

## Coverage

**TEST-21.** Branch coverage is measured on every PR:

| Scope | Minimum branch coverage |
|---|---|
| Domain and application layers | 90% |
| Each component overall | 80% |

**TEST-22.** A PR MUST NOT lower the coverage of the packages it touches. Generated code is excluded.

**TEST-23.** Coverage is a floor, not a goal. Tests written only to raise coverage, without meaningful assertions, are rejected in review.

**TEST-24.** At each milestone, mutation testing SHOULD run on domain modules to find tests that pass without checking behavior. Surviving mutants in guardrail logic are fixed.

## Speed

**TEST-25.** A single unit test SHOULD run in under 100 ms. A component's full unit suite SHOULD run in under 30 s. Slow tests move to the integration layer.

## Guardrail tests

**TEST-26.** These tests MUST exist and pass at all times. Removing or weakening one requires an ADR.

- No code path sends a reply without a staff action.
- A customer never sees a draft before staff send a reply.
- No endpoint performs a refund, an order change, or any other transaction.
- The AI abstains when no valid source supports the claims a draft would make.
- Every draft segment that states a fact or a policy carries a citation of the right kind: a policy cites a valid KB document version, and a fact about the order cites a field of the order context sent with the request ([ADR-0014](../decisions/0014-citations-to-order-context.md)).
- Mandatory escalation cases from the shared scenario set are routed correctly.
- `backend` switches to manual handling when `ai-service` fails, times out, or returns an unknown status.
- Actions that require authority (FR-06) are rejected for roles without it.
- No reply is accepted while a part of the current suggestion is `pending`, and no intent override is accepted before an intent is known, so a `requires_authority` result is always known before a send.
- Confidential data never appears in logs (a test captures log output and checks for it).
- Seeded personal values of the ticket never appear in any request that `backend` sends to `ai-service`, nor in any LLM payload captured by a fake LLM adapter (FR-09, NFR-06).
- When pseudonymization fails, `backend` makes no call to `ai-service` ([SEC-36](security-and-privacy.md#pseudonymization)).
- No reply or reply proposal body that contains a placeholder is accepted ([SEC-38](security-and-privacy.md#pseudonymization)).
- An admin cannot call any `/v1/shop/` or `/v1/console/` operation, and no other role can call a `/v1/admin/` operation ([SEC-41](security-and-privacy.md#authentication-and-authorization)).
- `UPDATE` and `DELETE` on the audit log are rejected by the database ([SEC-39](security-and-privacy.md#audit-log)).
- From the `backend` container, no internet host is reachable, directly or through the egress proxy. From the `ai-service` container, only allow-listed hosts are reachable, and only through the proxy ([SEC-40](security-and-privacy.md#transport-and-runtime)).
- No admin operation returns or changes a customer account ([SEC-41](security-and-privacy.md#authentication-and-authorization)).

## End-to-end scenarios

**TEST-27.** The end-to-end suite covers at least:

- a draft approved and sent;
- a draft edited and sent;
- an abstained ticket handled manually;
- a low-confidence ticket where staff confirm the intent and a draft follows;
- an escalation handled by a manager;
- a ticket where authority is required: a staff proposal sent by a manager;
- an intent correction that produces a new draft;
- `ai-service` unavailable, then a retry that produces a draft after it recovers;
- a draft whose pseudonyms appear restored in the console, and a placeholder that blocks sending until it is replaced;
- an admin role change that takes effect on the account's next request.
