# ADR-0024: Event schema of the suggestion progress stream

- **Status:** Accepted
- **Date:** 2026-11-16
- **Deciders:** Project lead
- **Related:** [ADR-0022](0022-server-sent-events-for-suggestion-progress.md) (statement 9), [contracts](../rules/contracts.md) (CON-21, CON-27), `backend` contract 1.3.0 ([CHANGELOG](../../contracts/CHANGELOG.md))

## Context

- ADR-0022, statement 9, gives `getSuggestionEvents` "a `text/event-stream` response with a string schema and an example".
- Schemathesis 4.33.1, the version of the provider contract tests (CON-27), splits a `text/event-stream` body into events and checks each event against the schema of the response (`schemathesis/specs/openapi/validation.py`, lines 61–66). An event is an object with `event` and `data`, so a string schema fails for every event: `SSE event violates schema … is not of type "string"`. Schemathesis also checks the `data` of an event against `contentSchema` when `contentMediaType` is `application/json` (same file, line 157). It drops blocks without `data`, such as `retry: 3000`, and comments, such as `: ping`.

## Decision drivers

1. Correctness: the contract tests check every event, and that `data` holds only the three fields of statement 2 (CON-21, SEC-01).
2. Low complexity: no exception in the contract tests.

## Considered options

1. Keep the string schema and leave the `200` response of this operation out of the schema checks.
2. Describe one event in the schema of the `200` response.

## Decision

We will use option 2. It replaces only the words "with a string schema" of ADR-0022, statement 9; every other part of ADR-0022 still holds.

1. The schema of the `200` response is one event: an object with `event`, which is `suggestion`, and `data`, a string with `contentMediaType: application/json` and `contentSchema` `SuggestionProgressEvent`. It allows no other field, so an event has no `id`.
2. `SuggestionProgressEvent` has exactly `suggestion_id`, `analysis_status`, and `draft_status`, and allows no other field.
3. The example of the `200` response is one event.

## Consequences

### Positive

- Schemathesis and the documented outcomes check every event of the stream and every field of its `data`.
- `frontend` gets a generated type for the `data` of an event.

### Negative

- The example shows one event, not a whole stream; the operation description explains the stream.

### Follow-ups

- None.

## Pros and cons of the options

### Keep the string schema

- Good, because it follows statement 9 as written.
- Bad, because the contract tests would not check any event, and an extra field in `data` would pass.

### Describe one event

- Good, because every event and every field is checked, as for every other response.
- Bad, because a schema of one event is the reading of OpenAPI 3.2 for event streams, while the contracts are OpenAPI 3.1.

## Validation

- A guard proof: a test fails when the stream adds a field to `data`.
- Revisit when the contracts move to OpenAPI 3.2, which has `itemSchema` for event streams.
