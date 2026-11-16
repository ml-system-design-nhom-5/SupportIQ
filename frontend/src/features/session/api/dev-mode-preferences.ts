/**
 * The dev mode switch of each account, a display preference that the browser keeps (UI-35). It
 * holds no Confidential data: only `on` or `off` under the account ID. The composition root
 * provides the browser storage (ARCH-31); tests and stories provide their own. When the browser
 * refuses storage, the switch still works until the page reloads.
 */
import { createContext } from "react";

import { buildDevModePreferenceKey, type FrontendDetails } from "@/features/session/model/dev-mode";

/** The stored value of a switch that is on. */
const ON_VALUE = "on";

/** The stored value of a switch that is off. */
const OFF_VALUE = "off";

/** The part of `Storage` that the preferences use: `localStorage` in the browser. */
export type PreferenceStorage = {
  readonly getItem: (key: string) => string | null;
  readonly setItem: (key: string, value: string) => void;
};

/** The dev mode switches of the accounts that use this browser. */
export type DevModePreferences = {
  readonly isOn: (accountId: string) => boolean;
  readonly setIsOn: (accountId: string, isOn: boolean) => void;
  /** Calls the listener after each change, until the returned function is called. */
  readonly subscribe: (listener: () => void) => () => void;
};

/** What the composition root provides for dev mode. */
export type DevModeSetup = {
  /** The environment setting that makes dev mode available. */
  readonly isAvailable: boolean;
  /** The Grafana trace link, with `{trace_id}`; absent when no Grafana is set up. */
  readonly grafanaTraceUrl?: string;
  readonly preferences: DevModePreferences;
  /** What frontend tells about itself in the developer details of the admin area. */
  readonly frontendDetails: FrontendDetails;
};

/** Holds the dev mode setup that the composition root provides. */
export const DevModeContext = createContext<DevModeSetup | null>(null);

/**
 * Create the switches over a storage.
 *
 * @param storage - The browser storage, or undefined when the browser offers none.
 * @returns The switches, which start off for every account.
 */
export function createDevModePreferences(
  storage: PreferenceStorage | undefined,
): DevModePreferences {
  const changedValues = new Map<string, boolean>();
  const listeners = new Set<() => void>();
  return {
    isOn: (accountId) => {
      const key = buildDevModePreferenceKey(accountId);
      // A refused read counts as off.
      return changedValues.get(key) ?? whenStorageAllows(() => storage?.getItem(key)) === ON_VALUE;
    },
    setIsOn: (accountId, isOn) => {
      const key = buildDevModePreferenceKey(accountId);
      changedValues.set(key, isOn);
      // A refused write keeps the switch in memory until the page reloads.
      whenStorageAllows(() => storage?.setItem(key, isOn ? ON_VALUE : OFF_VALUE));
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
