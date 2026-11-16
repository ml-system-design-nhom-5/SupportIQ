/**
 * Read and switch dev mode for the signed-in account (UI-35). The account menu offers the switch,
 * and the screens add their developer details while it is on. Dev mode never changes what the
 * role may do: `backend` decides every permission (UI-40).
 */
import { use, useSyncExternalStore } from "react";

import { DevModeContext, type DevModeSetup } from "@/features/session/api/dev-mode-preferences";
import { useSignedInAccountId, useSignedInRole } from "@/features/session/api/use-current-session";
import {
  buildTraceUrl,
  canUseDevMode,
  type FrontendDetails,
} from "@/features/session/model/dev-mode";

/** Dev mode for the signed-in account. */
export type DevMode = {
  /** Whether dev mode is available and the role of the account can switch it on. */
  readonly canSwitch: boolean;
  /** Whether the screens show their developer details. */
  readonly isOn: boolean;
  readonly setIsOn: (isOn: boolean) => void;
  /** The link to a trace in Grafana, or undefined when no Grafana is set up. */
  readonly traceHrefOf: (traceId: string) => string | undefined;
  readonly frontendDetails: FrontendDetails;
};

/**
 * Read dev mode.
 *
 * @returns Whether the account can switch it and whether it is on, the switch, and the trace link.
 * @throws Error when no composition root provides the dev mode setup.
 */
export function useDevMode(): DevMode {
  const setup = useDevModeSetup();
  const accountId = useSignedInAccountId();
  const role = useSignedInRole();
  const isStoredOn = useSyncExternalStore(
    setup.preferences.subscribe,
    () => accountId !== undefined && setup.preferences.isOn(accountId),
  );
  const canSwitch =
    setup.isAvailable && accountId !== undefined && role !== undefined && canUseDevMode(role);
  const { grafanaTraceUrl } = setup;
  return {
    canSwitch,
    isOn: canSwitch && isStoredOn,
    setIsOn: (isOn) => {
      if (accountId !== undefined) {
        setup.preferences.setIsOn(accountId, isOn);
      }
    },
    traceHrefOf: (traceId) =>
      grafanaTraceUrl === undefined ? undefined : buildTraceUrl(grafanaTraceUrl, traceId),
    frontendDetails: setup.frontendDetails,
  };
}

/**
 * Read the dev mode setup.
 *
 * @returns The setup that the composition root provides.
 * @throws Error when there is none.
 */
function useDevModeSetup(): DevModeSetup {
  const setup = use(DevModeContext);
  if (setup === null) {
    throw new Error("useDevMode needs DevModeContext.");
  }
  return setup;
}
