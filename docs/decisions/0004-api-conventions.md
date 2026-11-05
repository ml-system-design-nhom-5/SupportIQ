# ADR-0004: API style and conventions

- **Status:** Accepted
- **Date:** 2026-10-23
- **Deciders:** Team
- **Related:** [ADR-0001](0001-system-architecture.md), [ADR-0005](0005-intent-independent-retrieval.md), [ADR-0007](0007-observability-stack.md), [contract rules](../rules/contracts.md)

## Context

- All communication between components goes through APIs, so everything that crosses a boundary must be structured and typed.
- The system must never produce a firm answer without evidence, even when a component fails ([requirements §5](../product/requirements.md#5-quality-requirements)). Every branch, including failures, needs defined behavior.
- The team wants to start with REST and keep the option to change transport, for example to gRPC, later.

## Decision drivers

1. Defined behavior for every branch, including failures.
2. Typed, validated data at every boundary.
3. Tooling for contract-first work: code generation, mocks, contract tests.
4. Freedom to change transport later.

## Considered options

1. REST over HTTP with JSON, described in OpenAPI.
2. gRPC with Protocol Buffers.
3. GraphQL.

## Decision

1. REST over HTTP with JSON bodies, described in OpenAPI 3.1. The major version is in the path (`/v1/...`).
2. Every request, response, and error has a schema. Statuses and reason codes are enums.
3. Business outcomes are not HTTP errors. Abstention, escalation recommendation, and "LLM unavailable, no draft" return `200` with a status and reason codes. `4xx` means an invalid request; `5xx` means the provider itself failed. Error bodies follow Problem Details (RFC 9457).
4. Callers always set timeouts. If `ai-service` times out or is unreachable, `backend` switches the ticket to manual handling and records the reason.
5. Version 1 is synchronous and returns complete JSON. Streaming, if added later, is a new endpoint or media type, not a breaking change.
6. Trace context travels in the W3C `traceparent` header. Retried writes carry an `Idempotency-Key` header, which is separate from tracing because a retry belongs to the same logical operation but may start a new trace.
7. Naming, pagination, money, time, and evolution conventions are maintained in the [contract rules](../rules/contracts.md).

## Consequences

### Positive

- Simple, widely understood, and easy to debug with standard tools.
- Rich tooling: OpenAPI code generation, Prism mocks, Schemathesis tests.
- The UI has defined behavior for every outcome.

### Negative

- JSON is larger and slower than binary encodings. This is negligible because LLM calls dominate latency.

### Follow-ups

- `contracts/examples/` contains an example for every outcome of every operation.

## Pros and cons of the options

### REST with OpenAPI

- Good, because it is the simplest option, has the best contract-first tooling for Python and TypeScript, and works directly from the browser.
- Bad, because it has no built-in streaming, and its typing is only as strict as the schemas, which rule 2 makes mandatory.

### gRPC

- Good, because of compact binary encoding, strict schemas, and built-in streaming.
- Bad, because browsers cannot call it without a proxy, it is harder to debug, and its speed advantage does not matter when an LLM call takes seconds.

### GraphQL

- Good, because the UI could shape its own queries.
- Bad, because it adds a layer and tooling for access patterns that are simple and known in advance.

## Validation

- Contract tests cover every outcome of every operation.
- Transport stays in the outermost layer ([architecture rules](../rules/architecture.md#layers)), so moving to gRPC means a new adapter and no domain change. Revisit when a concrete need appears, such as many internal calls or a streaming requirement.
