/**
 * The Reports page when `backend` refuses it with `403` (console UI design, States,
 * state-permission-denied.png; UI-40): `backend` decided, and the page only says so, with the
 * copyable trace ID (UI-25). Staff see the same state as for a ticket they may not open. An
 * account without the console, which has no account menu in the console, sees the state of the
 * console area with Sign out.
 */
import { CenteredContent } from "@/design-system";
import { describeFailure, type RequestFailure } from "@/features/backend-requests";
import { ConsolePermissionDenied } from "@/features/console-tickets";
import { AreaPermissionDenied, getRoleArea, useSignedInRole } from "@/features/session";

/** Props of {@link ReportsPermissionDenied}. */
type ReportsPermissionDeniedProps = {
  /** The `403` of the report. */
  readonly failure: RequestFailure;
};

/**
 * Render the permission-denied state of the page.
 *
 * @param props - The failure.
 * @returns The state message in the middle of the page.
 */
export function ReportsPermissionDenied({ failure }: ReportsPermissionDeniedProps) {
  const role = useSignedInRole();
  const { traceId } = describeFailure(failure);
  const traceIdProps = traceId === undefined ? {} : { traceId };
  const isConsoleAccount = role === undefined || getRoleArea(role) === "console";
  return (
    <CenteredContent>
      {isConsoleAccount ? (
        <ConsolePermissionDenied {...traceIdProps} />
      ) : (
        <AreaPermissionDenied area="console" {...traceIdProps} />
      )}
    </CenteredContent>
  );
}
