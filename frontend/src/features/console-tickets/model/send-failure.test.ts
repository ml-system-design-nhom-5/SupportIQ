import { describe, expect, it } from "vitest";

import type { RequestFailure } from "@/features/backend-requests";
import { describeSendFailure } from "@/features/console-tickets/model/send-failure";

/** The trace ID of the failures of these tests. */
const TRACE_ID = "e929d0e0e4736bf92f3577b34da6a3c2";

describe("describeSendFailure of a refusal that means the ticket changed", () => {
  it.each<[RequestFailure, string]>([
    [
      { kind: "problem", status: 409, problemType: "suggestion_pending", traceId: TRACE_ID },
      "The AI is still working on this ticket. Your text is kept.",
    ],
    [
      { kind: "problem", status: 409, problemType: "suggestion_superseded", traceId: TRACE_ID },
      "The AI made a new draft for this ticket. Check it; your text is kept.",
    ],
    [
      { kind: "problem", status: 409, problemType: "invalid_ticket_state", traceId: TRACE_ID },
      "This ticket was already handled. It now shows its current state.",
    ],
    [
      { kind: "problem", status: 403, problemType: "forbidden", traceId: TRACE_ID },
      "A colleague escalated this ticket or submitted it for approval. Your text is kept.",
    ],
    [
      { kind: "problem", status: 403, problemType: "authority_required", traceId: TRACE_ID },
      "Only a manager can send the reply of this ticket. Submit it for approval instead.",
    ],
  ])("reloads the workspace after %j", (failure, message) => {
    expect(describeSendFailure(failure)).toEqual({
      lead: "The reply was not sent.",
      message,
      shouldReload: true,
      traceId: TRACE_ID,
    });
  });
});

describe("describeSendFailure of other failures", () => {
  it("keeps the editor after a 422, with the message of its category", () => {
    expect(
      describeSendFailure({
        kind: "problem",
        status: 422,
        problemType: "invalid_request",
        traceId: TRACE_ID,
      }),
    ).toEqual({
      lead: "The reply was not sent.",
      message: "The request was not accepted. Check what you entered and try again.",
      shouldReload: false,
      traceId: TRACE_ID,
    });
  });

  it.each<RequestFailure>([
    { kind: "network" },
    { kind: "timeout" },
    { kind: "ingress", status: 504 },
  ])("says that the reply may have been sent after %j", (failure) => {
    expect(describeSendFailure(failure)).toEqual({
      lead: "The reply may have been sent.",
      message:
        "We could not confirm it. Sending the same reply again is safe: the customer gets it once.",
      shouldReload: false,
    });
  });

  it("says that the reply was not sent after a 500", () => {
    expect(
      describeSendFailure({ kind: "problem", status: 500, problemType: "internal_error" }),
    ).toMatchObject({ lead: "The reply was not sent.", shouldReload: false });
  });
});
