/**
 * The error state of a screen or a section that could not load (UI-23, UI-25): what happened,
 * Try again, and the copyable trace ID when there is one.
 */
import { RotateCcw, TriangleAlert } from "lucide-react";

import { Button, type ButtonSize, StateMessage } from "@/design-system";
import { describeFailure } from "@/features/backend-requests/model/describe-failure";
import type { RequestFailure } from "@/features/backend-requests/model/request-failure";

/** Props of {@link FailureState}. */
export type FailureStateProps = {
  /** What could not be loaded, for example "Your orders could not be loaded". */
  readonly title: string;
  readonly failure: RequestFailure;
  /** 1 when the state replaces the whole screen. */
  readonly headingLevel: 1 | 2;
  /** Loads the data again. */
  readonly onRetry: () => void;
  /** True while the data loads again. */
  readonly isRetrying: boolean;
  /** `lg` in the shop. */
  readonly actionSize?: ButtonSize;
};

/**
 * Render the error state.
 *
 * @param props - The title, the failure, the heading level, and the retry handler.
 * @returns The state message.
 */
export function FailureState({
  title,
  failure,
  headingLevel,
  onRetry,
  isRetrying,
  actionSize = "md",
}: FailureStateProps) {
  const description = describeFailure(failure);
  return (
    <StateMessage
      icon={TriangleAlert}
      headingLevel={headingLevel}
      title={title}
      description={description.message}
      {...(description.traceId === undefined ? {} : { traceId: description.traceId })}
      actions={
        <Button leadingIcon={RotateCcw} size={actionSize} isPending={isRetrying} onClick={onRetry}>
          {isRetrying ? "Trying again…" : "Try again"}
        </Button>
      }
    />
  );
}
