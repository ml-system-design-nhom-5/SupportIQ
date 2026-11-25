import { describe, expect, it } from "vitest";

import { isSessionQueryKey, sessionQueryKeys } from "@/features/session/api/session-query-keys";

describe("sessionQueryKeys", () => {
  it("builds the key of the current session under the feature's root key", () => {
    expect(sessionQueryKeys.current()).toEqual(["session", "current"]);
  });

  it("recognizes its own keys and no other feature's", () => {
    expect(isSessionQueryKey(sessionQueryKeys.current())).toBe(true);
    expect(isSessionQueryKey(["shop-orders", "list"])).toBe(false);
  });
});
