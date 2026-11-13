import { describe, expect, it } from "vitest";

import type { RequestFailure } from "@/features/backend-requests";
import { describeSuggestionFailure } from "@/features/console-tickets/model/suggestion-failure";

/** A trace ID in the format of the contract. */
const TRACE_ID = "e929d0e0e4736bf92f3577b34da6a3c2";

/** What a refusal of an old screen says. */
const OLD_SCREEN_MESSAGE = "This ticket changed in the meantime. It now shows its current state.";

/** The shared message of a lost connection. */
const NETWORK_MESSAGE = "The server could not be reached. Check your connection and try again.";

/** The shared message of a service that is not available. */
const UNAVAILABLE_MESSAGE = "The service is not available right now. Try again in a moment.";

/** The refusals of `createSuggestion` that `backend` sends, with what they say. */
const refusals: readonly [string, RequestFailure, string][] = [
  [
    "409 suggestion-pending",
    { kind: "problem", status: 409, problemType: "suggestion_pending", traceId: TRACE_ID },
    "The AI is still working on this ticket. Wait until it is done, then try again.",
  ],
  [
    "422 invalid-request",
    { kind: "problem", status: 422, problemType: "invalid_request", traceId: TRACE_ID },
    OLD_SCREEN_MESSAGE,
  ],
  [
    "409 invalid-ticket-state",
    { kind: "problem", status: 409, problemType: "invalid_ticket_state", traceId: TRACE_ID },
    OLD_SCREEN_MESSAGE,
  ],
];

describe("describeSuggestionFailure for a correction", () => {
  it.each(refusals)(
    "says that the intent was not changed after %s, with the trace ID",
    (_case, failure, message) => {
      expect(describeSuggestionFailure(failure, "correction")).toEqual({
        lead: "The intent was not changed.",
        message,
        traceId: TRACE_ID,
      });
    },
  );

  it("never says that the intent did not change after an unknown outcome (ERR-07)", () => {
    expect(describeSuggestionFailure({ kind: "network" }, "correction")).toEqual({
      lead: "The intent may have been changed.",
      message: NETWORK_MESSAGE,
    });
  });
});

describe("describeSuggestionFailure for Try AI again", () => {
  it.each(refusals)(
    "says that the AI did not start again after %s, with the trace ID",
    (_case, failure, message) => {
      expect(describeSuggestionFailure(failure, "retry")).toEqual({
        lead: "The AI did not start again.",
        message,
        traceId: TRACE_ID,
      });
    },
  );

  it("uses the shared message of a failure that is not a refusal of an old screen", () => {
    const failure: RequestFailure = { kind: "problem", status: 503, problemType: "not_ready" };

    expect(describeSuggestionFailure(failure, "retry")).toEqual({
      lead: "The AI did not start again.",
      message: UNAVAILABLE_MESSAGE,
    });
  });
});

describe("describeSuggestionFailure for Try AI again after an unknown outcome", () => {
  it.each<[string, RequestFailure, string]>([
    ["a lost connection", { kind: "network" }, NETWORK_MESSAGE],
    [
      "a timeout",
      { kind: "timeout" },
      "The server took too long to answer. Try again in a moment.",
    ],
    [
      "a 503 after a lost connection with the same key",
      { kind: "ingress", status: 503, isAfterUnknownOutcome: true },
      UNAVAILABLE_MESSAGE,
    ],
  ])("never says that the AI did not start again after %s (ERR-16)", (_case, failure, message) => {
    expect(describeSuggestionFailure(failure, "retry")).toEqual({
      lead: "The AI may have started again.",
      message,
    });
  });
});
