/**
 * The Sign in screen (`/sign-in`): sends the credentials, then opens the page to return to, or the
 * area of the role (contract, `getCurrentSession`). It never reads the session, so a missing
 * session can never send it back to itself.
 */
import { useNavigate, useSearchParams } from "react-router";

import { getRequestFailure } from "@/features/backend-requests";
import { type SignInCredentials, useSignIn } from "@/features/session/api/use-sign-in";
import { type SignInFailure, SignInForm } from "@/features/session/components/sign-in-form";
import { InvalidCredentialsError } from "@/features/session/model/invalid-credentials-error";
import {
  resolvePathAfterSignIn,
  RETURN_TO_PARAMETER,
} from "@/features/session/model/sign-in-paths";

/**
 * Render the Sign in screen.
 *
 * @returns The sign-in form.
 */
export function SignInPage() {
  const signIn = useSignIn();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const failure = toSignInFailure(signIn.error);

  const handleSubmit = (credentials: SignInCredentials) => {
    signIn.mutate(credentials, {
      onSuccess: (session) => {
        const returnTo = searchParams.get(RETURN_TO_PARAMETER);
        void navigate(resolvePathAfterSignIn(session.role, returnTo), { replace: true });
      },
    });
  };

  return (
    <SignInForm
      isPending={signIn.isPending}
      {...(failure === undefined ? {} : { failure })}
      onSubmit={handleSubmit}
    />
  );
}

/**
 * Turn the error of the sign-in mutation into the state of the form.
 *
 * @param error - The error of the last attempt, or null.
 * @returns The failure to show, or undefined.
 * @throws The error itself when it is neither a refusal nor a request failure: a defect, which
 *   the route error boundary shows.
 */
function toSignInFailure(error: Error | null): SignInFailure | undefined {
  if (error === null) {
    return undefined;
  }
  if (error instanceof InvalidCredentialsError) {
    return { kind: "invalid_credentials" };
  }
  const failure = getRequestFailure(error);
  if (failure === undefined) {
    throw error;
  }
  return { kind: "request_failure", failure };
}
