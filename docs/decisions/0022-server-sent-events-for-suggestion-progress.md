# ADR-0022: Server-sent events for the suggestion progress of an open ticket

- **Status:** Accepted
- **Date:** 2026-11-13
- **Deciders:** Project lead
- **Related:** [Requirements](../product/requirements.md) (NFR-08, NFR-11), [ADR-0009](0009-demo-accounts-and-cookie-sessions.md), [ADR-0011](0011-deployment-and-runtime-topology.md) ([Ingress](0011-deployment-and-runtime-topology.md#ingress), [`backend` replicas](0011-deployment-and-runtime-topology.md#backend-replicas), [Suggestion job queue](0011-deployment-and-runtime-topology.md#suggestion-job-queue)), [ADR-0016](0016-hosting-on-free-tiers.md) ([`frontend` and the ingress](0016-hosting-on-free-tiers.md#frontend-and-the-ingress-on-cloudflare-pages), [`backend` on Render](0016-hosting-on-free-tiers.md#backend-on-render), [PostgreSQL on Supabase](0016-hosting-on-free-tiers.md#postgresql-on-supabase)), [contracts v1 design](../design/contracts-v1.md#non-goals), [console UI design](../design/console-ui.md#flow), [backend ticket workflow design](../design/backend-ticket-workflow.md#suggestions-and-the-job-queue), [SEC-01](../rules/security-and-privacy.md#data-classification), [LOG-29](../rules/logging-and-observability.md#privacy-in-telemetry)

## Context

Every web source below was read on 2026-11-13. A point that no source settles is marked "not documented".

### The problem

- The console learns that a suggestion part finished only by polling.
  - The approved console UI design polls the workspace, `getConsoleTicket`, every 2 s while a part is `pending`, and the inbox every 15 s ([console UI design](../design/console-ui.md#flow), revision of 2026-11-12).
  - The contracts v1 design lists "Streaming or push updates. `frontend` polls." as a non-goal ([contracts v1, Non-goals](../design/contracts-v1.md#non-goals)).
- On 2026-11-13 the project lead decided two things: the console never polls more often than every 30 s, and the team should check whether server-sent events (SSE) fit.
  - The inbox moves to 30 s in any case.
  - This ADR covers only the workspace of one open ticket.
- A part stays `pending` for at most the draft timeout, 11 000 ms. The end-to-end p95 target is 12 s ([NFR-08](../product/requirements.md#5-quality-requirements); [ADR-0011, Suggestion job queue](0011-deployment-and-runtime-topology.md#suggestion-job-queue), item 8). With a 30 s poll, staff see a stored draft up to 30 s after it is stored.
- Handling time for NFR-11 runs from the first view to the reply ([backend ticket workflow design, Reports](../design/backend-ticket-workflow.md#reports)). Every wait for a draft adds to the handling time of the `assisted` mode: the wait after a first view, after an intent correction, and after a retry. A longer display delay therefore works against the assisted mode in the product-value comparison of NFR-11.

### How a replica learns that a job finished

- **Any replica can finish a job.** Jobs run in the claim loop of any replica ([ADR-0011, Suggestion job queue](0011-deployment-and-runtime-topology.md#suggestion-job-queue), item 2), and a replica keeps no state between requests ([`backend` replicas](0011-deployment-and-runtime-topology.md#backend-replicas), item 1). The demo runs one replica ([ADR-0016, `backend` on Render](0016-hosting-on-free-tiers.md#backend-on-render), item 1): a free Render service cannot scale "beyond a single instance" ([Render, Free instances](https://render.com/docs/free)). The rules still have to hold with more replicas.
- **The existing pattern.** The claim loop already combines two signals: an in-process wake-up after a commit, and a poll every `suggestion_queue_poll_ms` for work that another replica committed ([backend ticket workflow design, Suggestions and the job queue](../design/backend-ticket-workflow.md#suggestions-and-the-job-queue)).
- **PostgreSQL LISTEN/NOTIFY.** It delivers a notification only after the sending transaction commits ([PostgreSQL 17, NOTIFY](https://www.postgresql.org/docs/17/sql-notify.html)). Through Supabase:
  - LISTEN is lost in transaction mode, and works in session mode and on a direct connection;
  - a direct connection needs IPv6, or an IPv4 add-on on the Pro plan and above ([Supabase, Connect to your database](https://supabase.com/docs/guides/database/connecting-to-postgres));
  - a session-mode client keeps its connection "until voluntarily surrendered" ([Supavisor FAQ](https://supabase.com/docs/guides/troubleshooting/supavisor-faq-YyP5tI)).
- **The connection pool is already full.** The default pool size on the free compute is 15, and it applies "per database user (role)" ([Compute and disk](https://supabase.com/docs/guides/platform/compute-and-disk), [Connection management](https://supabase.com/docs/guides/database/connection-management)). The pool of `backend`, 5 connections plus 10 overflow, already fills those 15 ([ADR-0016, PostgreSQL on Supabase](0016-hosting-on-free-tiers.md#postgresql-on-supabase), item 3).
- **Supabase Realtime.** It authorizes with RLS policies and a Supabase Auth JWT ([Realtime authorization](https://supabase.com/docs/guides/realtime/authorization)). The cookie sessions of [ADR-0009](0009-demo-accounts-and-cookie-sessions.md) provide no such JWT.

### The ingress and the hosting

- **The ingress Function.** The ingress is a Pages Function in `frontend/` ([ADR-0016](0016-hosting-on-free-tiers.md#frontend-and-the-ingress-on-cloudflare-pages), statement 2). It does not exist on any branch yet. It answers `504` when `backend` does not answer within 10 000 ms (statement 4).
- **Cloudflare Workers, free plan:**
  - A Worker can return the body of a `fetch()` without buffering it ([Workers, Streams](https://developers.cloudflare.com/workers/runtime-apis/streams/)).
  - A Worker has 10 ms of CPU time per request, and "Waiting on network requests … does not count toward CPU time" ([Workers limits](https://developers.cloudflare.com/workers/platform/limits/)).
  - There is "No hard limit while the client remains connected". However, a runtime update gives open streams "up to 20 minutes to finish" and then ends them (same page).
  - Every request counts toward the 100 000 requests per day of the free plan (same page; [Pages Functions pricing](https://developers.cloudflare.com/pages/functions/pricing/)).
  - A client disconnect cancels the upstream `fetch()` only when the Function passes `request.signal` to it. Before the compatibility date 2026-11-17, this also needs the flag `enable_request_signal` ([Request](https://developers.cloudflare.com/workers/runtime-apis/request/), [Compatibility flags](https://developers.cloudflare.com/workers/configuration/compatibility-flags/)).
- **Cloudflare, not documented:**
  - The Proxy Read Timeout of Cloudflare is 125 s ([Error 524](https://developers.cloudflare.com/support/troubleshooting/http-status-codes/cloudflare-5xx-errors/error-524/)). Whether it applies after the response headers, or to a Worker subrequest, is not documented.
  - Whether Workers compress or buffer `text/event-stream` is not documented ([Fetch](https://developers.cloudflare.com/workers/runtime-apis/fetch/), [Content compression](https://developers.cloudflare.com/speed/optimization/content/compression/)).
- **Render, free web service:**
  - Responses may take up to 100 minutes ([Render vs Vercel](https://render.com/docs/render-vs-vercel-comparison)).
  - The instance has 0.1 CPU and 512 MB ([Compute plans](https://render.com/docs/compute-plans)).
  - It spins down after 15 minutes without inbound traffic ([Free instances](https://render.com/docs/free)), which the keep-alive of ADR-0016 prevents.
  - It gets 30 s after `SIGTERM` to shut down ([WebSockets](https://render.com/docs/websocket)).
- **uvicorn:** it sets no concurrency limit. On shutdown, it waits for open responses unless `--timeout-graceful-shutdown` is set ([Server behavior](https://uvicorn.dev/server-behavior/), [Settings](https://uvicorn.dev/settings/)).

### Browsers and the stack

- **`EventSource` behavior:**
  - A same-origin `EventSource` sends cookies ([HTML, Server-sent events](https://html.spec.whatwg.org/multipage/server-sent-events.html); [create a potential-CORS request](https://html.spec.whatwg.org/multipage/urls-and-fetching.html#create-a-potential-cors-request)).
  - It reconnects after a network error and after the server closes the stream, and it follows `retry:`.
  - It stops reconnecting on `204 No Content`.
  - Any other non-`200` status, or a content type other than `text/event-stream`, ends it for good (same page).
- **No `Origin` header on a same-origin GET** ([Fetch, append a request `Origin` header](https://fetch.spec.whatwg.org/#append-a-request-origin-header)). `backend` checks `Origin` only on state-changing operations, and its reads rely on the `SameSite=Strict` session cookie ([ADR-0009](0009-demo-accounts-and-cookie-sessions.md)).
- **Connections per origin.** Over HTTP/1.1 a browser keeps at most 6 connections per origin, while HTTP/2 negotiates about 100 streams ([MDN, Using server-sent events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events)). Cloudflare enables HTTP/2 on every plan ([HTTP/2](https://developers.cloudflare.com/speed/optimization/protocol/http2/)).
- **FastAPI.** FastAPI 0.135.0 and later have `EventSourceResponse`, which sends a ping comment every 15 s, `Cache-Control: no-cache`, and `X-Accel-Buffering: no` ([FastAPI, Server-Sent Events](https://fastapi.tiangolo.com/tutorial/server-sent-events/)). `backend` pins FastAPI 0.162.0, so SSE needs no new dependency. Starlette lets an endpoint detect a disconnect ([Starlette, Requests](https://starlette.dev/requests/)). In Starlette 1.10.0 under uvicorn 0.54.0, the versions that `backend` pins, `StreamingResponse` stops on `http.disconnect`, as their installed source shows.
- **Prism and OpenAPI.** Prism documents no mock of `text/event-stream` ([Prism mocking guide](https://github.com/stoplightio/prism/blob/main/docs/guides/01-mocking.md)). The contracts are OpenAPI 3.1.0, and `itemSchema` for event streams belongs to OpenAPI 3.2 ([OpenAPI media type registry, SSE](https://spec.openapis.org/registry/media-type/sse)).

## Decision drivers

1. **Safety and privacy.** No Confidential value leaves `backend` outside the restore and the role checks of `getConsoleTicket`, and the stream keeps the sessions of ADR-0009 (SEC-01, LOG-29).
2. **Fit with the accepted runtime rules.** Replicas stay stateless, more than one replica keeps working, and the connections stay within the Supabase pool ([ADR-0011](0011-deployment-and-runtime-topology.md), [ADR-0016](0016-hosting-on-free-tiers.md)).
3. **Reliability on the free hosting.** A stream that cannot start, drops, or ends leaves the console working.
4. **Latency.** Staff see a draft soon after it is stored, and NFR-11 compares the two modes fairly.
5. **Low complexity and cost.** No new dependency, no new infrastructure, and use within the free limits.

## Considered options

1. Poll `getConsoleTicket` every 30 s while a part is `pending`, without push.
2. An SSE stream of signals, fed by an in-process wake-up after the commit and a periodic re-read: the pattern of the claim loop.
3. An SSE stream of signals, fed by PostgreSQL LISTEN/NOTIFY.
4. Long polling.
5. WebSockets.

## Decision

We will use option 2, an SSE stream of signals fed like the claim loop. On 2026-11-14 the project lead chose this option and made three decisions:

- the change of ADR-0016, statement 4, for the stream route;
- a re-read every 1 000 ms in v1, with a better way as a follow-up;
- a stream that is open only while a part is `pending`.

1. `backend` serves `GET /v1/console/tickets/{ticket_id}/suggestion-events` as `text/event-stream`.
   - **Roles and session.** The roles are `staff` and `manager`, with the session cookie of ADR-0009.
   - **Checks and errors.** The checks run in the order of `getConsoleTicket`: session (`401`), role (`403`), and ticket (`404`). Each refusal is a Problem Details body sent before the stream starts.
   - **No `Origin` check.** Like every read of the contract, it has none, because a same-origin `EventSource` sends no `Origin` header. `SameSite=Strict` keeps other sites from sending the cookie.
   - **Tickets that stop the stream.** Some tickets get `204 No Content`, which tells `EventSource` to stop reconnecting: a ticket that is not `open`, a ticket in `manual` mode, and a ticket whose current suggestion has no `pending` part.
2. **Events are signals of Internal values only.** Each event is `event: suggestion`, with `suggestion_id`, `analysis_status`, and `draft_status` of the current suggestion. After each event, the console reloads the workspace with `getConsoleTicket`, which restores the pseudonyms and checks the role. No message text, AI text, order data, or display name is ever written to a stream.
3. **Each connection starts with the current state.** It then sends an event whenever the current suggestion or the status of one of its parts changes. A reconnect therefore loses nothing, and `backend` ignores `Last-Event-ID`. The stream sends `retry: 3000`, and a ping comment when nothing was sent for 15 s.
4. **How `backend` notices a change.** It uses two signals, as the claim loop does:
   - **The in-process wake-up.** A use case wakes the streams of the ticket on its own replica after it commits one of three things: a part result, a new suggestion, or a cancelled part.
   - **The re-read.** Each stream also re-reads the part statuses every `suggestion_events_poll_ms`, 1 000 in v1, in one short read transaction. This covers a job that another replica finished. The project lead accepted this periodic read for v1 and asked for a way without it later ([Follow-ups](#follow-ups)).

   No connection is held between two reads, so the pool of ADR-0016 does not change.
5. **When a stream ends.**
   - Once no part of the current suggestion is `pending`, right after the event that shows it.
   - When the ticket leaves `open`.
   - After at most `suggestion_events_max_ms`, initially 600 000, as a bound for a job that stays `pending` through its lease and its attempts. The browser reconnects by itself.
   - At shutdown: the lifespan ends every stream before uvicorn's graceful shutdown, within Render's 30 s.
6. **When the console opens a stream.** It opens one stream for the workspace of an `open` ticket in `assisted` mode while a part of the current suggestion is `pending`. That happens when the workspace opens with a `pending` part, and when a staff action starts a suggestion. The console closes the stream when an event shows no `pending` part, and when staff leave the ticket. A reconnect after the last event gets `204`, so it stops by itself. When the first connection already gets `204`, because the part finished before the stream opened, the console reloads the workspace once with `getConsoleTicket`.
7. **Fallback.** When the stream cannot start or ends with an error, the console polls `getConsoleTicket` every 30 s while a part is `pending`. It opens a new stream after the next successful read. The inbox polls every 30 s.
8. **The ingress Function** forwards the stream unchanged and passes `request.signal` to its `fetch()`. On this route, the 10 000 ms of [ADR-0016, statement 4](0016-hosting-on-free-tiers.md#frontend-and-the-ingress-on-cloudflare-pages) bounds only the wait for the response headers, not the whole response. This part belongs to `frontend/`. Once accepted, it changes ADR-0016, statement 4, for this one route.
9. **The contract.** `backend` contract 1.3.0 adds the operation through the [contract-first process](../rules/contracts.md#contract-first-process): a `text/event-stream` response with a string schema and an example. Prism does not mock streams. `frontend` therefore tests the stream with a fake `EventSource`, and the Prism mock exercises the fallback.

```mermaid
sequenceDiagram
    actor S as Staff
    participant FE as Console
    participant F as Pages Function
    participant BE as backend replica
    participant DB as PostgreSQL
    S->>FE: Open the workspace of an open, assisted ticket with a pending part, or start a suggestion
    FE->>F: GET .../suggestion-events (cookie)
    F->>BE: Forward; headers within 10 000 ms
    alt 401, 403, or 404
        BE-->>FE: Problem Details
        FE->>FE: Poll getConsoleTicket every 30 s while a part is pending
    else The ticket is not open, is in manual mode, or has no pending part
        BE-->>FE: 204 No Content; EventSource stops
        FE->>F: GET getConsoleTicket once
    else Stream starts
        BE->>DB: Read the current suggestion and its part statuses
        BE-->>FE: event: suggestion (current state)
        loop While a part is pending, until the maximum or shutdown
            alt A part result commits on this replica
                BE->>BE: Wake the streams of the ticket
            else suggestion_events_poll_ms passes
                BE->>DB: Re-read the part statuses
            end
            BE-->>FE: event: suggestion, only when something changed
            FE->>F: GET getConsoleTicket
        end
        alt No part is pending any more
            BE-->>FE: Last event, then the stream ends
            FE->>FE: Close the stream
        else The stream ends at its maximum or at shutdown
            FE->>F: Reconnect after retry
        else The stream fails: buffering, cut-off, or an error status
            FE->>FE: Poll every 30 s while a part is pending, then open a new stream after a successful read
        end
    end
```

## Consequences

### Positive

- Staff see a stored draft almost at once on the replica that stored it, and within `suggestion_events_poll_ms` on another replica, instead of up to 30 s later. The NFR-11 comparison then measures handling, not polling.
- The workspace sends fewer requests than the 2 s poll of the console UI design, so it uses less of the 100 000 daily Function requests.
- A stream holds only identifiers and statuses. The text still comes only from `getConsoleTicket`, with its restore and its role checks.
- No new dependency, no new infrastructure, and no held database connection. The rules of ADR-0011 for more than one replica still hold.

### Negative

- The console gets a new kind of request: a long-lived response through the Function and Render. Two of its limits are not documented: the 125 s timeout after the headers, and the buffering of `text/event-stream`. Both must be measured before staff depend on the stream, and the fallback carries the console until then.
- Each open stream reads the database once per `suggestion_events_poll_ms`, even when nothing changes, while a part is `pending`. Five workspaces that wait for a draft at the same time add about five reads per second.
- The decision changes three accepted or approved texts:
  - statement 4 of ADR-0016, for one route;
  - the non-goal "Streaming or push updates" of the contracts v1 design;
  - the polling of the console UI design.
- Prism cannot mock the stream. Schemathesis cannot read an endless stream, so this operation is left out of the generated requests and covered by the documented outcomes instead.
- A stream lives only while a part is `pending`, so each suggestion costs about one stream request and one reload per change. A runtime update of Cloudflare can still end a stream, and its reconnect is one more request.
- A suggestion that someone else starts on the same ticket is not pushed to a workspace whose own parts are not `pending`. Staff see it at their next reload or action.

### Follow-ups

- Revisions with dates of the [contracts v1 design](../design/contracts-v1.md#non-goals), the [console UI design](../design/console-ui.md#flow), and the [backend ticket workflow design](../design/backend-ticket-workflow.md#suggestions-and-the-job-queue), once this ADR is accepted.
- `backend` contract 1.3.0, through the contract-first process.
- The stream route of the Pages Function in `frontend/`, with its unit tests (ADR-0016, statement 7).
- The settings `suggestion_events_poll_ms` and `suggestion_events_max_ms` in the Settings table of the backend ticket workflow design.
- A way without periodic reads, which the project lead asked for after v1. Examples: LISTEN/NOTIFY, once the Supabase pool leaves room for one held connection per replica, or a signal that the claim loop already sends.

## Pros and cons of the options

### Poll every 30 s, without push

- Good, because it needs no new operation, no contract change, and no change of the ingress. Prism mocks it, and the inbox already works this way.
- Good, because a missed poll costs at most one more interval, and nothing stays open on the Function or on Render.
- Bad, because staff see a draft up to 30 s after it is stored. This wait repeats after every intent correction and every retry, and it counts toward the handling time of the assisted mode (NFR-11).
- Bad, because staff may reload the page to see a draft sooner. That sends more requests than the poll it replaces, and the handling time then measures waiting.

### An SSE stream fed like the claim loop

- Good, because it reuses the wake-up and re-read pattern of the claim loop (CODE-52), holds no database connection, and works with any number of replicas.
- Good, because FastAPI already provides it, and the browser reconnects by itself.
- Bad, because the Function and Render must carry a long-lived response, and two of their limits are not documented.
- Bad, because every open stream reads the database every `suggestion_events_poll_ms` while a part is `pending`, and it changes statement 4 of ADR-0016 for one route.

### An SSE stream fed by LISTEN/NOTIFY

- Good, because a notification arrives right after the commit, on every replica, with no re-read.
- Bad, because each replica holds one session-mode connection for LISTEN. Within the pool size of 15, which the pool of `backend` already fills, that needs a smaller pool and a change of ADR-0016, PostgreSQL on Supabase, item 3.
- Bad, because a dropped LISTEN connection loses notifications until it reconnects, so a re-read is still needed as a safety net.

### Long polling

- Good, because each request is an ordinary request, which Prism can mock.
- Bad, because each request must stay open longer than the 10 000 ms of ADR-0016, statement 4, which needs the same change of the ingress as SSE.
- Bad, because each wait is a new request through the Function, and the server side still needs the wake-up and the re-read.

### WebSockets

- Good, because Render documents WebSockets with no fixed duration ([WebSockets](https://render.com/docs/websocket)).
- Bad, because OpenAPI 3.1 cannot describe them, the Prism mock cannot serve them, and Cloudflare documents no WebSocket proxying for Pages Functions.
- Bad, because the console needs one direction only, and a two-way channel adds a protocol and its tests for nothing.

## Validation

- **Unit tests** of the stream with a fake clock that waits until cancelled, as the claim loop tests do (TEST-14):
  - the current state comes first;
  - an event follows a wake-up;
  - an event follows a re-read;
  - no event comes without a change;
  - the stream ends once no part is `pending`, at its maximum, and when the ticket leaves `open`;
  - a connection to a ticket without a `pending` part gets `204`.
- **Integration tests** against PostgreSQL: a part result that another session commits reaches an open stream through the re-read, and a client disconnect ends the stream.
- **Documented outcomes** of the operation: `200` with the first event, then `204`, `401`, `403`, and `404`.
- **A guardrail test:** the bytes of a stream hold no seeded value, message text, or AI text (LOG-29).
- **A measurement after the first deploy** through the Function:
  - the delay of the first event;
  - whether events arrive unbuffered;
  - whether a stream with 15 s pings outlives 125 s;
  - the reconnect after a stream ends.

  If the Function buffers or cuts the stream, the console keeps the fallback, and this ADR is revisited.
- **The NFR-08 load test** with five concurrent sessions, each with an open stream.
- **Revisit** in any of these cases:
  - the daily Function requests come near the free limit;
  - the re-reads show in the database latency;
  - more than one replica runs;
  - FastAPI or the Workers runtime changes how a stream is cancelled.
