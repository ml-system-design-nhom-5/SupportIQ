import { describe, expect, it } from "vitest";

import {
  buildDevModePreferenceKey,
  buildTraceUrl,
  canUseDevMode,
} from "@/features/session/model/dev-mode";

describe("canUseDevMode (UI-35)", () => {
  it.each([
    ["staff", true],
    ["manager", true],
    ["admin", true],
    ["customer", false],
    ["unknown", false],
  ] as const)("lets %s switch dev mode: %s", (role, canSwitch) => {
    expect(canUseDevMode(role)).toBe(canSwitch);
  });
});

describe("buildDevModePreferenceKey", () => {
  it("keeps one switch per account", () => {
    expect(buildDevModePreferenceKey("a1")).toBe("supportiq.dev-mode.a1");
    expect(buildDevModePreferenceKey("a2")).not.toBe(buildDevModePreferenceKey("a1"));
  });
});

describe("buildTraceUrl", () => {
  it("puts the trace ID where the setting has its slot", () => {
    expect(
      buildTraceUrl(
        "https://grafana.example/explore?trace={trace_id}&view=1",
        "4bf92f3577b34da6a3ce929d0e0e4736",
      ),
    ).toBe("https://grafana.example/explore?trace=4bf92f3577b34da6a3ce929d0e0e4736&view=1");
  });

  it("encodes the trace ID, so it never changes the rest of the link", () => {
    expect(buildTraceUrl("https://grafana.example/t/{trace_id}", "a&b=c")).toBe(
      "https://grafana.example/t/a%26b%3Dc",
    );
  });
});
