/**
 * The message of a sign-out that failed, under Sign out or next to the account menu, with the
 * copyable trace ID when there is one (UI-25). After a timeout or a lost connection, sign-out may
 * have worked, and trying again is safe: `401` counts as signed out.
 */
import { TriangleAlert } from "lucide-react";

import { InlineMessage, Stack, TraceId } from "@/design-system";
import {
  describeFailure,
  getRequestFailure,
  isWriteOutcomeUnknown,
} from "@/features/backend-requests";

/** Props of {@link SignOutFailure}. */
export type SignOutFailureProps = {
  /** The error of the sign-out. */
  readonly error: Error;
};

/**
 * Say that sign-out failed: the person is still signed in, or, after an unknown outcome, sign-out
 * could not be confirmed.
 *
 * @param props - The error of the sign-out.
 * @returns The message.
 */
export function SignOutFailure({ error }: SignOutFailureProps) {
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
