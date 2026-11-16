/**
 * The "Developer details" panel of a screen of the admin area (admin UI design, Developer details
 * in the admin area; UI-35), collapsed until opened: the details of the screen, then what frontend
 * tells about itself. It renders nothing while dev mode is off, so the screen stays as it is.
 */
import { Code } from "lucide-react";
import type { ReactNode } from "react";

import { DisclosurePanel, Stack } from "@/design-system";
import { useDevMode } from "@/features/session/api/use-dev-mode";
import { FrontendDetailsView } from "@/features/session/components/frontend-details-view";

/** Props of {@link DevModeDetailsPanel}. */
export type DevModeDetailsPanelProps = {
  /** The details of the screen; absent when the screen adds none. */
  readonly children?: ReactNode;
};

/**
 * Render the panel while dev mode is on.
 *
 * @param props - The details of the screen.
 * @returns The panel, or nothing while dev mode is off.
 */
export function DevModeDetailsPanel({ children }: DevModeDetailsPanelProps) {
  const devMode = useDevMode();
  if (!devMode.isOn) {
    return null;
  }
  return (
    <DisclosurePanel title="Developer details" icon={Code}>
      <Stack gap="3">
        {children}
        <FrontendDetailsView details={devMode.frontendDetails} />
      </Stack>
    </DisclosurePanel>
  );
}
