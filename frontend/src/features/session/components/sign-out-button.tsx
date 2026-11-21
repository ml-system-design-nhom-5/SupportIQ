/**
 * Sign out from a state message, such as permission denied; the app bar has it in the account menu.
 * While the request is sent the button ignores activation, so it is sent once; it is never retried
 * automatically (TS-29).
 */
import { LogOut } from "lucide-react";

import { Button } from "@/design-system";
import { useSignOut } from "@/features/session/api/use-sign-out";
import { SignOutFailure } from "@/features/session/components/sign-out-failure";

/**
 * Render Sign out. When it fails, the person is told that they are still signed in, or, after an
 * unknown outcome, that sign-out could not be confirmed.
 *
 * @returns The button, and the failure message when sign-out failed.
 */
export function SignOutButton() {
  const signOut = useSignOut();
  return (
    <>
      <Button
        variant="secondary"
        size="lg"
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
