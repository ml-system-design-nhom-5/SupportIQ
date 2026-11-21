import { describe, expect, it } from "vitest";

import {
  getRoleArea,
  getRoleLabel,
  toAccountRole,
  toSession,
} from "@/features/session/model/session";
import { readOperationExample } from "@/test/contract-examples";

describe("toSession", () => {
  it("maps SessionView to a camelCase view model (TS-09)", () => {
    const view = readOperationExample("getCurrentSession", 200, "staff");

    expect(toSession(view)).toEqual({
      accountId: "9a7d3e21-6c4b-4f8e-b1a2-3c5d7e9f0a12",
      displayName: "Mai Nguyen",
      role: "staff",
    });
  });
});

describe("toAccountRole", () => {
  it.each(["customer", "staff", "manager", "admin"] as const)("keeps the known role %s", (role) => {
    expect(toAccountRole(role)).toBe(role);
  });

  it.each(["supervisor", "auditor", "", "ADMIN"])(
    "maps the unknown role %j to unknown (CON-22)",
    (role) => {
      expect(toAccountRole(role)).toBe("unknown");
    },
  );
});

describe("getRoleArea", () => {
  it.each([
    ["customer", "shop"],
    ["staff", "console"],
    ["manager", "console"],
    ["admin", "admin"],
    ["unknown", "none"],
  ] as const)("opens the area of %s: %s", (role, area) => {
    expect(getRoleArea(role)).toBe(area);
  });
});

describe("getRoleLabel", () => {
  it.each([
    ["customer", "Customer"],
    ["staff", "Staff"],
    ["manager", "Manager"],
    ["admin", "Admin"],
    ["unknown", "Unknown role"],
  ] as const)("names %s as %s", (role, label) => {
    expect(getRoleLabel(role)).toBe(label);
  });
});
