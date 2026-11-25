import { describe, expect, it } from "vitest";

import { type RequestFailure, RequestFailureError } from "@/features/backend-requests";
import {
  describeReplyFailure,
  isTakenByColleague,
  pickLatestFailure,
} from "@/features/console-tickets/model/reply-failure";

/** The trace ID of the failures of these tests. */
const TRACE_ID = "e929d0e0e4736bf92f3577b34da6a3c2";

describe("describeReplyFailure of Send reply, a refusal that means the ticket changed", () => {
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
    expect(describeReplyFailure(failure, "send_reply")).toEqual({
      lead: "The reply was not sent.",
      message,
      shouldReload: true,
      traceId: TRACE_ID,
    });
  });
});

describe("describeReplyFailure of Send reply, other failures", () => {
  it("keeps the editor after a 422, with the message of its category", () => {
    expect(
      describeReplyFailure(
        {
          kind: "problem",
          status: 422,
          problemType: "invalid_request",
          traceId: TRACE_ID,
        },
        "send_reply",
      ),
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
    expect(describeReplyFailure(failure, "send_reply")).toEqual({
      lead: "The reply may have been sent.",
      message:
        "We could not confirm it. Sending the same reply again is safe: the customer gets it once.",
      shouldReload: false,
    });
  });

  it("says that the reply was not sent after a 500", () => {
    expect(
      describeReplyFailure(
        { kind: "problem", status: 500, problemType: "internal_error" },
        "send_reply",
      ),
    ).toMatchObject({ lead: "The reply was not sent.", shouldReload: false });
  });
});

describe("describeReplyFailure of Submit for approval and Escalate ticket", () => {
  it.each([
    ["submit_reply_proposal", "The reply was not submitted."],
    ["escalate", "The ticket was not escalated."],
  ] as const)("says that %s did not happen after a refusal, and reloads", (action, lead) => {
    expect(
      describeReplyFailure(
        { kind: "problem", status: 409, problemType: "invalid_ticket_state", traceId: TRACE_ID },
        action,
      ),
    ).toEqual({
      lead,
      message: "This ticket was already handled. It now shows its current state.",
      shouldReload: true,
      traceId: TRACE_ID,
    });
  });

  it.each([
    [
      "submit_reply_proposal",
      "The reply may have been submitted.",
      "We could not confirm it. Submitting the same reply again is safe: a manager gets it once.",
    ],
    [
      "escalate",
      "The ticket may have been escalated.",
      "We could not confirm it. Escalating again with the same reasons is safe: it is escalated once.",
    ],
  ] as const)(
    "never says that %s did not happen after an unknown outcome (ERR-16)",
    (action, lead, message) => {
      expect(describeReplyFailure({ kind: "network" }, action)).toEqual({
        lead,
        message,
        shouldReload: false,
      });
    },
  );
});

describe("describeReplyFailure of a 403 (contract, ForbiddenRoleOrOrigin)", () => {
  const forbidden: RequestFailure = {
    kind: "problem",
    status: 403,
    problemType: "forbidden",
    traceId: TRACE_ID,
  };

  it("says that a colleague handled the ticket after Send reply, and reloads", () => {
    expect(describeReplyFailure(forbidden, "send_reply")).toMatchObject({
      message: "A colleague escalated this ticket or submitted it for approval. Your text is kept.",
      shouldReload: true,
    });
  });

  it.each(["submit_reply_proposal", "escalate"] as const)(
    "gives the shared message after %s, whose 403 only means a refused origin, without a reload",
    (write) => {
      expect(describeReplyFailure(forbidden, write)).toMatchObject({
        message: "Your account is not allowed to do this.",
        shouldReload: false,
      });
    },
  );
});

describe("isTakenByColleague (console UI design, Flow, step 6)", () => {
  it.each<[RequestFailure, boolean]>([
    [{ kind: "problem", status: 403, problemType: "forbidden" }, true],
    [{ kind: "problem", status: 403, problemType: "authority_required" }, false],
    [{ kind: "problem", status: 422, problemType: "invalid_request" }, false],
    [{ kind: "network" }, false],
  ])("tells whether %j means that a colleague took the ticket", (failure, isTaken) => {
    expect(isTakenByColleague(new RequestFailureError(failure))).toBe(isTaken);
  });

  it("is false for an error that is not a request failure", () => {
    expect(isTakenByColleague(new Error("A defect"))).toBe(false);
  });
});

describe("pickLatestFailure", () => {
  it("shows the failure of the latest request, or none", () => {
    const view = { lead: "Old.", message: "", shouldReload: false };
    const latest = { lead: "New.", message: "", shouldReload: false };

    expect(
      pickLatestFailure([{ view, submittedAt: 1 }, undefined, { view: latest, submittedAt: 2 }]),
    ).toBe(latest);
    expect(pickLatestFailure([undefined, undefined])).toBeUndefined();
  });
});
