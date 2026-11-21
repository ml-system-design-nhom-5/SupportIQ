/**
 * A link to another page of the app that looks like a button, such as "Back to My orders".
 */
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router";

import {
  type ButtonSize,
  type ButtonVariant,
  buttonVariants,
  type ButtonWidth,
} from "@/design-system/primitives/button";
import { cn } from "@/design-system/primitives/class-names";
import { FOCUS_RING_CLASSES } from "@/design-system/primitives/focus-ring";
import { Icon } from "@/design-system/primitives/icon";

/** Props of {@link ButtonLink}. */
export type ButtonLinkProps = {
  /** The app path to open. */
  readonly to: string;
  readonly variant?: ButtonVariant;
  readonly size?: ButtonSize;
  readonly width?: ButtonWidth;
  readonly leadingIcon?: LucideIcon;
  readonly children: ReactNode;
};

/**
 * Render a link with the button style.
 *
 * @param props - The target path, the button style, and the label.
 * @returns The link.
 */
export function ButtonLink({
  to,
  variant = "secondary",
  size = "md",
  width = "auto",
  leadingIcon,
  children,
}: ButtonLinkProps) {
  return (
    <Link to={to} className={cn(buttonVariants({ variant, size, width }), FOCUS_RING_CLASSES)}>
      {leadingIcon === undefined ? null : <Icon icon={leadingIcon} />}
      {children}
    </Link>
  );
}
