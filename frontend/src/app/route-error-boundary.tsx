/**
 * The error boundary of a top-level route (TS-26), such as sign-in or a whole area: an
 * unexpected error shows a plain-language state with a way out, never a stack trace or an
 * internal name (UI-25).
 */
import { ScreenErrorBoundary } from "@/app/screen-error-boundary";
import { PageColumn } from "@/design-system";

/**
 * Render the error state of a route in its own content column.
 *
 * @returns The error state.
 */
export function RouteErrorBoundary() {
  return (
    <PageColumn area="shop">
      <ScreenErrorBoundary />
    </PageColumn>
  );
}
