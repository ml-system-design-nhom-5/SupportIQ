import { describe, expect, it } from "vitest";

import { InvalidSettingError, parseFrontendSettings } from "@/app/settings";

describe("parseFrontendSettings", () => {
  it("uses the defaults of the contract and ERR-13 when no variable is set", () => {
    const settings = parseFrontendSettings({});

    expect(settings).toEqual({
      requestTimeoutMs: 10_000,
      requestRetryMaxCount: 2,
      requestRetryBaseDelayMs: 500,
    });
  });

  it("reads every variable that is set", () => {
    const settings = parseFrontendSettings({
      VITE_REQUEST_TIMEOUT_MS: "2500",
      VITE_REQUEST_RETRY_MAX_COUNT: "0",
      VITE_REQUEST_RETRY_BASE_DELAY_MS: "100",
    });

    expect(settings).toEqual({
      requestTimeoutMs: 2500,
      requestRetryMaxCount: 0,
      requestRetryBaseDelayMs: 100,
    });
  });

  it("treats an empty variable as not set", () => {
    const settings = parseFrontendSettings({ VITE_REQUEST_TIMEOUT_MS: "" });

    expect(settings.requestTimeoutMs).toBe(10_000);
  });
});

describe("parseFrontendSettings, invalid values", () => {
  it.each([
    ["VITE_REQUEST_TIMEOUT_MS", "0"],
    ["VITE_REQUEST_TIMEOUT_MS", "ten seconds"],
    ["VITE_REQUEST_TIMEOUT_MS", "1.5"],
    ["VITE_REQUEST_RETRY_MAX_COUNT", "-1"],
    ["VITE_REQUEST_RETRY_BASE_DELAY_MS", "0"],
  ])("stops startup with a message naming %s when it is %s", (name, value) => {
    const parse = () => parseFrontendSettings({ [name]: value });

    expect(parse).toThrow(InvalidSettingError);
    expect(parse).toThrow(name);
  });

  it("rejects a boolean value, which Vite gives for some variables", () => {
    const parse = () => parseFrontendSettings({ VITE_REQUEST_TIMEOUT_MS: true });

    expect(parse).toThrow("VITE_REQUEST_TIMEOUT_MS");
  });
});
