/**
 * The dev mode switch of each account, a display preference that the browser keeps (UI-35). It
 * holds no Confidential data: only `on` or `off` under the account ID. When the browser refuses
 * storage, the switch still works until the page reloads.
 */
import { createContext } from "react";

import {
  createPreferenceStore,
  type PreferenceStorage,
} from "@/features/session/api/preference-store";
import { buildDevModePreferenceKey, type FrontendDetails } from "@/features/session/model/dev-mode";

/** The stored value of a switch that is on. */
const ON_VALUE = "on";

/** The stored value of a switch that is off. */
const OFF_VALUE = "off";

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
 * @returns The switches, which start off for every account; any other stored value is off.
 */
export function createDevModePreferences(
  storage: PreferenceStorage | undefined,
): DevModePreferences {
  const store = createPreferenceStore(storage);
  return {
    isOn: (accountId) => store.read(buildDevModePreferenceKey(accountId)) === ON_VALUE,
    setIsOn: (accountId, isOn) => {
      store.write(buildDevModePreferenceKey(accountId), isOn ? ON_VALUE : OFF_VALUE);
    },
    subscribe: store.subscribe,
  };
}
