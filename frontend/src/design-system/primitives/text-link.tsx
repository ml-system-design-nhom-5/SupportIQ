/**
 * A link to another page of the app, in the `primary` role. {@link textLinkVariants} also styles
 * {@link ExternalLink}.
 */
import { cva } from "class-variance-authority";
import type { ReactNode } from "react";
import { Link } from "react-router";

import { cn } from "@/design-system/primitives/class-names";
import { FOCUS_RING_CLASSES } from "@/design-system/primitives/focus-ring";

/** The classes of a link in text, with the focus ring, shared with the link that leaves the app. */
export const textLinkVariants = cva(
  cn("rounded-sm text-primary hover:underline", FOCUS_RING_CLASSES),
  { variants: { emphasis: { default: "", strong: "font-medium" } } },
);

/** `default` for links in text, `strong` for the name of an item in a list or a card. */
export type TextLinkEmphasis = "default" | "strong";

/** Props of {@link TextLink}. */
export type TextLinkProps = {
  /** The app path to open. */
  readonly to: string;
  readonly emphasis?: TextLinkEmphasis;
  readonly children: ReactNode;
};

/**
 * Render an in-app link.
 *
 * @param props - The target path, the emphasis, and the label.
 * @returns The link.
 */
export function TextLink({ to, emphasis = "default", children }: TextLinkProps) {
  return (
    <Link to={to} className={textLinkVariants({ emphasis })}>
      {children}
    </Link>
  );
}
