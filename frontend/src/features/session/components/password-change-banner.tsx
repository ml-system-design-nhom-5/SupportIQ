/**
 * The banner of a password change that failed (account management design, Change password page).
 * A wrong current password shows at its field instead; any other `422` asks to check the fields;
 * an unknown outcome says that the password may have been changed; any other failure is the shared
 * failure banner, with the trace ID when there is one (UI-25).
 */
import { StatusBanner } from "@/design-system";
import {
  assertNever,
  describeFailure,
  FailureBanner,
  type RequestFailure,
} from "@/features/backend-requests";
import {
  classifyPasswordChangeFailure,
  passwordChangeText,
} from "@/features/session/model/password-change";

/** Props of {@link PasswordChangeBanner}. */
export type PasswordChangeBannerProps = {
  readonly failure: RequestFailure;
};

/**
 * Render the banner of a failed change.
 *
 * @param props - The failure of the change.
 * @returns The banner, announced as an alert, or nothing for a wrong current password.
 */
export function PasswordChangeBanner({ failure }: PasswordChangeBannerProps) {
  const { traceId } = describeFailure(failure);
  const traceIdProps = traceId === undefined ? {} : { traceId };
  const kind = classifyPasswordChangeFailure(failure);
  switch (kind) {
    case "current_password_incorrect":
      return null;
    case "refused":
      return (
        <StatusBanner tone="danger" lead={passwordChangeText.notChanged} {...traceIdProps}>
          {passwordChangeText.checkFields}
        </StatusBanner>
      );
    case "outcome_unknown":
      return (
        <StatusBanner tone="danger" lead={passwordChangeText.mayHaveChanged} {...traceIdProps}>
          {passwordChangeText.submitAgain}
        </StatusBanner>
      );
    case "technical":
      return <FailureBanner lead={passwordChangeText.notChanged} failure={failure} />;
    default:
      assertNever(kind);
  }
}
