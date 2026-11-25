import { describe, expect, it } from "vitest";

import { describeAiUnavailable } from "@/features/console-tickets/model/manual-handling";

describe("describeAiUnavailable", () => {
  it.each([
    [
      "ai_service_unavailable",
      "The AI service did not answer, so there is no analysis, draft, or source.",
    ],
    [
      "pseudonymization_failed",
      "Personal data in the message could not be hidden, so nothing was sent to the AI.",
    ],
    ["llm_unavailable", "The AI could not write a draft for this ticket."],
    ["unknown", "The AI could not write a draft for this ticket."],
  ] as const)("says why the AI did not help after %s", (reasonCode, text) => {
    expect(describeAiUnavailable(reasonCode)).toBe(text);
  });
});
