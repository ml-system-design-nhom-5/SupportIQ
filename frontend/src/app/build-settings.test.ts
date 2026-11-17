import { describe, expect, it } from "vitest";

import { InvalidSettingError, parseBackendWakeOrigin } from "@/app/build-settings";

describe("parseBackendWakeOrigin (backend wake-up design, rules 9 and 10)", () => {
  it.each([undefined, ""])("reads %j as not set, so no wake request is sent", (raw) => {
    expect(parseBackendWakeOrigin(raw)).toBeUndefined();
  });

  it.each(["https://backend.example.com", "http://127.0.0.1:4010"])(
    "accepts the origin %s",
    (raw) => {
      expect(parseBackendWakeOrigin(raw)).toBe(raw);
    },
  );

  it.each([
    ["without a scheme", "backend.example.com"],
    ["of another scheme", "ftp://backend.example.com"],
    ["with a path", "https://backend.example.com/health"],
    ["with a trailing slash", "https://backend.example.com/"],
    ["with a query", "https://backend.example.com?x=1"],
    ["of another type", true],
  ])("stops at a value %s, naming the setting", (_case, raw) => {
    expect(() => parseBackendWakeOrigin(raw)).toThrow(InvalidSettingError);
    expect(() => parseBackendWakeOrigin(raw)).toThrow(
      "VITE_BACKEND_WAKE_ORIGIN must be an http or https origin without a path",
    );
  });
});
