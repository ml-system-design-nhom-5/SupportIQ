/**
 * A short label that is not a status, such as "AI suggestion", "Predicted", or "This ticket", in a
 * badge of its tone. A label of AI content uses the `ai` tone (UI-13); a status uses
 * {@link StatusBadge} with its one presentation (UI-12).
 */
import type { LucideIcon } from "lucide-react";

import { badgeVariants } from "@/design-system/components/badge-tones";
import type { StatusTone } from "@/design-system/components/status-presentations";
import { Icon } from "@/design-system/primitives/icon";

/** Props of {@link Tag}. */
export type TagProps = {
  readonly tone: StatusTone;
  readonly icon?: LucideIcon;
  readonly children: string;
};

/**
 * Render a tag.
 *
 * @param props - The tone, an optional icon, and the label.
 * @returns The tag.
 */
export function Tag({ tone, icon, children }: TagProps) {
  return (
    <span className={badgeVariants({ tone })}>
      {icon === undefined ? null : <Icon icon={icon} />}
      {children}
    </span>
  );
}
