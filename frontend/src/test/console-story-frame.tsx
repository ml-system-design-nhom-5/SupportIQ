/**
 * The frame of the console screens in stories: the console app bar and the inbox next to the
 * screen, as the router composes them, so each state of a screen shows in its layout (UI-23).
 */
import type { ReactNode } from "react";

import { AppBar, ConsoleShell } from "@/design-system";
import { ConsoleTicketsArea } from "@/features/console-tickets";

/** Props of {@link ConsoleStoryFrame}. */
type ConsoleStoryFrameProps = {
  readonly children: ReactNode;
};

/**
 * Render a console screen next to the inbox.
 *
 * @param props - The screen.
 * @returns The console frame.
 */
export function ConsoleStoryFrame({ children }: ConsoleStoryFrameProps) {
  return (
    <ConsoleShell appBar={<AppBar variant="console" brandName="SupportIQ" areaName="Console" />}>
      <ConsoleTicketsArea>{children}</ConsoleTicketsArea>
    </ConsoleShell>
  );
}
