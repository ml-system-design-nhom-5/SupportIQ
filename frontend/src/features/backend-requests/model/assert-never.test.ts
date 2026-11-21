import { describe, expect, it } from "vitest";

import { assertNever } from "@/features/backend-requests/model/assert-never";

describe("assertNever", () => {
  it("names the value that reached it at runtime", () => {
    expect(() => {
      Reflect.apply(assertNever, undefined, ["archived"]);
    }).toThrow('No case handled the value "archived".');
  });
});
