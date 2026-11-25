/**
 * The banner of a change that did not happen, or that may have happened (admin UI design, Accounts
 * and States). It names the account and follows `violated_rule` of the `422` body: the last-manager
 * text, or, for any other value, an unknown one included, a request to reload the list.
 */
import { Button, StatusBanner } from "@/design-system";
import type { AccountChange } from "@/features/admin-accounts/model/account";
import { classifyChangeFailure } from "@/features/admin-accounts/model/account-change-failure";
import {
  buildChangeFailureLead,
  buildChangeOutcomeUnknownLead,
} from "@/features/admin-accounts/model/account-change-text";
import { assertNever, describeFailure, type RequestFailure } from "@/features/backend-requests";

/** Props of {@link AccountChangeBanner}. */
export type AccountChangeBannerProps = {
  /** The change that did not happen, or that may have happened. */
  readonly change: AccountChange;
  readonly failure: RequestFailure;
  /** Loads the list again and clears the banner. */
  readonly onReload: () => void;
};

/**
 * Render the banner.
 *
 * @param props - The change, the failure, and the reload handler.
 * @returns The banner, announced as an alert.
 */
export function AccountChangeBanner({ change, failure, onReload }: AccountChangeBannerProps) {
  const { traceId } = describeFailure(failure);
  const kind = classifyChangeFailure(failure);
  return (
    <StatusBanner
      tone="danger"
      lead={
        kind === "outcome_unknown"
          ? buildChangeOutcomeUnknownLead(change)
          : buildChangeFailureLead(change)
      }
      {...(traceId === undefined ? {} : { traceId })}
      {...(kind === "refused" ? { action: <Button onClick={onReload}>Reload list</Button> } : {})}
    >
      {buildChangeFailureText(failure)}
    </StatusBanner>
  );
}

/**
 * Choose the text after the lead of the banner.
 *
 * @param failure - The failure of the change.
 * @returns The sentence that says why, and what to do next.
 */
function buildChangeFailureText(failure: RequestFailure): string {
  const kind = classifyChangeFailure(failure);
  switch (kind) {
    case "last_active_manager":
      return "This change would leave no active manager. Make another account a manager first.";
    case "refused":
      return "The list may be out of date. Reload the list, then try again.";
    case "not_found":
      return "This account was not found. The list was loaded again.";
    case "outcome_unknown":
      return "We could not confirm it. The list is loading again. If the row does not change, it is safe to try again.";
    case "permission_denied":
    case "technical":
      return describeFailure(failure).message;
    default:
      assertNever(kind);
  }
}
