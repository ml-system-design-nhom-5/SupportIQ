import { describe, expect, it } from "vitest";

import { toTicketActions } from "@/features/console-tickets/model/ticket-actions";

describe("toTicketActions", () => {
  it("keeps every action of the contract", () => {
    expect(
      toTicketActions([
        "send_reply",
        "submit_reply_proposal",
        "escalate",
        "correct_intent",
        "retry_suggestion",
      ]),
    ).toEqual(
      new Set([
        "send_reply",
        "submit_reply_proposal",
        "escalate",
        "correct_intent",
        "retry_suggestion",
      ]),
    );
  });

  it("ignores an action that this version does not know (CON-22)", () => {
    expect(toTicketActions(["escalate", "a_later_action"])).toEqual(new Set(["escalate"]));
  });
});
