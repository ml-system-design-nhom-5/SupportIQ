/**
 * The banners of the workspace (console UI design, placement rule 3): Authority required (UI-19),
 * which stays while the flag is set, and the failures of the view and of the last reload, which
 * leave the ticket on screen.
 */
import { StatusBanner } from "@/design-system";
import { FailureBanner, type RequestFailure } from "@/features/backend-requests";

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
        <StatusBanner tone="warning" lead="Authority required.">
          The AI output is supporting information only. A manager decides and sends the reply.
        </StatusBanner>
      ) : null}
      {viewFailure === undefined ? null : (
        <FailureBanner lead="The opening of this ticket was not recorded." failure={viewFailure} />
      )}
      {refreshFailure === undefined ? null : (
        <FailureBanner
          lead="This ticket could not be updated. It shows the last loaded state."
          failure={refreshFailure}
        />
      )}
    </>
  );
}
