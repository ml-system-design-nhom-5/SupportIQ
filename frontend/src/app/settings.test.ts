import { describe, expect, it } from "vitest";

import { InvalidSettingError, parseFrontendSettings } from "@/app/settings";

/** A Grafana trace link of the local stack. */
const TRACE_URL = "http://localhost:3000/explore?trace={trace_id}";

describe("parseFrontendSettings", () => {
  it("uses the defaults of the contract and ERR-13 when no variable is set", () => {
    const settings = parseFrontendSettings({});

    expect(settings).toEqual({
      requestTimeoutMs: 10_000,
      requestRetryMaxCount: 2,
      requestRetryBaseDelayMs: 500,
      isDevModeAvailable: false,
    });
  });

  it("reads every variable that is set", () => {
    const settings = parseFrontendSettings({
      VITE_REQUEST_TIMEOUT_MS: "2500",
      VITE_REQUEST_RETRY_MAX_COUNT: "0",
      VITE_REQUEST_RETRY_BASE_DELAY_MS: "100",
      VITE_DEV_MODE: "on",
      VITE_GRAFANA_TRACE_URL: TRACE_URL,
    });

    expect(settings).toEqual({
      requestTimeoutMs: 2500,
      requestRetryMaxCount: 0,
      requestRetryBaseDelayMs: 100,
      isDevModeAvailable: true,
      grafanaTraceUrl: TRACE_URL,
    });
  });

  it("treats an empty variable as not set", () => {
    const settings = parseFrontendSettings({
      VITE_REQUEST_TIMEOUT_MS: "",
      VITE_DEV_MODE: "",
      VITE_GRAFANA_TRACE_URL: "",
    });

    expect(settings).toMatchObject({ requestTimeoutMs: 10_000, isDevModeAvailable: false });
    expect(settings).not.toHaveProperty("grafanaTraceUrl");
  });
});

describe("parseFrontendSettings, dev mode (UI-35)", () => {
  it.each([
    ["the dev server", { DEV: true }, true],
    ["a production build", { DEV: false }, false],
    ["the dev server with dev mode off", { DEV: true, VITE_DEV_MODE: "off" }, false],
    ["a production build with dev mode on", { DEV: false, VITE_DEV_MODE: "on" }, true],
  ])("follows %s", (_case, environment, isDevModeAvailable) => {
    expect(parseFrontendSettings(environment).isDevModeAvailable).toBe(isDevModeAvailable);
  });
});

describe("parseFrontendSettings, the Grafana trace link (UI-35, SEC-28)", () => {
  it.each([
    "https://grafana.example/explore?trace={trace_id}",
    "https://localhost.example.com/explore?trace={trace_id}",
    "http://localhost:3000/explore?trace={trace_id}",
    "http://127.0.0.1:3000/explore?trace={trace_id}",
    "http://[::1]:3000/explore?trace={trace_id}",
  ])("accepts %s: https on any host, or http on the developer's machine", (url) => {
    expect(parseFrontendSettings({ VITE_GRAFANA_TRACE_URL: url }).grafanaTraceUrl).toBe(url);
  });

  it.each([
    "http://localhost.example.com/explore?trace={trace_id}",
    "http://127.0.0.1.nip.io/explore?trace={trace_id}",
    "http://user@localhost.example.com/explore?trace={trace_id}",
    "http://example.com/explore?trace={trace_id}",
    "/explore?trace={trace_id}",
    "https://grafana.example/explore",
    "https://grafana.example/{trace_id}/{trace_id}",
  ])("stops startup for %s", (url) => {
    expect(() => parseFrontendSettings({ VITE_GRAFANA_TRACE_URL: url })).toThrow(
      "VITE_GRAFANA_TRACE_URL",
    );
  });
});

describe("parseFrontendSettings, invalid values", () => {
  it.each([
    ["VITE_REQUEST_TIMEOUT_MS", "0"],
    ["VITE_REQUEST_TIMEOUT_MS", "ten seconds"],
    ["VITE_REQUEST_TIMEOUT_MS", "1.5"],
    ["VITE_REQUEST_RETRY_MAX_COUNT", "-1"],
    ["VITE_REQUEST_RETRY_BASE_DELAY_MS", "0"],
    ["VITE_DEV_MODE", "true"],
    ["VITE_DEV_MODE", "ON"],
    ["VITE_DEV_MODE", "constructor"],
    ["VITE_DEV_MODE", "toString"],
    ["VITE_DEV_MODE", "__proto__"],
    ["VITE_GRAFANA_TRACE_URL", "http://localhost:3000/explore"],
    ["VITE_GRAFANA_TRACE_URL", "localhost:3000/{trace_id}"],
    ["VITE_GRAFANA_TRACE_URL", "javascript:alert('{trace_id}')"],
  ])("stops startup with a message naming %s when it is %s", (name, value) => {
    const parse = () => parseFrontendSettings({ [name]: value });

    expect(parse).toThrow(InvalidSettingError);
    expect(parse).toThrow(name);
  });

  it.each(["VITE_REQUEST_TIMEOUT_MS", "VITE_DEV_MODE", "VITE_GRAFANA_TRACE_URL"])(
    "rejects a boolean value of %s, which Vite gives for some variables",
    (name) => {
      const parse = () => parseFrontendSettings({ [name]: true });

      expect(parse).toThrow(name);
    },
  );
});
