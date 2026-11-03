# Error and reliability rules

> **Status:** Active · **Owner:** team · **Last reviewed:** 2026-11-01

Every failure is designed: it has a type, a defined behavior, a contract mapping, a log event, and a test. The system never turns a failure into a firm answer without evidence.

## Error taxonomy

Every error belongs to exactly one category:

| Category | Examples | Handling |
|---|---|---|
| Business outcome | Low confidence, no valid document, conflicting sources, sensitive request | Not an error for HTTP: return `200` with a status and reason codes |
| Invalid input | Schema violation, unknown ticket, forbidden action | `4xx` with Problem Details; never passed inward |
| Dependency failure | LLM timeout, `ai-service` unreachable, database unavailable | Timeout, bounded retry if idempotent, then degraded mode with a reason code |
| Defect | Broken invariant, unexpected exception | `500` with Problem Details, logged as `error` with the trace ID; never hidden |

**ERR-01.** Each component defines domain error types for its failures, for example `LowConfidenceError`, `NoValidDocumentError`, `StaleSourceError`, `ConflictingSourcesError`, `LlmUnavailableError`. Each type maps to exactly one category and, where applicable, one reason code.

**ERR-02.** Every error type carries a stable code, a safe message, and structured context (IDs, versions). It never carries confidential data ([security-and-privacy.md](security-and-privacy.md#data-classification)).

**ERR-03.** The mapping from domain errors to contract statuses, reason codes, and HTTP codes is defined in one place per component (the interface layer's error handler). No other code builds error responses.

## Handling rules

**ERR-04.** Errors are never swallowed. Empty `except` or `catch` blocks are forbidden. Catching an error requires handling it meaningfully, converting it to a domain error, or re-raising it with its cause.

**ERR-05.** An error is logged once, where it is handled, not at every layer it passes through.

**ERR-06.** Errors are never returned as strings, `None`, booleans, or magic values.

**ERR-07.** User-facing messages say what happened and what to do next. They never contain stack traces, internal names, or confidential data.

## Required behavior per failure

**ERR-08.** These behaviors are mandatory. They implement the escalation rules ESC-01 to ESC-05 of the [requirements](../product/requirements.md#41-escalation-and-fallback-rules). The exact statuses and reason codes are defined in `contracts/`.

| Failure | Required behavior |
|---|---|
| Classifier is uncertain (top-1 below τ or gap below δ) | No draft until staff confirm or correct the intent (ESC-01). Show the top three candidates |
| Intent and retrieved documents disagree | No firm draft. Show alternatives and a warning; abstain or recommend review, with a reason code |
| No valid document | Abstain with a reason code; staff handle the ticket manually |
| Only expired or conflicting documents | Do not draft from them. Flag them, then abstain or recommend escalation |
| Sensitive request: refund, transaction dispute, policy exception, legal claim, suspected fraud | Retrieval still runs. Supporting information only. Authority is required, and a manager decides (FR-06, ESC-03) |
| Customer asks for a human (`human_agent`) | No draft. Recommend escalation; staff decide (ESC-03) |
| LLM timeout, error, or rate limit | No draft. The analysis is still returned, and the reason is recorded |
| LLM output does not match the expected structure, or contains a placeholder that was not in the prompt | Treated as an LLM failure. Partial output is never used |
| Pseudonymization fails | Fail closed: nothing is sent to `ai-service`; manual handling with `pseudonymization_failed` ([SEC-36](security-and-privacy.md#pseudonymization)) |
| Draft fails the grounding check | Unsupported claims never reach staff as facts |
| `ai-service` unreachable, times out, or returns `5xx` | `backend` switches the ticket to manual handling and records the reason. The suggestion runs again when staff open the ticket or ask for a retry |
| Unknown status or reason code from another component | Treated as manual handling ([CON-22](contracts.md#evolution)) |
| Invalid input at a boundary | Rejected with a typed `4xx` error; never "fixed" silently |

## Timeouts and latency budget

**ERR-09.** Every call to another component or external service (LLM, vector store, database, HTTP) has an explicit timeout from settings. A call without a timeout is a defect.

**ERR-10.** The end-to-end target is p95 ≤ 12 s ([NFR-08](../product/requirements.md#5-quality-requirements)). Each step has a budget in settings, and the sum of step timeouts plus retries MUST fit within the end-to-end budget. The LLM step, retries included, has a budget of at most 10 s (NFR-07). The budgets are documented in the `ai-service` and `backend` design docs.

**ERR-11.** When the remaining budget is too small for a step, the step is skipped and the result degrades with a reason code; it does not run late.

## Retries

**ERR-12.** Retries apply only to idempotent operations and only to retryable failures: timeouts, connection errors, `502`, `503`, `504`, and rate limits. `4xx` responses are never retried.

**ERR-13.** Retries are bounded (maximum attempts from settings), use exponential backoff with jitter, and stop when the latency budget is exhausted.

**ERR-14.** When the LLM provider fails repeatedly, `ai-service` SHOULD stop calling it for a cooling-off period (circuit breaker) and return `llm_unavailable` immediately, so staff do not wait for each timeout.

## Idempotency

**ERR-15.** Every write operation that a client may retry accepts an `Idempotency-Key`. A repeated key with the same body returns the original result without repeating the side effect. A repeated key with a different body returns `409`.

**ERR-16.** Recording a staff decision and sending a reply are idempotent. A retry never records a decision twice or sends a reply twice.

**ERR-22.** A suggestion job can run more than once, because an expired lease is claimed again ([ADR-0011](../decisions/0011-deployment-and-runtime-topology.md#suggestion-job-queue)). A job stores its results only when its attempt number still matches the job and the suggestion is still current. A repeated or late run therefore never overwrites newer results and never records an outcome twice. The one exception is the authority flag of a superseded suggestion, which is always kept, because it can only be set to true ([ADR-0011](../decisions/0011-deployment-and-runtime-topology.md#suggestion-job-queue)).

## Startup and health

**ERR-17.** Components fail fast at startup: invalid settings, a missing or corrupt model artifact, or an invalid KB version stops startup with a clear message.

**ERR-18.** Each component exposes liveness (the process runs) and readiness (it can serve requests: settings valid, artifacts loaded, dependencies reachable). A component that is not ready returns `503` and is not sent traffic.

## Degraded mode

**ERR-19.** When a part fails, the system degrades to manual handling. It MUST NOT produce a firm answer without evidence.

**ERR-20.** Degraded mode is visible: the console shows the manual-handling state with instructions, and the reason code is recorded.

## Testing failures

**ERR-21.** Every failure path has at least one test. Dependency failures are tested with fault injection: timeouts, connection errors, `5xx` responses, malformed LLM output, and slow responses that exceed the budget ([testing.md](testing.md#required-tests-per-change)).
