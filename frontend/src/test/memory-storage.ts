/**
 * A browser storage in memory for tests, which behaves as `localStorage` does for the display
 * preferences of the app, such as dev mode (UI-35).
 */
import type { PreferenceStorage } from "@/features/session";

/** A storage in memory and the values it holds. */
export type MemoryStorage = {
  readonly storage: PreferenceStorage;
  readonly stored: Map<string, string>;
};

/**
 * Create a storage in memory.
 *
 * @param values - The values that are already stored.
 * @returns The storage and its values.
 */
export function createMemoryStorage(values: Readonly<Record<string, string>> = {}): MemoryStorage {
  const stored = new Map(Object.entries(values));
  return {
    storage: {
      getItem: (key) => stored.get(key) ?? null,
      setItem: (key, value) => {
        stored.set(key, value);
      },
    },
    stored,
  };
}
