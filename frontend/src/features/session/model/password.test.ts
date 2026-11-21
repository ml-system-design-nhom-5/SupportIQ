import { describe, expect, it } from "vitest";

import {
  classifyPasswordLength,
  PASSWORD_MAX_LENGTH,
  PASSWORD_MIN_LENGTH,
} from "@/features/session/model/password";
import { readBackendSchema } from "@/test/contract-schemas";

/** An emoji: one code point, two UTF-16 units. */
const EMOJI = "😊";

describe("PASSWORD_MIN_LENGTH and PASSWORD_MAX_LENGTH", () => {
  it("are the limits of Password in the contract", () => {
    const schema = readBackendSchema("Password");

    expect(schema).toContain(`minLength: ${String(PASSWORD_MIN_LENGTH)}\n`);
    expect(schema).toContain(`maxLength: ${String(PASSWORD_MAX_LENGTH)}\n`);
  });
});

describe("classifyPasswordLength", () => {
  it.each([
    ["an empty password", "", "empty"],
    ["one character", "a", "valid"],
    ["128 emoji, which are 256 UTF-16 units", EMOJI.repeat(PASSWORD_MAX_LENGTH), "valid"],
    ["129 characters", "a".repeat(PASSWORD_MAX_LENGTH + 1), "too_long"],
    ["129 emoji", EMOJI.repeat(PASSWORD_MAX_LENGTH + 1), "too_long"],
    ["spaces only, never trimmed", "   ", "valid"],
  ])("counts %s in code points: %s", (_case, password, length) => {
    expect(classifyPasswordLength(password)).toBe(length);
  });
});
