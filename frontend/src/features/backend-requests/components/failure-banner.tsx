/**
 * The banner of a write that failed (UI-25): what did not happen, why in plain language, and the
 * copyable trace ID when there is one. The text that the person typed stays where it was.
 */
import type { ReactNode } from "react";

import { StatusBanner } from "@/design-system";
import { describeFailure } from "@/features/backend-requests/model/describe-failure";
import type { RequestFailure } from "@/features/backend-requests/model/request-failure";

/** Props of {@link FailureBanner}. */
export type FailureBannerProps = {
  /** What did not happen, for example "Your message was not sent." */
  readonly lead: string;
  readonly failure: RequestFailure;
  readonly action?: ReactNode;
  /** The sentence for a `404`, when the screen knows what was not found. */
  readonly notFoundMessage?: string;
};

/**
 * Render the failure banner.
 *
 * @param props - The lead, the failure, an optional action, and an optional `404` sentence.
 * @returns The banner, announced as an alert.
 */
export function FailureBanner({ lead, failure, action, notFoundMessage }: FailureBannerProps) {
  const description = describeFailure(failure);
  const isNotFound = description.category === "not_found";
  return (
    <StatusBanner
      tone="danger"
      lead={lead}
      {...(description.traceId === undefined ? {} : { traceId: description.traceId })}
      {...(action === undefined ? {} : { action })}
    >
      {isNotFound ? (notFoundMessage ?? description.message) : description.message}
    </StatusBanner>
  );
}
