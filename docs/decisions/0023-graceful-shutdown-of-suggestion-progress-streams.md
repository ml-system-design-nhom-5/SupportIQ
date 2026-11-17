# ADR-0023: Graceful shutdown of suggestion progress streams

- **Status:** Accepted
- **Date:** 2026-11-16
- **Deciders:** Project lead
- **Related:** [ADR-0022](0022-server-sent-events-for-suggestion-progress.md) (statement 5), [ADR-0016, `backend` on Render](0016-hosting-on-free-tiers.md#backend-on-render), [backend ticket workflow design](../design/backend-ticket-workflow.md#the-suggestion-progress-stream), [ERR-09](../rules/errors-and-reliability.md), [CODE-03](../rules/code.md)

## Context

- ADR-0022, statement 5, says: "At shutdown: the lifespan ends every stream before uvicorn's graceful shutdown, within Render's 30 s." Render gives a service 30 s after `SIGTERM` ([ADR-0022, Context](0022-server-sent-events-for-suggestion-progress.md#the-ingress-and-the-hosting)).
- uvicorn 0.54.0, the version that `backend` pins, cannot do that. `Server.shutdown` in `uvicorn/server.py` closes the listeners (line 281 on), waits for every open connection and task with `timeout=self.config.timeout_graceful_shutdown` (lines 297–299), cancels the tasks left when that timeout passes (line 307), and only then calls `self.lifespan.shutdown()` (line 311). The default timeout is None, so uvicorn waits for an open stream for up to `suggestion_events_max_ms`, 600 000 ms.
- While uvicorn waits, the claim loop still runs. A job that is running when the shutdown starts usually ends within its two `ai-service` calls, 3 000 ms and 11 000 ms, so its stream ends with its last event before 15 000 ms. A job still queued, or one that retries, stays `pending` longer, and its stream is cancelled.

## Decision drivers

1. Reliability: a replica stops within Render's 30 s, and the lifespan still stops the claim loop and flushes traces.
2. Low complexity: no dependence on uvicorn internals.

## Considered options

1. Bound uvicorn's graceful shutdown with a setting.
2. Subclass `uvicorn.Server` so that its `shutdown` ends every stream before uvicorn waits.

## Decision

We will use option 1. It replaces only the point "At shutdown" of ADR-0022, statement 5; every other part of ADR-0022 still holds.

1. `backend serve` passes `timeout_graceful_shutdown` to uvicorn from the setting `graceful_shutdown_timeout_ms`, 15 000 by default, in whole seconds (ERR-09, CODE-03).
2. A stream still open after that time is cancelled by uvicorn. `EventSource` reconnects after the `retry: 3000` of the stream to a replica that runs, or the console falls back to the 30 s poll of [ADR-0022, statement 7](0022-server-sent-events-for-suggestion-progress.md#decision).
3. The lifespan then stops the claim loop and flushes the traces, within the 30 s of Render.

## Consequences

### Positive

- A replica stops within a known time, with one setting and no new code at shutdown.

### Negative

- A stream cancelled at shutdown ends without its last event. The console sees an error, reconnects, and reads the state again.
- Every response still open after 15 s is cancelled, not only streams.

### Follow-ups

- Measure the shutdown of a replica with an open stream on Render, with the checks of the [deploy guide](../../deploy/README.md#first-deploy-checklist).

## Pros and cons of the options

### Bound uvicorn's graceful shutdown with a setting

- Good, because it uses a documented option of uvicorn, and the value is a typed setting.
- Bad, because an open stream ends by cancellation, not with an event.

### Subclass `uvicorn.Server`

- Good, because every stream could end cleanly when the shutdown starts.
- Bad, because it overrides an internal method of uvicorn, which can change in any release, and the composition root must hand the streams of the app to the server.

## Validation

- A unit test checks that `backend serve` passes the setting to uvicorn.
- Revisit when `backend` changes its server or its uvicorn version, or when a host gives other than 30 s after `SIGTERM`.
