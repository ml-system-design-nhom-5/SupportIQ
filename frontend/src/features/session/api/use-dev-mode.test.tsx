import { renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useDevMode } from "@/features/session/api/use-dev-mode";

describe("useDevMode", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("fails loudly when no composition root provides the dev mode setup", () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);

    expect(() => renderHook(useDevMode)).toThrow("useDevMode needs DevModeContext.");
  });
});
