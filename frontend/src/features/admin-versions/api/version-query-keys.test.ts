import { describe, expect, it } from "vitest";

import { versionQueryKeys } from "@/features/admin-versions/api/version-query-keys";

describe("versionQueryKeys", () => {
  it("builds the key of the versions under the feature's root key (TS-19)", () => {
    expect(versionQueryKeys.versions()).toEqual(["admin-versions", "versions"]);
  });
});
