/**
 * The page banner after a create or reset dialog closed with an outcome (account management
 * design, Create account dialog and Reset password dialog): the account that was created with the
 * login name of the response, the reset password, or the reset that did not happen. The display
 * name is Confidential: it is only rendered, never logged (SEC-01).
 */
import { Button, StatusBanner } from "@/design-system";
import {
  accountFormText,
  buildAccountCreatedText,
  buildResetOutcomeText,
} from "@/features/admin-accounts/model/account-form-text";
import type { AccountNotice } from "@/features/admin-accounts/model/account-notice";
import { assertNever, describeFailure, type RequestFailure } from "@/features/backend-requests";

/** Props of {@link AccountNoticeBanner}. */
export type AccountNoticeBannerProps = {
  readonly notice: AccountNotice;
  /** Loads the list again and clears the banner. */
  readonly onReload: () => void;
};

/**
 * Render the banner of a notice.
 *
 * @param props - The notice and the reload handler.
 * @returns The banner, or nothing for permission denied, which replaces the screen.
 */
export function AccountNoticeBanner({ notice, onReload }: AccountNoticeBannerProps) {
  switch (notice.kind) {
    case "created":
      return (
        <StatusBanner
          tone="success"
          lead={buildAccountCreatedText(notice.account.displayName, notice.account.loginName)}
        />
      );
    case "password_reset": {
      const text = buildResetOutcomeText(notice.account.displayName);
      return (
        <StatusBanner tone="success" lead={text.reset}>
          {notice.isSignedOutEverywhere ? text.signedOutEverywhere : null}
        </StatusBanner>
      );
    }
    case "reset_not_found":
      return (
        <StatusBanner
          tone="danger"
          lead={buildResetOutcomeText(notice.account.displayName).notFound}
          {...buildTraceIdProps(notice.failure)}
        >
          {accountFormText.listLoadedAgain}
        </StatusBanner>
      );
    case "reset_refused":
      return (
        <StatusBanner
          tone="danger"
          lead={buildResetOutcomeText(notice.account.displayName).notReset}
          action={<Button onClick={onReload}>Reload list</Button>}
          {...buildTraceIdProps(notice.failure)}
        >
          {accountFormText.loadListAgain}
        </StatusBanner>
      );
    case "permission_denied":
      return null;
    default:
      assertNever(notice);
  }
}

/**
 * Build the trace ID prop of a banner (UI-25).
 *
 * @param failure - The failure of the reset.
 * @returns The trace ID when `backend` sent one.
 */
function buildTraceIdProps(failure: RequestFailure): { readonly traceId?: string } {
  const { traceId } = describeFailure(failure);
  return traceId === undefined ? {} : { traceId };
}
