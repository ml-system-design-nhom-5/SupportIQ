/**
 * The banner of a failed Send reply (UI-25; console UI design, Errors and guardrails): what
 * happened to the reply, what to do next, and the copyable trace ID. The text in the editor stays.
 */
import { StatusBanner } from "@/design-system";
import type { SendFailureView } from "@/features/console-tickets/model/send-failure";

/** Props of {@link SendFailureBanner}. */
type SendFailureBannerProps = {
  readonly failure: SendFailureView;
};

/**
 * Render the banner.
 *
 * @param props - The failed send in plain language.
 * @returns The banner, announced as an alert.
 */
export function SendFailureBanner({ failure }: SendFailureBannerProps) {
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
