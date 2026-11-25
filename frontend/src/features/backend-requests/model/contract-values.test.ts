import { describe, expect, it } from "vitest";

import {
  countContractCharacters,
  MESSAGE_MAX_LENGTH,
  requireMembers,
  toMoney,
} from "@/features/backend-requests/model/contract-values";
import { readOperationExample } from "@/test/contract-examples";
import { readContractSchema } from "@/test/contract-schemas";

describe("MESSAGE_MAX_LENGTH", () => {
  it("is the maxLength of MessageText in the contract", () => {
    expect(readContractSchema("MessageText")).toContain(
      `maxLength: ${String(MESSAGE_MAX_LENGTH)}\n`,
    );
  });
});

describe("requireMembers", () => {
  it("accepts members with a falsy value, which are present", () => {
    expect(() => {
      requireMembers({ is_active: false, amount_minor: 0, name: "" }, [
        "is_active",
        "amount_minor",
        "name",
      ]);
    }).not.toThrow();
  });

  it.each([undefined, null])("names a member that is %s", (value) => {
    expect(() => {
      requireMembers({ order_id: value }, ["order_id"]);
    }).toThrow("The response has no order_id.");
  });

  it("types the members as present after the call, so they read without a check", () => {
    const body: { readonly kb_version?: string | null } = { kb_version: "kb-2026.11" };

    requireMembers(body, ["kb_version"]);
    // The type check fails here if requireMembers does not narrow the body.
    const kbVersion: string = body.kb_version;

    expect(kbVersion).toBe("kb-2026.11");
  });
});

describe("countContractCharacters", () => {
  it.each([
    ["", 0],
    ["Hello", 5],
    ["Tiền hoàn", 9],
    ["👍🏽", 2],
    ["😊", 1],
    ["   ", 3],
    ["a\nb", 3],
  ])("counts %j as %i code points, as JSON Schema counts length", (text, count) => {
    expect(countContractCharacters(text)).toBe(count);
  });
});

describe("toMoney", () => {
  it("stops at an amount without its members", () => {
    expect(() => {
      Reflect.apply(toMoney, undefined, [{}]);
    }).toThrow("The response has no amount_minor.");
  });

  it("maps the contract's Money to camelCase, keeping minor units (CON-16)", () => {
    const product = readOperationExample("getShopProduct", 200, "found");

    expect(toMoney(product.price)).toEqual({ amountMinor: 8900, currency: "USD" });
  });
});
