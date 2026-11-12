/**
 * The account menu of the signed-in account in the app bar of every area (account management
 * design, Account menu): Change password opens `/change-password`, and Sign out ends the session.
 * Sign out is never retried automatically (TS-29); when it fails, the message stays next to the
 * menu.
 */
import { useNavigate } from "react-router";

import { AccountMenu, type AccountMenuVariant } from "@/design-system";
import { useSignOut } from "@/features/session/api/use-sign-out";
import { SignOutFailure } from "@/features/session/components/sign-out-failure";
import { CHANGE_PASSWORD_PATH } from "@/features/session/model/password-change";
import { getRoleLabel, type Session } from "@/features/session/model/session";

/** Props of {@link SessionAccountMenu}. */
export type SessionAccountMenuProps = {
  readonly session: Session;
  /** `shop` shows only the icon at phone width. */
  readonly variant: AccountMenuVariant;
};

/**
 * Render the account menu of the session.
 *
 * @param props - The signed-in account and the variant of the area.
 * @returns The sign-out failure, when there is one, and the menu.
 */
export function SessionAccountMenu({ session, variant }: SessionAccountMenuProps) {
  const signOut = useSignOut();
  const navigate = useNavigate();
  return (
    <>
      {signOut.error === null ? null : <SignOutFailure error={signOut.error} />}
      <AccountMenu
        variant={variant}
        displayName={session.displayName}
        roleLabel={getRoleLabel(session.role)}
        isSigningOut={signOut.isPending}
        onChangePassword={() => {
          void navigate(CHANGE_PASSWORD_PATH);
        }}
        onSignOut={() => {
          signOut.mutate();
        }}
      />
    </>
  );
}
