/**
 * The Sign in form of the console UI design, shared by every role: a login name with a hint, a
 * password, and Sign in. No list of accounts is shown. A refused sign-in shows the same message
 * for an unknown name, a wrong password, and a deactivated account (ADR-0009, statement 8).
 */
import { TriangleAlert } from "lucide-react";
import { type SubmitEvent, useState } from "react";

import {
  Button,
  CenteredPanel,
  FormField,
  Heading,
  InlineMessage,
  Stack,
  Text,
  TextInput,
} from "@/design-system";
import { FailureBanner, type RequestFailure } from "@/features/backend-requests";
import type { SignInCredentials } from "@/features/session/api/use-sign-in";

const LOGIN_NAME_ID = "sign-in-login-name";

const PASSWORD_ID = "sign-in-password";

const ERROR_ID = "sign-in-error";

/** Why the last sign-in did not succeed. */
export type SignInFailure =
  | { readonly kind: "invalid_credentials" }
  | { readonly kind: "request_failure"; readonly failure: RequestFailure };

/** Props of {@link SignInForm}. */
export type SignInFormProps = {
  /** True while the credentials are sent; Sign in ignores activation, so they are sent once. */
  readonly isPending: boolean;
  readonly failure?: SignInFailure;
  readonly onSubmit: (credentials: SignInCredentials) => void;
};

/**
 * Render the sign-in form. The typed values stay after a failed attempt.
 *
 * @param props - The pending state, the last failure, and the submit handler.
 * @returns The form in the centered panel.
 */
export function SignInForm({ isPending, failure, onSubmit }: SignInFormProps) {
  const [loginName, setLoginName] = useState("");
  const [password, setPassword] = useState("");
  const isRefused = failure?.kind === "invalid_credentials";

  const handleSubmit = (event: SubmitEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!isPending) {
      onSubmit({ loginName, password });
    }
  };

  return (
    <CenteredPanel>
      <title>Sign in · SupportIQ</title>
      <Heading level={1} size="section">
        SupportIQ{" "}
        <Text tone="muted" size="lg">
          Console
        </Text>
      </Heading>
      <form aria-label="Sign in" onSubmit={handleSubmit}>
        <Stack gap="4">
          <FormField inputId={LOGIN_NAME_ID} label="Login name">
            <TextInput
              id={LOGIN_NAME_ID}
              name="login_name"
              autoComplete="username"
              placeholder="staff-1"
              required
              value={loginName}
              aria-invalid={isRefused}
              aria-describedby={isRefused ? ERROR_ID : undefined}
              onChange={(event) => {
                setLoginName(event.target.value);
              }}
            />
          </FormField>
          <FormField inputId={PASSWORD_ID} label="Password">
            <TextInput
              id={PASSWORD_ID}
              name="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              aria-invalid={isRefused}
              aria-describedby={isRefused ? ERROR_ID : undefined}
              onChange={(event) => {
                setPassword(event.target.value);
              }}
            />
          </FormField>
          {isRefused ? (
            <InlineMessage tone="danger" icon={TriangleAlert} role="alert" id={ERROR_ID}>
              The login name or the password is not correct.
            </InlineMessage>
          ) : null}
          {failure?.kind === "request_failure" ? (
            <FailureBanner lead="You were not signed in." failure={failure.failure} />
          ) : null}
          <Button type="submit" variant="primary" width="full" isPending={isPending}>
            {isPending ? "Signing in…" : "Sign in"}
          </Button>
        </Stack>
      </form>
    </CenteredPanel>
  );
}
