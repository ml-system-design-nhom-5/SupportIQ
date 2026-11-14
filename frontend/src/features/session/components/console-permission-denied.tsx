/**
 * The permission-denied state of one console screen (console UI design, States,
 * state-permission-denied.png; UI-40), next to `AreaPermissionDenied`, which refuses a whole
 * area: the screen is not for the role, and the console only says so, with the copyable trace ID
 * when `backend` sent one (UI-25). The ticket workspace and the Reports page show the same state.
 */
import { Lock } from "lucide-react";

import { StateMessage } from "@/design-system";

/** Props of {@link ConsolePermissionDenied}. */
export type ConsolePermissionDeniedProps = {
  /** The trace ID of the refusal, when `backend` sent one. */
  readonly traceId?: string;
};

/**
 * Render the permission-denied state.
 *
 * @param props - The trace ID of the refusal.
 * @returns The state message, with the screen's heading.
 */
export function ConsolePermissionDenied({ traceId }: ConsolePermissionDeniedProps) {
  return (
    <StateMessage
      icon={Lock}
      headingLevel={1}
      title="You cannot open this page"
      description="Your role does not allow it. Ask a manager if you need it."
      {...(traceId === undefined ? {} : { traceId })}
    />
  );
}
