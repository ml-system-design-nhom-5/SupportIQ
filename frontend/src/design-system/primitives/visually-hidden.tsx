/**
 * Text for assistive technology only, such as a label that the layout already shows visually.
 */
import type { ReactNode } from "react";

/** Props of {@link VisuallyHidden}. */
export type VisuallyHiddenProps = {
  readonly children: ReactNode;
};

/**
 * Render text that screen readers read and the screen does not show.
 *
 * @param props - The text.
 * @returns A visually hidden span.
 */
export function VisuallyHidden({ children }: VisuallyHiddenProps) {
  return <span className="sr-only">{children}</span>;
}
