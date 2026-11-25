/**
 * The banners of the workspace (console UI design, placement rule 3): Authority required (UI-19),
 * which stays while the flag is set, and the failures of the view and of the last reload, which
 * leave the ticket on screen.
 */
import { authorityRequiredPresentation, StatusBanner } from "@/design-system";
import {
  describeFailure,
  FailureBanner,
  isWriteOutcomeUnknown,
  type RequestFailure,
} from "@/features/backend-requests";

/** Props of {@link WorkspaceBanners}. */
type WorkspaceBannersProps = {
  readonly isAuthorityRequired: boolean;
  /** The failure of `recordTicketView`; undefined after a success. */
  readonly viewFailure: RequestFailure | undefined;
  /** The failure of the last reload; undefined while reloads succeed. */
  readonly refreshFailure: RequestFailure | undefined;
};

/**
 * Render the banners.
 *
 * @param props - The authority flag and the failures.
 * @returns The banners that apply.
 */
export function WorkspaceBanners({
  isAuthorityRequired,
  viewFailure,
  refreshFailure,
}: WorkspaceBannersProps) {
  return (
    <>
      {isAuthorityRequired ? (
        <StatusBanner
          tone="warning"
          icon={authorityRequiredPresentation.icon}
          lead={`${authorityRequiredPresentation.label}.`}
        >
          The AI output is supporting information only. A manager decides and sends the reply.
        </StatusBanner>
      ) : null}
      {viewFailure === undefined ? null : <ViewFailureBanner failure={viewFailure} />}
      {refreshFailure === undefined ? null : (
        <FailureBanner
          lead="This ticket could not be updated. It shows the last loaded state."
          failure={refreshFailure}
        />
      )}
    </>
  );
}

/**
 * Say what happened to the view of this opening (ERR-07). After a timeout, a lost connection,
 * `502`, or `504`, `backend` may have recorded it. The screen has no way to send the view again, so
 * the banner offers no retry: staff keep working on the ticket.
 *
 * @param props - The failure of `recordTicketView`.
 * @returns The banner, announced as an alert.
 */
function ViewFailureBanner({ failure }: { readonly failure: RequestFailure }) {
  const { traceId } = describeFailure(failure);
  const traceIdProps = traceId === undefined ? {} : { traceId };
  return isWriteOutcomeUnknown(failure) ? (
    <StatusBanner
      tone="danger"
      lead="The opening of this ticket may have been recorded."
      {...traceIdProps}
    >
      We could not confirm it. You can keep working on this ticket.
    </StatusBanner>
  ) : (
    <StatusBanner
      tone="danger"
      lead="The opening of this ticket was not recorded."
      {...traceIdProps}
    >
      You can keep working on this ticket.
    </StatusBanner>
  );
}
