import { describe, expect, it } from "vitest";

import {
  hasPlaceholder,
  PLACEHOLDER_PATTERN,
  splitPlaceholders,
} from "@/features/console-tickets/model/placeholders";
import { readContractSchema, readPattern } from "@/test/contract-schemas";

describe("PLACEHOLDER_PATTERN", () => {
  it("is the pattern of the Placeholder schema of the contract", () => {
    expect(PLACEHOLDER_PATTERN).toBe(readPattern(readContractSchema("Placeholder")));
  });
});

describe("splitPlaceholders", () => {
  it("marks a mask, a pseudonym, and a LITERAL, and keeps the text between them", () => {
    expect(splitPlaceholders("Sent to [EMAIL] for [ORDER_ID_1]. You wrote [LITERAL_2]")).toEqual([
      { text: "Sent to ", isMarked: false },
      { text: "[EMAIL]", isMarked: true },
      { text: " for ", isMarked: false },
      { text: "[ORDER_ID_1]", isMarked: true },
      { text: ". You wrote ", isMarked: false },
      { text: "[LITERAL_2]", isMarked: true },
    ]);
  });

  it("marks placeholders next to each other one by one", () => {
    expect(splitPlaceholders("[NAME][PHONE_12]")).toEqual([
      { text: "[NAME]", isMarked: true },
      { text: "[PHONE_12]", isMarked: true },
    ]);
  });

  it.each([
    ["an unknown type", "Call [MOBILE] now"],
    ["a number from 0", "See [ORDER_ID_0]"],
    ["a number above 999", "See [ORDER_ID_1000]"],
    ["lowercase", "Write to [email]"],
  ])("leaves %s unmarked", (_case, text) => {
    expect(splitPlaceholders(text)).toEqual([{ text, isMarked: false }]);
  });

  it("has no part for empty text", () => {
    expect(splitPlaceholders("")).toEqual([]);
  });
});

describe("hasPlaceholder", () => {
  it.each([
    ["Your order [ORDER_ID_1] is on its way.", true],
    ["Thank you for your patience.", false],
    ["", false],
  ])("answers for %j: %s", (text, isFound) => {
    expect(hasPlaceholder(text)).toBe(isFound);
  });
});
