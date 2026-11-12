import { renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import {
  buildIdempotentWriteKey,
  IdempotencyKeyFactoryContext,
  idempotentWriteMutationKey,
  useCreateIdempotencyKey,
  useFormIdempotencyKey,
} from "@/features/backend-requests/api/idempotent-writes";

describe("useCreateIdempotencyKey", () => {
  it("returns the factory that the composition root provides (ARCH-31)", () => {
    const createKey = () => "00000000-0000-4000-8000-000000000001";

    const { result } = renderHook(useCreateIdempotencyKey, {
      wrapper: ({ children }) => (
        <IdempotencyKeyFactoryContext value={createKey}>{children}</IdempotencyKeyFactoryContext>
      ),
    });

    expect(result.current).toBe(createKey);
  });

  it("fails loudly when no composition root provides a factory", () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);

    expect(() => renderHook(useCreateIdempotencyKey)).toThrow(
      "useCreateIdempotencyKey needs IdempotencyKeyFactoryContext.",
    );

    vi.restoreAllMocks();
  });
});

describe("buildIdempotentWriteKey", () => {
  it("starts with the prefix that receives the retry policy", () => {
    expect(buildIdempotentWriteKey("createShopTicket")).toEqual([
      ...idempotentWriteMutationKey,
      "createShopTicket",
    ]);
  });
});

describe("useFormIdempotencyKey (account management design, Shared behavior)", () => {
  it("reuses the key while the fields stay the same, and creates a new one after an edit", () => {
    let keyCount = 0;
    const createKey = () => {
      keyCount += 1;
      return `00000000-0000-4000-8000-${String(keyCount).padStart(12, "0")}`;
    };
    const { result } = renderHook(useFormIdempotencyKey, {
      wrapper: ({ children }) => (
        <IdempotencyKeyFactoryContext value={createKey}>{children}</IdempotencyKeyFactoryContext>
      ),
    });

    const firstKey = result.current.getOrCreateKey();
    const keyOfSameFields = result.current.getOrCreateKey();
    result.current.forgetKey();
    const keyAfterEdit = result.current.getOrCreateKey();

    expect(keyOfSameFields).toBe(firstKey);
    expect(keyAfterEdit).not.toBe(firstKey);
  });
});
