/**
 * Content in the middle of the space next to the inbox, such as the prompt to select a ticket or
 * the error state of a ticket (console UI design, no-ticket-selected.png and state-error.png).
 */
import type { ReactNode } from "react";

/** Props of {@link CenteredContent}. */
export type CenteredContentProps = {
  readonly children: ReactNode;
};

/**
 * Render the content in the middle.
 *
 * @param props - The content, such as a state message.
 * @returns The centered content, at most the width of a dialog.
 */
export function CenteredContent({ children }: CenteredContentProps) {
  return (
    <div className="flex min-h-0 flex-1 items-center justify-center overflow-y-auto p-6">
      <div className="flex w-full max-w-dialog flex-col">{children}</div>
    </div>
  );
}
