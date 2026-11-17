/**
 * The display preferences that the browser keeps for each account, such as the dev mode switch
 * and the widths of the console columns (UI-35; console UI design, Column controls). They hold no
 * Confidential data. A preference lives in memory first, so it still works until the page reloads
 * when the browser refuses storage. The composition root provides the browser storage (ARCH-31);
 * tests and stories provide their own.
 */
import { createContext } from "react";

/** The part of `Storage` that the preferences use: `localStorage` in the browser. */
export type PreferenceStorage = {
  readonly getItem: (key: string) => string | null;
  readonly setItem: (key: string, value: string) => void;
};

/** Text values under keys, kept in memory and, where the browser allows it, in its storage. */
export type PreferenceStore = {
  /** The value, or undefined when none is kept or the browser refuses the read. */
  readonly read: (key: string) => string | undefined;
  readonly write: (key: string, value: string) => void;
  /** Calls the listener after each write, until the returned function is called. */
  readonly subscribe: (listener: () => void) => () => void;
};

/** Holds the preference store that the composition root provides. */
export const PreferenceStoreContext = createContext<PreferenceStore | null>(null);

/**
 * Create a store over a storage.
 *
 * @param storage - The browser storage, or undefined when the browser offers none.
 * @returns The store.
 */
export function createPreferenceStore(storage: PreferenceStorage | undefined): PreferenceStore {
  const changedValues = new Map<string, string>();
  const listeners = new Set<() => void>();
  return {
    read: (key) =>
      changedValues.get(key) ?? whenStorageAllows(() => storage?.getItem(key)) ?? undefined,
    write: (key, value) => {
      changedValues.set(key, value);
      // A refused write keeps the value in memory until the page reloads.
      whenStorageAllows(() => storage?.setItem(key, value));
      for (const listener of listeners) {
        listener();
      }
    },
    subscribe: (listener) => {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
  };
}

/**
 * Use the browser storage where the browser allows it. A browser refuses storage with a
 * `DOMException`, for example when the person blocks site data or the storage is full; the app
 * then works without remembering its display preferences. Every use of the storage goes through
 * here, so the refusal is handled in one place (CODE-40).
 *
 * @param action - Reads the storage, writes to it, or reads `localStorage` itself.
 * @returns What the action returns, or undefined when the browser refuses.
 * @throws Any error other than the refusal of the browser.
 */
export function whenStorageAllows<Result>(action: () => Result): Result | undefined {
  try {
    return action();
  } catch (error) {
    if (error instanceof DOMException) {
      return undefined;
    }
    throw error;
  }
}
