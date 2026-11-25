/**
 * The password field of the create and reset dialogs (account management design, Suggested
 * passwords): a password input filled with a suggested password, Copy password next to it, and a
 * hint. Copy password announces its outcome, as the trace ID does (UI-25). It puts the password on
 * the admin's clipboard, which the browser does not clear (account management design, Security and
 * privacy).
 */
import { Copy } from "lucide-react";

import {
  Button,
  type CopyOutcome,
  FormField,
  getFieldDescriptionId,
  PasswordInput,
  Stack,
  Text,
  useCopyToClipboard,
} from "@/design-system";
import { accountFormText } from "@/features/admin-accounts/model/account-form-text";

const textByCopyOutcome: Readonly<Record<CopyOutcome, string>> = {
  idle: "",
  copied: accountFormText.passwordCopied,
  failed: accountFormText.passwordNotCopied,
};

/** Props of {@link SuggestedPasswordField}. */
export type SuggestedPasswordFieldProps = {
  readonly inputId: string;
  readonly password: string;
  readonly hint: string;
  readonly error: string | undefined;
  readonly onChange: (password: string) => void;
};

/**
 * Render the password field with Copy password.
 *
 * @param props - The input's `id`, the password, the hint, the error, and the change handler.
 * @returns The field.
 */
export function SuggestedPasswordField({
  inputId,
  password,
  hint,
  error,
  onChange,
}: SuggestedPasswordFieldProps) {
  const { copyOutcome, copy } = useCopyToClipboard();
  return (
    <FormField inputId={inputId} label={accountFormText.passwordLabel} hint={hint} error={error}>
      <Stack direction="row" gap="2" align="center">
        <PasswordInput
          id={inputId}
          autoComplete="new-password"
          value={password}
          aria-invalid={error !== undefined}
          aria-describedby={getFieldDescriptionId({ inputId, hint, error })}
          onChange={(event) => {
            onChange(event.target.value);
          }}
        />
        <Button
          leadingIcon={Copy}
          onClick={() => {
            void copy(password);
          }}
        >
          {accountFormText.copyPassword}
        </Button>
      </Stack>
      <p role="status">
        <Text size="xs" tone="muted">
          {textByCopyOutcome[copyOutcome]}
        </Text>
      </p>
    </FormField>
  );
}
