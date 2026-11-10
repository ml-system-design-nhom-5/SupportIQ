import { renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";

import { ClockContext, systemClock, useNow } from "@/design-system/format/clock";

describe("useNow", () => {
  it("reads the time of the clock that the provider fixes", () => {
    const fixed = new Date("2026-11-05T09:00:00Z");
    const wrapper = ({ children }: { readonly children: ReactNode }) => (
      <ClockContext value={() => fixed}>{children}</ClockContext>
    );

    const { result } = renderHook(() => useNow(), { wrapper });

    expect(result.current).toBe(fixed);
  });

  it("reads the system clock without a provider", () => {
    const { result } = renderHook(() => useNow());

    expect(result.current).toBeInstanceOf(Date);
  });
});

describe("systemClock", () => {
  it("returns a new date on each call", () => {
    expect(systemClock()).not.toBe(systemClock());
  });
});
