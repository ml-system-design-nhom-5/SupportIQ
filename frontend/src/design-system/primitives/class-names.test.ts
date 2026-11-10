import { describe, expect, it } from "vitest";

import { cn } from "@/design-system/primitives/class-names";

describe("cn", () => {
  it("joins class names and drops falsy values", () => {
    expect(cn("flex", undefined, false, "gap-2")).toBe("flex gap-2");
  });

  it("lets a later class win over a conflicting earlier one", () => {
    expect(cn("px-3", "px-4")).toBe("px-4");
  });

  it("keeps token color and size classes apart", () => {
    expect(cn("text-sm", "text-text-muted")).toBe("text-sm text-text-muted");
  });
});
