/**
 * Sign out, from the app bar or from a permission-denied state. While the request is sent the
 * button ignores activation, so it is sent once; it is never retried automatically (TS-29).
 */
import { LogOut, TriangleAlert } from "lucide-react";

import { Button, InlineMessage, Stack, TraceId } from "@/design-system";
import {
  describeFailure,
  getRequestFailure,
  isWriteOutcomeUnknown,
} from "@/features/backend-requests";
import { useSignOut } from "@/features/session/api/use-sign-out";

/** `app-bar` is the quiet button of the app bar; `state` is a button of a state message. */
export type SignOutButtonPlacement = "app-bar" | "state";

/** Props of {@link SignOutButton}. */
export type SignOutButtonProps = {
  readonly placement: SignOutButtonPlacement;
};

/**
 * Render Sign out. When it fails, the person is told that they are still signed in, or, after an
 * unknown outcome, that sign-out could not be confirmed.
 *
 * @param props - Where the button sits.
 * @returns The button, and the failure message when sign-out failed.
 */
export function SignOutButton({ placement }: SignOutButtonProps) {
  const signOut = useSignOut();
  return (
    <>
      <Button
        variant={placement === "app-bar" ? "ghost" : "secondary"}
        size={placement === "app-bar" ? "sm" : "lg"}
        leadingIcon={LogOut}
        isPending={signOut.isPending}
        onClick={() => {
          signOut.mutate();
        }}
      >
        {signOut.isPending ? "Signing out…" : "Sign out"}
      </Button>
      {signOut.error === null ? null : <SignOutFailure error={signOut.error} />}
    </>
  );
}

/**
 * Say that sign-out failed, with the copyable trace ID when there is one (UI-25). After a timeout
 * or a lost connection it may have worked, and trying again is safe: `401` counts as signed out.
 *
 * @param props - The error of the sign-out.
 * @returns The message.
 */
function SignOutFailure({ error }: { readonly error: Error }) {
  const failure = getRequestFailure(error);
  const traceId = failure === undefined ? undefined : describeFailure(failure).traceId;
  const isOutcomeUnknown = failure !== undefined && isWriteOutcomeUnknown(failure);
  return (
    <Stack gap="1">
      <InlineMessage tone="danger" icon={TriangleAlert} role="alert">
        {isOutcomeUnknown
          ? "We could not confirm that you signed out. Try again."
          : "You are still signed in. Try again."}
      </InlineMessage>
      {traceId === undefined ? null : <TraceId traceId={traceId} />}
    </Stack>
  );
}
