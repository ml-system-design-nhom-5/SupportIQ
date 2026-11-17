import { describe, expect, it } from "vitest";

import { toTicketActions } from "@/features/console-tickets/model/ticket-actions";
import { readBackendSchema, readEnumValues } from "@/test/contract-schemas";

describe("toTicketActions", () => {
  it("keeps every action of TicketAction in the contract", () => {
    const contractActions = readEnumValues(readBackendSchema("TicketAction"));

    expect(toTicketActions(contractActions)).toEqual(new Set(contractActions));
  });

  it("ignores an action that this version does not know (CON-22)", () => {
    expect(toTicketActions(["escalate", "a_later_action"])).toEqual(new Set(["escalate"]));
  });
});
