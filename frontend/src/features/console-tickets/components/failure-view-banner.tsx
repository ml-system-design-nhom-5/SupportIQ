/**
 * The banner of a failed console action (UI-25; console UI design, Errors and guardrails): what
 * happened, what to do next, and the copyable trace ID.
 */
import { StatusBanner } from "@/design-system";
import type { FailureView } from "@/features/console-tickets/model/failure-view";

/** Props of {@link FailureViewBanner}. */
type FailureViewBannerProps = {
  readonly failure: FailureView;
};

/**
 * Render the banner.
 *
 * @param props - The failed action in plain language.
 * @returns The banner, announced as an alert.
 */
export function FailureViewBanner({ failure }: FailureViewBannerProps) {
  return (
    <StatusBanner
      tone="danger"
      lead={failure.lead}
      {...(failure.traceId === undefined ? {} : { traceId: failure.traceId })}
    >
      {failure.message}
    </StatusBanner>
  );
}
