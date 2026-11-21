/**
 * The page `/change-password` of every role (account management design, Change password page): a
 * centered panel like `/sign-in`, without the app bar of an area, opened from the account menu.
 * Cancel and Go back open the previous page, or the start of the role's area when there is none.
 * A `401` ends the session, which opens sign-in. The success notice takes the focus (UI-30).
 */
import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router";

import { Button, CenteredPanel, Heading, StatusBanner, Text } from "@/design-system";
import {
  ChangePasswordForm,
  type CompletedPasswordChange,
} from "@/features/session/components/change-password-form";
import { RequireSession } from "@/features/session/components/require-session";
import { passwordChangeText } from "@/features/session/model/password-change";
import type { Session } from "@/features/session/model/session";
import { getAreaStartPath } from "@/features/session/model/sign-in-paths";

/** React Router gives this key to the first location of a history, which has no previous page. */
const INITIAL_LOCATION_KEY = "default";

/** The element ID of the success notice, which gets the focus when it replaces the form. */
const PASSWORD_CHANGED_ID = "change-password-changed";

/** Props of {@link ChangePasswordScreen}. */
type ChangePasswordScreenProps = {
  readonly session: Session;
};

/** Props of {@link PasswordChanged}. */
type PasswordChangedProps = {
  readonly change: CompletedPasswordChange;
  readonly onGoBack: () => void;
};

/**
 * Render the page for the signed-in account.
 *
 * @returns The page, or the session's loading, error, or sign-in redirect.
 */
export function ChangePasswordPage() {
  return <RequireSession>{(session) => <ChangePasswordScreen session={session} />}</RequireSession>;
}

/**
 * Render the form, then the success state. The form unmounts on success, so its passwords and its
 * write are gone (account management design, Shared behavior).
 *
 * @param props - The signed-in account.
 * @returns The panel with the form or the success state.
 */
function ChangePasswordScreen({ session }: ChangePasswordScreenProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const [completedChange, setCompletedChange] = useState<CompletedPasswordChange | null>(null);

  const leave = () => {
    if (location.key === INITIAL_LOCATION_KEY) {
      void navigate(getAreaStartPath(session.role), { replace: true });
      return;
    }
    void navigate(-1);
  };

  return (
    <CenteredPanel>
      <title>Change password · SupportIQ</title>
      <Text size="lg">SupportIQ</Text>
      <Heading level={1} size="section">
        Change password
      </Heading>
      {completedChange === null ? (
        <ChangePasswordForm onChanged={setCompletedChange} onCancel={leave} />
      ) : (
        <PasswordChanged change={completedChange} onGoBack={leave} />
      )}
    </CenteredPanel>
  );
}

/**
 * Render the success state.
 *
 * @param props - The completed change and the handler of Go back.
 * @returns The confirmation and Go back.
 */
function PasswordChanged({ change, onGoBack }: PasswordChangedProps) {
  useFocusPasswordChanged();
  return (
    <>
      <StatusBanner
        tone="success"
        lead={passwordChangeText.changed}
        focusTargetId={PASSWORD_CHANGED_ID}
      >
        {change.isSignedOutElsewhere ? passwordChangeText.otherSessionsSignedOut : null}
      </StatusBanner>
      <Button variant="primary" onClick={onGoBack}>
        Go back
      </Button>
    </>
  );
}

/**
 * Move the focus to the success notice once it is shown. The form, whose Change password held the
 * focus, unmounts on success, so the focus would otherwise fall to the page (UI-30).
 */
function useFocusPasswordChanged(): void {
  useEffect(() => {
    document.getElementById(PASSWORD_CHANGED_ID)?.focus();
  }, []);
}
