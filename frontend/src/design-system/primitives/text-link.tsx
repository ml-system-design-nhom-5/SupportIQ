/**
 * A link to another page of the app, in the `primary` role.
 */
import { cva } from "class-variance-authority";
import type { ReactNode } from "react";
import { Link } from "react-router";

import { cn } from "@/design-system/primitives/class-names";
import { FOCUS_RING_CLASSES } from "@/design-system/primitives/focus-ring";

const textLinkVariants = cva("rounded-sm text-primary hover:underline", {
  variants: { emphasis: { default: "", strong: "font-medium" } },
});

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
    <Link to={to} className={cn(textLinkVariants({ emphasis }), FOCUS_RING_CLASSES)}>
      {children}
    </Link>
  );
}
