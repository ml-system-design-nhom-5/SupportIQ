import { describe, expect, it } from "vitest";

import {
  countMessageCharacters,
  MESSAGE_MAX_LENGTH,
} from "@/features/shop-support/model/message-text";
import { readContractSchema } from "@/test/contract-schemas";

describe("MESSAGE_MAX_LENGTH", () => {
  it("is the maxLength of MessageText in the contract", () => {
    expect(readContractSchema("MessageText")).toContain(
      `maxLength: ${String(MESSAGE_MAX_LENGTH)}\n`,
    );
  });
});

describe("countMessageCharacters", () => {
  it.each([
    ["", 0],
    ["Hello", 5],
    ["Tiền", 4],
    ["😊", 1],
  ])("counts %j as %i", (text, count) => {
    expect(countMessageCharacters(text)).toBe(count);
  });
});
