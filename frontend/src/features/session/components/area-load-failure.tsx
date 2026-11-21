/**
 * The state of a screen whose data could not load: the permission-denied state of the area for a
 * `403` (shop UI design and admin UI design, States), otherwise the error state with Try again.
 * A `401` never stays on screen: it ends the session, which opens sign-in.
 */
import {
  type FailureCategory,
  FailureState,
  type RequestFailure,
} from "@/features/backend-requests";
import { categorizeFailure, describeFailure } from "@/features/backend-requests";
import {
  AreaPermissionDenied,
  type RestrictedArea,
} from "@/features/session/components/area-permission-denied";

const PERMISSION_DENIED: FailureCategory = "permission_denied";

/** Props of {@link AreaLoadFailure}. */
export type AreaLoadFailureProps = {
  readonly area: RestrictedArea;
  /** What could not be loaded, for example "Your orders could not be loaded". */
  readonly title: string;
  readonly failure: RequestFailure;
  readonly headingLevel: 1 | 2;
  readonly isRetrying: boolean;
  readonly onRetry: () => void;
};

/**
 * Render the failure state of a screen.
 *
 * @param props - The area, the title, the failure, and the retry handler.
 * @returns The permission-denied state or the error state.
 */
export function AreaLoadFailure({
  area,
  title,
  failure,
  headingLevel,
  isRetrying,
  onRetry,
}: AreaLoadFailureProps) {
  if (categorizeFailure(failure) === PERMISSION_DENIED) {
    const { traceId } = describeFailure(failure);
    return <AreaPermissionDenied area={area} {...(traceId === undefined ? {} : { traceId })} />;
  }
  return (
    <FailureState
      title={title}
      failure={failure}
      headingLevel={headingLevel}
      isRetrying={isRetrying}
      onRetry={onRetry}
      actionSize={area === "shop" ? "lg" : "md"}
    />
  );
}
