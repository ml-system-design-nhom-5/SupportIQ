import { describe, expect, it } from "vitest";

import { requireMembers, toMoney } from "@/features/backend-requests/model/contract-values";
import { readOperationExample } from "@/test/contract-examples";

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
