/**
 * The reset dialog of the Accounts screen (account management design, Reset password dialog): a
 * suggested password and whether every session of the account ends. A `404` or a `422` closes the
 * dialog with a page banner, because only an outdated list offers the action. The
 * `Idempotency-Key` stays until a field changes, so sending the same fields again after an unknown
 * outcome is safe (account management design, Shared behavior). The dialog unmounts when it
 * closes, so its password and its write are gone.
 */
import { useState } from "react";

import { Checkbox, type DialogReturnFocus, FormDialog, StatusBanner } from "@/design-system";
import { useRandomBytes } from "@/features/admin-accounts/api/random-bytes";
import { useResetPassword } from "@/features/admin-accounts/api/use-reset-password";
import { SuggestedPasswordField } from "@/features/admin-accounts/components/suggested-password-field";
import type { Account } from "@/features/admin-accounts/model/account";
import { classifyResetFailure } from "@/features/admin-accounts/model/account-form-failure";
import {
  accountFormText,
  buildResetDialogText,
  buildResetOutcomeText,
} from "@/features/admin-accounts/model/account-form-text";
import {
  type AccountNotice,
  toResetFailureNotice,
} from "@/features/admin-accounts/model/account-notice";
import {
  parsePasswordReset,
  type PasswordResetFields,
} from "@/features/admin-accounts/model/password-reset";
import { buildSuggestedPassword } from "@/features/admin-accounts/model/suggested-password";
import {
  describeFailure,
  FailureBanner,
  getRequestFailure,
  type RequestFailure,
  useFormIdempotencyKey,
} from "@/features/backend-requests";

const PASSWORD_ID = "reset-password-password";

const SIGN_OUT_EVERYWHERE_ID = "reset-password-sign-out-everywhere";

/** Props of {@link ResetPasswordDialog}. */
export type ResetPasswordDialogProps = {
  /** A `staff` or `manager` account, active or deactivated. */
  readonly account: Account;
  readonly returnFocus: DialogReturnFocus;
  /** Closes the dialog with what the page says. */
  readonly onNotice: (notice: AccountNotice) => void;
  readonly onCancel: () => void;
};

/** Props of {@link ResetFailureBanner}. */
type ResetFailureBannerProps = {
  readonly account: Account;
  readonly failure: RequestFailure;
};

/**
 * Render the reset dialog.
 *
 * @param props - The account, the focus target, and the handlers of an outcome and of Cancel.
 * @returns The dialog.
 */
export function ResetPasswordDialog({
  account,
  returnFocus,
  onNotice,
  onCancel,
}: ResetPasswordDialogProps) {
  const resetPassword = useResetPassword();
  const formKey = useFormIdempotencyKey();
  const randomBytes = useRandomBytes();
  const [fields, setFields] = useState<PasswordResetFields>(() => ({
    password: buildSuggestedPassword(randomBytes),
    isSignedOutEverywhere: true,
  }));
  const [passwordError, setPasswordError] = useState<string | undefined>(undefined);
  const failure = getRequestFailure(resetPassword.error);
  const text = buildResetDialogText(account);

  const updateFields = (changed: Partial<PasswordResetFields>) => {
    formKey.forgetKey();
    setFields((current) => ({ ...current, ...changed }));
  };

  const handleSubmit = () => {
    const check = parsePasswordReset(fields);
    setPasswordError(check.kind === "invalid" ? check.passwordError : undefined);
    if (check.kind === "invalid") {
      return;
    }
    const { isSignedOutEverywhere } = check.reset;
    resetPassword.mutate(
      { ...check.reset, accountId: account.accountId, idempotencyKey: formKey.getOrCreateKey() },
      {
        onSuccess: () => {
          onNotice({ kind: "password_reset", account, isSignedOutEverywhere });
        },
        onError: (error) => {
          const refusal = getRequestFailure(error);
          const notice = refusal === undefined ? undefined : toResetFailureNotice(account, refusal);
          if (notice !== undefined) {
            onNotice(notice);
          }
        },
      },
    );
  };

  return (
    <FormDialog
      text={{
        title: text.title,
        description: text.description,
        submitLabel: accountFormText.resetLabel,
      }}
      returnFocus={returnFocus}
      tone="danger"
      isPending={resetPassword.isPending}
      onSubmit={handleSubmit}
      onCancel={onCancel}
    >
      <SuggestedPasswordField
        inputId={PASSWORD_ID}
        password={fields.password}
        hint={text.passwordHint}
        error={passwordError}
        onChange={(password) => {
          updateFields({ password });
        }}
      />
      <Checkbox
        id={SIGN_OUT_EVERYWHERE_ID}
        label={text.signOutEverywhere}
        hint={accountFormText.resetSessionsHint}
        isChecked={fields.isSignedOutEverywhere}
        onCheckedChange={(isSignedOutEverywhere) => {
          updateFields({ isSignedOutEverywhere });
        }}
      />
      {failure === undefined ? null : <ResetFailureBanner account={account} failure={failure} />}
    </FormDialog>
  );
}

/**
 * Render the banner of a failed reset that keeps the dialog open: an unknown outcome, or a
 * technical failure. The other failures close the dialog.
 *
 * @param props - The account and the failure of the reset.
 * @returns The banner, or nothing.
 */
function ResetFailureBanner({ account, failure }: ResetFailureBannerProps) {
  const kind = classifyResetFailure(failure);
  if (kind === "technical") {
    return (
      <FailureBanner lead={buildResetOutcomeText(account.displayName).notReset} failure={failure} />
    );
  }
  if (kind !== "outcome_unknown") {
    return null;
  }
  const { traceId } = describeFailure(failure);
  return (
    <StatusBanner
      tone="danger"
      lead={accountFormText.passwordMayHaveBeenReset}
      {...(traceId === undefined ? {} : { traceId })}
    >
      {accountFormText.resetAgain}
    </StatusBanner>
  );
}
