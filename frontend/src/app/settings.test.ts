import { describe, expect, it } from "vitest";

import { InvalidSettingError } from "@/app/build-settings";
import { parseFrontendSettings } from "@/app/settings";

/** A Grafana trace link of the local stack. */
const TRACE_URL = "http://localhost:3000/explore?trace={trace_id}";

/** A Grafana dashboard link of the local stack. */
const DASHBOARD_URL = "http://localhost:3000/d/system-overview";

describe("parseFrontendSettings", () => {
  it("uses the defaults of the contract and ERR-13 when no variable is set", () => {
    const settings = parseFrontendSettings({});

    expect(settings).toMatchObject({
      requestTimeoutMs: 10_000,
      requestRetryMaxCount: 2,
      requestRetryBaseDelayMs: 500,
      isDevModeAvailable: false,
      backendWakeTimeoutMs: 90_000,
    });
  });

  it("reads every variable that is set", () => {
    const settings = parseFrontendSettings({
      VITE_REQUEST_TIMEOUT_MS: "2500",
      VITE_REQUEST_RETRY_MAX_COUNT: "0",
      VITE_REQUEST_RETRY_BASE_DELAY_MS: "100",
      VITE_DEV_MODE: "on",
      VITE_GRAFANA_TRACE_URL: TRACE_URL,
      VITE_BACKEND_WAKE_ORIGIN: "https://backend.example.com",
      VITE_BACKEND_WAKE_TIMEOUT_MS: "60000",
      VITE_FRONTEND_BUILD_VERSION: "cc489d3",
      VITE_GRAFANA_SYSTEM_OVERVIEW_URL: DASHBOARD_URL,
      VITE_GRAFANA_AI_PIPELINE_URL: "https://grafana.example/d/ai-pipeline",
    });

    expect(settings).toMatchObject({
      requestTimeoutMs: 2500,
      requestRetryMaxCount: 0,
      requestRetryBaseDelayMs: 100,
      isDevModeAvailable: true,
      grafanaTraceUrl: TRACE_URL,
      backendWakeOrigin: "https://backend.example.com",
      backendWakeTimeoutMs: 60_000,
      frontendBuildVersion: "cc489d3",
      grafanaSystemOverviewUrl: DASHBOARD_URL,
      grafanaAiPipelineUrl: "https://grafana.example/d/ai-pipeline",
    });
  });
});

describe("parseFrontendSettings, the list of the developer details (admin UI design)", () => {
  it("lists every VITE_ setting with the value in use, in the order of the settings", () => {
    expect(parseFrontendSettings({}).viteSettings).toEqual([
      { name: "VITE_REQUEST_TIMEOUT_MS", value: "10000" },
      { name: "VITE_REQUEST_RETRY_MAX_COUNT", value: "2" },
      { name: "VITE_REQUEST_RETRY_BASE_DELAY_MS", value: "500" },
      { name: "VITE_DEV_MODE", value: "false" },
      { name: "VITE_GRAFANA_TRACE_URL" },
      { name: "VITE_FRONTEND_BUILD_VERSION" },
      { name: "VITE_GRAFANA_SYSTEM_OVERVIEW_URL" },
      { name: "VITE_GRAFANA_AI_PIPELINE_URL" },
      { name: "VITE_BACKEND_WAKE_ORIGIN" },
      { name: "VITE_BACKEND_WAKE_TIMEOUT_MS", value: "90000" },
    ]);
  });

  it("lists the value of a variable that is set", () => {
    const { viteSettings } = parseFrontendSettings({ VITE_GRAFANA_TRACE_URL: TRACE_URL });

    expect(viteSettings).toContainEqual({ name: "VITE_GRAFANA_TRACE_URL", value: TRACE_URL });
  });
});

describe("parseFrontendSettings, the build version (admin UI design)", () => {
  it.each([
    ["is local on the dev server", { DEV: true }, "local"],
    ["is absent in a production build", { DEV: false }, undefined],
    ["is the value of a build", { DEV: false, VITE_FRONTEND_BUILD_VERSION: "cc489d3" }, "cc489d3"],
  ])("%s", (_case, environment, buildVersion) => {
    expect(parseFrontendSettings(environment).frontendBuildVersion).toBe(buildVersion);
  });
});

describe("parseFrontendSettings, the Grafana dashboard links (admin UI design, SEC-28)", () => {
  it.each(["https://grafana.example/d/system-overview", DASHBOARD_URL])("accepts %s", (url) => {
    expect(
      parseFrontendSettings({ VITE_GRAFANA_SYSTEM_OVERVIEW_URL: url }).grafanaSystemOverviewUrl,
    ).toBe(url);
  });

  it.each([
    ["VITE_GRAFANA_SYSTEM_OVERVIEW_URL", "http://grafana.example/d/system-overview"],
    ["VITE_GRAFANA_AI_PIPELINE_URL", "https://grafana.example/explore?trace={trace_id}"],
  ])("stops startup with a message naming %s when it is %s", (name, value) => {
    expect(() => parseFrontendSettings({ [name]: value })).toThrow(name);
  });
});

describe("parseFrontendSettings, empty and invalid values", () => {
  it("treats an empty variable as not set", () => {
    const settings = parseFrontendSettings({
      VITE_REQUEST_TIMEOUT_MS: "",
      VITE_DEV_MODE: "",
      VITE_GRAFANA_TRACE_URL: "",
      VITE_BACKEND_WAKE_ORIGIN: "",
    });

    expect(settings).toMatchObject({ requestTimeoutMs: 10_000, isDevModeAvailable: false });
    expect(settings).not.toHaveProperty("grafanaTraceUrl");
    expect(settings).not.toHaveProperty("backendWakeOrigin");
  });

  it("stops at an invalid wake origin, naming the setting (backend wake-up design, rule 10)", () => {
    expect(() =>
      parseFrontendSettings({ VITE_BACKEND_WAKE_ORIGIN: "https://backend.example.com/" }),
    ).toThrow("VITE_BACKEND_WAKE_ORIGIN must be an http or https origin without a path");
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
