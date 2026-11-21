import fc from "fast-check";
import { describe, expect, it } from "vitest";

import { rootPathByArea } from "@/features/session/model/session";
import { buildSignInPath, resolvePathAfterSignIn } from "@/features/session/model/sign-in-paths";

/** TEST-14: a property test runs the same inputs on every run. */
const PROPERTY_SEED = 20261107;
const APP_ORIGIN = "https://supportiq.invalid";

describe("buildSignInPath", () => {
  it("has no return path after a sign-out", () => {
    expect(buildSignInPath(undefined)).toBe("/sign-in");
  });

  it("encodes the page to return to", () => {
    expect(buildSignInPath("/shop/orders/ORD-20931#ticket-TCK-1042")).toBe(
      "/sign-in?returnTo=%2Fshop%2Forders%2FORD-20931%23ticket-TCK-1042",
    );
  });
});

describe("resolvePathAfterSignIn, for any return path (TEST-13)", () => {
  const returnPaths = fc.oneof(
    fc.string(),
    fc.webUrl(),
    fc.string().map((rest) => `/shop${rest}`),
    fc.string().map((rest) => `/admin${rest}`),
    fc.string().map((rest) => `//${rest}`),
    fc.string().map((rest) => `/shop\\${rest}`),
    fc
      .array(
        fc.constantFrom("..", ".", "%2e%2e", "%2E.", ".%2e", "\\..", "admin", "shop", "orders"),
      )
      .map((segments) => `/shop/${segments.join("/")}`),
  );

  it("never leaves the app and never leaves the area of the customer", () => {
    fc.assert(
      fc.property(returnPaths, (returnTo) => {
        const opened = new URL(resolvePathAfterSignIn("customer", returnTo), APP_ORIGIN);

        expect(opened.origin).toBe(APP_ORIGIN);
        expect(`${opened.pathname}/`.startsWith(`${rootPathByArea.shop}/`)).toBe(true);
      }),
      { seed: PROPERTY_SEED },
    );
  });
});

describe("resolvePathAfterSignIn, a return path inside the area", () => {
  it.each([
    ["customer", "/shop/orders/ORD-20931", "/shop/orders/ORD-20931"],
    ["customer", "/shop", "/shop"],
    ["customer", "/shop?cursor=x", "/shop?cursor=x"],
    ["staff", "/console", "/console"],
    ["admin", "/admin/accounts", "/admin/accounts"],
    [
      "customer",
      "/shop/orders/ORD-20931?x=1#ticket-TCK-1042",
      "/shop/orders/ORD-20931?x=1#ticket-TCK-1042",
    ],
    ["customer", "/shop/orders/../support", "/shop/support"],
    ["customer", "/shop/%2e%2e/shop/orders", "/shop/orders"],
  ] as const)("returns a %s from %s to %s", (role, returnTo, path) => {
    expect(resolvePathAfterSignIn(role, returnTo)).toBe(path);
  });
});

describe("resolvePathAfterSignIn, any other return path", () => {
  it.each([
    ["customer", null, "/shop"],
    ["customer", "/admin/accounts", "/shop"],
    ["customer", "/shopping", "/shop"],
    ["customer", "//evil.example/shop", "/shop"],
    ["customer", "https://evil.example/shop", "/shop"],
    ["customer", "/shop\\..\\admin", "/shop"],
    ["customer", "/shop/../admin/accounts", "/shop"],
    ["customer", "/shop/%2e%2e/admin", "/shop"],
    ["customer", "/shop/%2E%2E/admin", "/shop"],
    ["customer", "/shop/.%2e/admin", "/shop"],
    ["customer", "/shop/orders/../../admin", "/shop"],
    ["customer", "/\\evil.example/shop", "/shop"],
    ["customer", "/\t/evil.example/shop", "/shop"],
    ["customer", "//", "/shop"],
    ["manager", "/console/../shop", "/console"],
    ["admin", "/admin/%2e%2e/shop/orders", "/admin"],
    ["manager", "/shop/orders", "/console"],
    ["admin", "/console", "/admin"],
  ] as const)("opens the area root for a %s with return path %j: %s", (role, returnTo, path) => {
    expect(resolvePathAfterSignIn(role, returnTo)).toBe(path);
  });

  it("opens the start page for a role without an area", () => {
    expect(resolvePathAfterSignIn("unknown", "/shop")).toBe("/");
  });
});
