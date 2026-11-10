/**
 * A status badge: icon and label on the tinted background of its tone (UI-11, UI-12).
 */
import { cva } from "class-variance-authority";

import type { StatusPresentation } from "@/design-system/components/status-presentations";
import { Icon } from "@/design-system/primitives/icon";

const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-full border px-2 py-0 text-sm font-medium whitespace-nowrap",
  {
    variants: {
      tone: {
        neutral: "border-border bg-background text-text-muted",
        info: "border-info/35 bg-info-subtle text-info",
        success: "border-success/35 bg-success-subtle text-success",
        warning: "border-warning/35 bg-warning-subtle text-warning",
        danger: "border-danger/35 bg-danger-subtle text-danger",
        ai: "border-ai/35 bg-ai-subtle text-ai",
      },
    },
  },
);

/** Props of {@link StatusBadge}. */
export type StatusBadgeProps = {
  /** One of the presentations in `status-presentations.ts`. */
  readonly presentation: StatusPresentation;
};

/**
 * Render a status badge.
 *
 * @param props - The presentation of the status.
 * @returns The badge.
 */
export function StatusBadge({ presentation }: StatusBadgeProps) {
  return (
    <span className={badgeVariants({ tone: presentation.tone })}>
      <Icon icon={presentation.icon} />
      {presentation.label}
    </span>
  );
}
