/**
 * The create dialog of the Accounts screen (account management design, Create account dialog): the
 * role, the number of the login name, the display name, and a suggested password. The
 * `Idempotency-Key` stays until a field changes, so sending the same fields again after an unknown
 * outcome is safe (account management design, Shared behavior). The dialog unmounts when it
 * closes, so its password and its write are gone.
 */
import { useState } from "react";

import {
  type DialogReturnFocus,
  FormDialog,
  FormField,
  getFieldDescriptionId,
  presentationByInternalRole,
  RadioGroup,
  type RadioOption,
  StatusBanner,
  TextInput,
} from "@/design-system";
import { useRandomBytes } from "@/features/admin-accounts/api/random-bytes";
import { useCreateAccount } from "@/features/admin-accounts/api/use-create-account";
import { SuggestedPasswordField } from "@/features/admin-accounts/components/suggested-password-field";
import {
  type AccountCreationFieldErrors,
  type AccountCreationFields,
  type AssignableRole,
  buildLoginNamePrefix,
  findTakenLoginName,
  parseAccountCreation,
} from "@/features/admin-accounts/model/account-creation";
import { classifyCreationFailure } from "@/features/admin-accounts/model/account-form-failure";
import {
  accountFormText,
  buildLoginNameTakenText,
} from "@/features/admin-accounts/model/account-form-text";
import type { AccountNotice } from "@/features/admin-accounts/model/account-notice";
import { buildSuggestedPassword } from "@/features/admin-accounts/model/suggested-password";
import {
  assertNever,
  describeFailure,
  FailureBanner,
  getRequestFailure,
  type RequestFailure,
  useFormIdempotencyKey,
} from "@/features/backend-requests";

const ROLE_NAME = "create-account-role";

const LOGIN_NUMBER_ID = "create-account-login-number";

const DISPLAY_NAME_ID = "create-account-display-name";

const PASSWORD_ID = "create-account-password";

/** The roles of a new account: Staff is selected first. */
const roleOptions: readonly RadioOption<AssignableRole>[] = [
  { value: "staff", label: presentationByInternalRole.staff.label },
  { value: "manager", label: presentationByInternalRole.manager.label },
];

/** Props of {@link CreateAccountDialog}. */
export type CreateAccountDialogProps = {
  readonly returnFocus: DialogReturnFocus;
  /** Closes the dialog with what the page says: the new account, or permission denied. */
  readonly onNotice: (notice: AccountNotice) => void;
  readonly onCancel: () => void;
};

/**
 * Render the create dialog.
 *
 * @param props - The focus target and the handlers of an outcome and of Cancel.
 * @returns The dialog.
 */
export function CreateAccountDialog({ returnFocus, onNotice, onCancel }: CreateAccountDialogProps) {
  const createAccount = useCreateAccount();
  const formKey = useFormIdempotencyKey();
  const randomBytes = useRandomBytes();
  const [fields, setFields] = useState<AccountCreationFields>(() => ({
    role: "staff",
    loginNumber: "",
    displayName: "",
    password: buildSuggestedPassword(randomBytes),
  }));
  const [fieldErrors, setFieldErrors] = useState<AccountCreationFieldErrors>({});
  const failure = getRequestFailure(createAccount.error);
  const takenLoginName = findTakenLoginName(failure, createAccount.variables);

  const updateFields = (changed: Partial<AccountCreationFields>) => {
    formKey.forgetKey();
    setFields((current) => ({ ...current, ...changed }));
  };

  const handleSubmit = () => {
    const check = parseAccountCreation(fields);
    setFieldErrors(check.kind === "invalid" ? check.errors : {});
    if (check.kind === "invalid") {
      return;
    }
    createAccount.mutate(
      { ...check.creation, idempotencyKey: formKey.getOrCreateKey() },
      {
        onSuccess: (account) => {
          onNotice({ kind: "created", account });
        },
        onError: (error) => {
          const refusal = getRequestFailure(error);
          if (refusal !== undefined && classifyCreationFailure(refusal) === "permission_denied") {
            onNotice({ kind: "permission_denied", failure: refusal });
          }
        },
      },
    );
  };

  const loginNumberError =
    fieldErrors.loginNumber ??
    (takenLoginName === undefined ? undefined : buildLoginNameTakenText(takenLoginName));
  return (
    <FormDialog
      text={{ title: accountFormText.createTitle, submitLabel: accountFormText.createLabel }}
      returnFocus={returnFocus}
      isPending={createAccount.isPending}
      onSubmit={handleSubmit}
      onCancel={onCancel}
    >
      <RadioGroup
        name={ROLE_NAME}
        legend={accountFormText.roleLegend}
        options={roleOptions}
        value={fields.role}
        onValueChange={(role) => {
          updateFields({ role });
        }}
      />
      <FormField
        inputId={LOGIN_NUMBER_ID}
        label={accountFormText.loginNameLabel}
        hint={accountFormText.loginNumberHint}
        error={loginNumberError}
      >
        <TextInput
          id={LOGIN_NUMBER_ID}
          leadingText={buildLoginNamePrefix(fields.role)}
          inputMode="numeric"
          autoComplete="off"
          placeholder={accountFormText.loginNumberPlaceholder}
          value={fields.loginNumber}
          aria-invalid={loginNumberError !== undefined}
          aria-describedby={getFieldDescriptionId({
            inputId: LOGIN_NUMBER_ID,
            hint: accountFormText.loginNumberHint,
            error: loginNumberError,
          })}
          onChange={(event) => {
            updateFields({ loginNumber: event.target.value });
          }}
        />
      </FormField>
      <FormField
        inputId={DISPLAY_NAME_ID}
        label={accountFormText.displayNameLabel}
        hint={accountFormText.displayNameHint}
        error={fieldErrors.displayName}
      >
        <TextInput
          id={DISPLAY_NAME_ID}
          autoComplete="off"
          value={fields.displayName}
          aria-invalid={fieldErrors.displayName !== undefined}
          aria-describedby={getFieldDescriptionId({
            inputId: DISPLAY_NAME_ID,
            hint: accountFormText.displayNameHint,
            error: fieldErrors.displayName,
          })}
          onChange={(event) => {
            updateFields({ displayName: event.target.value });
          }}
        />
      </FormField>
      <SuggestedPasswordField
        inputId={PASSWORD_ID}
        password={fields.password}
        hint={accountFormText.createPasswordHint}
        error={fieldErrors.password}
        onChange={(password) => {
          updateFields({ password });
        }}
      />
      {failure === undefined || takenLoginName !== undefined ? null : (
        <CreationFailureBanner failure={failure} />
      )}
    </FormDialog>
  );
}

/**
 * Render the banner of a failed creation in the dialog.
 *
 * @param props - The failure of the creation.
 * @returns The banner, or nothing when the page shows the permission-denied state.
 */
function CreationFailureBanner({ failure }: { readonly failure: RequestFailure }) {
  const { traceId } = describeFailure(failure);
  const traceIdProps = traceId === undefined ? {} : { traceId };
  const kind = classifyCreationFailure(failure);
  switch (kind) {
    case "refused":
      return (
        <StatusBanner tone="danger" lead={accountFormText.accountNotCreated} {...traceIdProps}>
          {accountFormText.checkFields}
        </StatusBanner>
      );
    case "outcome_unknown":
      return (
        <StatusBanner
          tone="danger"
          lead={accountFormText.accountMayHaveBeenCreated}
          {...traceIdProps}
        >
          {accountFormText.createAgain}
        </StatusBanner>
      );
    case "permission_denied":
      return null;
    case "login_name_taken":
    case "technical":
      return <FailureBanner lead={accountFormText.accountNotCreated} failure={failure} />;
    default:
      assertNever(kind);
  }
}
