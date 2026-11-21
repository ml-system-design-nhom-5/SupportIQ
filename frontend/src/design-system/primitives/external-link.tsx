/**
 * A link that leaves the app, such as a trace in Grafana (UI-35). It opens in a new tab, so the
 * screen stays where it was, without passing the address of the app on (`rel="noreferrer"`). Its
 * name says that it opens a new tab, and a small icon shows it. It has the classes of a
 * {@link TextLink} (CODE-48).
 */
import { ExternalLinkIcon } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/design-system/primitives/class-names";
import { Icon } from "@/design-system/primitives/icon";
import { type TextLinkEmphasis, textLinkVariants } from "@/design-system/primitives/text-link";
import { VisuallyHidden } from "@/design-system/primitives/visually-hidden";

/** Props of {@link ExternalLink}. */
export type ExternalLinkProps = {
  /** The full address outside the app. */
  readonly href: string;
  readonly emphasis?: TextLinkEmphasis;
  /** The label; the name adds "(opens in a new tab)" to it. */
  readonly children: ReactNode;
};

/**
 * Render a link that opens outside the app in a new tab.
 *
 * @param props - The address, the emphasis, and the label.
 * @returns The link.
 */
export function ExternalLink({ href, emphasis = "default", children }: ExternalLinkProps) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className={cn(textLinkVariants({ emphasis }), "inline-flex items-center gap-1")}
    >
      {children} <VisuallyHidden>(opens in a new tab)</VisuallyHidden>
      <Icon icon={ExternalLinkIcon} size="xs" />
    </a>
  );
}
