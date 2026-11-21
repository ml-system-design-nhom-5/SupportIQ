/**
 * The Reports page for a role that may not read the report (console UI design, States,
 * state-permission-denied.png; UI-40). A role other than manager sees it at once, and the page
 * sends no request. A manager whom `backend` refuses with `403` sees it too, with the copyable
 * trace ID (UI-25), because `backend` stays the check (SEC-20). Staff see the same state as for a
 * ticket they may not open. An account without the console, which has no account menu in the
 * console, sees the state of the console area with Sign out.
 */
import { CenteredContent } from "@/design-system";
import { describeFailure, type RequestFailure } from "@/features/backend-requests";
import {
  AreaPermissionDenied,
  ConsolePermissionDenied,
  getRoleArea,
  useSignedInRole,
} from "@/features/session";

/** Props of {@link ReportsPermissionDenied}. */
type ReportsPermissionDeniedProps = {
  /** The `403` of the report; absent when the page sent no request for the role. */
  readonly failure?: RequestFailure;
};

/**
 * Render the permission-denied state of the page.
 *
 * @param props - The refusal of `backend`, when there was one.
 * @returns The state message in the middle of the page.
 */
export function ReportsPermissionDenied({ failure }: ReportsPermissionDeniedProps) {
  const role = useSignedInRole();
  const traceId = failure === undefined ? undefined : describeFailure(failure).traceId;
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
