import { describe, expect, it, vi } from "vitest";

import { createDevModePreferences } from "@/features/session/api/dev-mode-preferences";
import { type PreferenceStorage, whenStorageAllows } from "@/features/session/api/preference-store";
import { createMemoryStorage } from "@/test/memory-storage";

/** A storage that the browser refuses, as with blocked site data. */
const refusedStorage: PreferenceStorage = {
  getItem: () => {
    throw new DOMException("The operation is insecure.", "SecurityError");
  },
  setItem: () => {
    throw new DOMException("The quota has been exceeded.", "QuotaExceededError");
  },
};

describe("createDevModePreferences", () => {
  it("starts off and stores the switch of each account under its own key", () => {
    const { storage, stored } = createMemoryStorage();
    const preferences = createDevModePreferences(storage);

    expect(preferences.isOn("a1")).toBe(false);
    preferences.setIsOn("a1", true);

    expect(preferences.isOn("a1")).toBe(true);
    expect(stored).toEqual(new Map([["supportiq.dev-mode.a1", "on"]]));
  });

  it("never gives one account the choice of another", () => {
    const { storage } = createMemoryStorage({ "supportiq.dev-mode.a1": "on" });
    const preferences = createDevModePreferences(storage);

    expect(preferences.isOn("a1")).toBe(true);
    expect(preferences.isOn("a2")).toBe(false);
  });

  it("stores off when the switch goes off", () => {
    const { storage, stored } = createMemoryStorage({ "supportiq.dev-mode.a1": "on" });
    const preferences = createDevModePreferences(storage);

    preferences.setIsOn("a1", false);

    expect(preferences.isOn("a1")).toBe(false);
    expect(stored.get("supportiq.dev-mode.a1")).toBe("off");
  });

  it("counts any other stored value as off", () => {
    const { storage } = createMemoryStorage({ "supportiq.dev-mode.a1": "yes" });

    expect(createDevModePreferences(storage).isOn("a1")).toBe(false);
  });
});

describe("createDevModePreferences without a usable storage", () => {
  it("reads off and keeps the switch in memory when the browser refuses storage", () => {
    const preferences = createDevModePreferences(refusedStorage);

    expect(preferences.isOn("a1")).toBe(false);
    preferences.setIsOn("a1", true);
    expect(preferences.isOn("a1")).toBe(true);
  });

  it("works without any storage", () => {
    const preferences = createDevModePreferences(undefined);

    preferences.setIsOn("a1", true);

    expect(preferences.isOn("a1")).toBe(true);
  });

  it("lets an error that is not a refusal of the browser through (CODE-40)", () => {
    const preferences = createDevModePreferences({
      getItem: () => {
        throw new TypeError("A defect.");
      },
      setItem: () => {
        throw new TypeError("A defect.");
      },
    });

    expect(() => preferences.isOn("a1")).toThrow(TypeError);
    expect(() => {
      preferences.setIsOn("a1", true);
    }).toThrow(TypeError);
  });

  it("tells each listener about a change until it unsubscribes", () => {
    const preferences = createDevModePreferences(undefined);
    const listener = vi.fn();
    const unsubscribe = preferences.subscribe(listener);

    preferences.setIsOn("a1", true);
    unsubscribe();
    preferences.setIsOn("a1", false);

    expect(listener).toHaveBeenCalledOnce();
  });
});

describe("whenStorageAllows", () => {
  it("returns what the action returns", () => {
    expect(whenStorageAllows(() => "on")).toBe("on");
  });

  it("returns undefined when the browser refuses storage with a DOMException", () => {
    expect(
      whenStorageAllows((): string => {
        throw new DOMException("The operation is insecure.", "SecurityError");
      }),
    ).toBeUndefined();
  });

  it("lets any other error through (CODE-40)", () => {
    expect(() =>
      whenStorageAllows((): string => {
        throw new TypeError("A defect.");
      }),
    ).toThrow(TypeError);
  });
});
