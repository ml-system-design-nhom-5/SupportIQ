/**
 * The form of `/change-password` (account management design, Change password page): the current
 * password, the new password twice, and whether the other sessions end. frontend checks the fields
 * before sending, and the `Idempotency-Key` stays until a field changes, so sending the same fields
 * again after an unknown outcome is safe (account management design, Shared behavior).
 */
import { type Ref, type SubmitEvent, useRef, useState } from "react";

import {
  Button,
  Checkbox,
  FormField,
  getFieldDescriptionId,
  PasswordInput,
  type PasswordInputProps,
  Stack,
} from "@/design-system";
import { getRequestFailure, useFormIdempotencyKey } from "@/features/backend-requests";
import { useChangeOwnPassword } from "@/features/session/api/use-change-own-password";
import { PasswordChangeBanner } from "@/features/session/components/password-change-banner";
import {
  classifyPasswordChangeFailure,
  parsePasswordChange,
  type PasswordChangeFieldErrors,
  type PasswordChangeFields,
  passwordChangeText,
} from "@/features/session/model/password-change";

const CURRENT_PASSWORD_ID = "change-password-current";

const NEW_PASSWORD_ID = "change-password-new";

const CONFIRMATION_ID = "change-password-confirmation";

const SIGN_OUT_ELSEWHERE_ID = "change-password-sign-out-elsewhere";

/** The fields when the page opens: Sign out of my other sessions is checked. */
const initialFields: PasswordChangeFields = {
  currentPassword: "",
  newPassword: "",
  confirmation: "",
  isSignedOutElsewhere: true,
};

/** What the page shows after a successful change. */
export type CompletedPasswordChange = {
  readonly isSignedOutElsewhere: boolean;
};

/** Props of {@link ChangePasswordForm}. */
export type ChangePasswordFormProps = {
  readonly onChanged: (change: CompletedPasswordChange) => void;
  readonly onCancel: () => void;
};

/** Props of {@link PasswordField}. */
type PasswordFieldProps = {
  readonly inputId: string;
  readonly label: string;
  readonly autoComplete: PasswordInputProps["autoComplete"];
  readonly value: string;
  readonly error: string | undefined;
  readonly onChange: (value: string) => void;
  readonly inputRef?: Ref<HTMLInputElement>;
};

/**
 * Render the form.
 *
 * @param props - The handlers of a successful change and of Cancel.
 * @returns The form with its fields, its banner after a failure, and its buttons.
 */
export function ChangePasswordForm({ onChanged, onCancel }: ChangePasswordFormProps) {
  const changePassword = useChangeOwnPassword();
  const formKey = useFormIdempotencyKey();
  const [fields, setFields] = useState(initialFields);
  const [fieldErrors, setFieldErrors] = useState<PasswordChangeFieldErrors>({});
  const currentPasswordRef = useRef<HTMLInputElement>(null);
  const failure = getRequestFailure(changePassword.error);
  const isCurrentPasswordRefused =
    failure !== undefined &&
    classifyPasswordChangeFailure(failure) === "current_password_incorrect";

  const updateFields = (changed: Partial<PasswordChangeFields>) => {
    formKey.forgetKey();
    setFields((current) => ({ ...current, ...changed }));
  };

  const handleSubmit = (event: SubmitEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (changePassword.isPending) {
      return;
    }
    const check = parsePasswordChange(fields);
    setFieldErrors(check.kind === "invalid" ? check.errors : {});
    if (check.kind === "invalid") {
      return;
    }
    changePassword.mutate(
      { ...check.change, idempotencyKey: formKey.getOrCreateKey() },
      {
        onSuccess: () => {
          onChanged({ isSignedOutElsewhere: check.change.isSignedOutElsewhere });
        },
        onError: (error) => {
          const refusal = getRequestFailure(error);
          if (
            refusal !== undefined &&
            classifyPasswordChangeFailure(refusal) === "current_password_incorrect"
          ) {
            updateFields({ currentPassword: "" });
            currentPasswordRef.current?.focus();
          }
        },
      },
    );
  };

  return (
    <form aria-label="Change password" noValidate onSubmit={handleSubmit}>
      <Stack gap="4">
        <PasswordField
          inputId={CURRENT_PASSWORD_ID}
          label="Current password"
          autoComplete="current-password"
          value={fields.currentPassword}
          error={
            fieldErrors.currentPassword ??
            (isCurrentPasswordRefused ? passwordChangeText.currentPasswordIncorrect : undefined)
          }
          inputRef={currentPasswordRef}
          onChange={(currentPassword) => {
            updateFields({ currentPassword });
          }}
        />
        <PasswordField
          inputId={NEW_PASSWORD_ID}
          label="New password"
          autoComplete="new-password"
          value={fields.newPassword}
          error={fieldErrors.newPassword}
          onChange={(newPassword) => {
            updateFields({ newPassword });
          }}
        />
        <PasswordField
          inputId={CONFIRMATION_ID}
          label="Confirm new password"
          autoComplete="new-password"
          value={fields.confirmation}
          error={fieldErrors.confirmation}
          onChange={(confirmation) => {
            updateFields({ confirmation });
          }}
        />
        <Checkbox
          id={SIGN_OUT_ELSEWHERE_ID}
          label="Sign out of my other sessions"
          hint="This browser stays signed in."
          isChecked={fields.isSignedOutElsewhere}
          onCheckedChange={(isSignedOutElsewhere) => {
            updateFields({ isSignedOutElsewhere });
          }}
        />
        {failure === undefined ? null : <PasswordChangeBanner failure={failure} />}
        <Stack direction="row" gap="2" justify="end">
          <Button variant="secondary" disabled={changePassword.isPending} onClick={onCancel}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" isPending={changePassword.isPending}>
            {changePassword.isPending ? "Changing password…" : "Change password"}
          </Button>
        </Stack>
      </Stack>
    </form>
  );
}

/**
 * Render a password field with its label and its error.
 *
 * @param props - The input's `id`, the label, the autocomplete value, the value, the error, the
 *   change handler, and a ref to the input.
 * @returns The field.
 */
function PasswordField({
  inputId,
  label,
  autoComplete,
  value,
  error,
  onChange,
  inputRef,
}: PasswordFieldProps) {
  return (
    <FormField inputId={inputId} label={label} error={error}>
      <PasswordInput
        id={inputId}
        ref={inputRef}
        autoComplete={autoComplete}
        value={value}
        aria-invalid={error !== undefined}
        aria-describedby={getFieldDescriptionId({ inputId, error })}
        onChange={(event) => {
          onChange(event.target.value);
        }}
      />
    </FormField>
  );
}
