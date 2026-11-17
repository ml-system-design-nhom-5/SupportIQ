/**
 * A status badge: icon and label on the tinted background of its tone (UI-11, UI-12).
 */
import { badgeVariants } from "@/design-system/components/badge-tones";
import type { StatusPresentation } from "@/design-system/components/status-presentations";
import { Icon } from "@/design-system/primitives/icon";

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
