/**
 * The button of every screen (shadcn/ui pattern, UI-31). Buttons are verbs that name the result
 * (UI-27). {@link buttonVariants} also styles {@link ButtonLink}.
 */
import { cva } from "class-variance-authority";
import type { LucideIcon } from "lucide-react";
import type { ComponentProps, MouseEvent, ReactNode } from "react";

import { cn } from "@/design-system/primitives/class-names";
import { FOCUS_RING_CLASSES } from "@/design-system/primitives/focus-ring";
import { Icon } from "@/design-system/primitives/icon";

/** The button classes, shared with the link that looks like a button. */
export const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 rounded-md border font-medium whitespace-nowrap transition-colors duration-100 disabled:cursor-not-allowed disabled:opacity-45 aria-disabled:cursor-not-allowed aria-disabled:opacity-45",
  {
    variants: {
      variant: {
        primary: "border-primary bg-primary text-primary-foreground",
        secondary: "border-border-strong bg-surface text-text hover:bg-background",
        danger: "border-danger bg-danger text-text-inverse",
        ghost: "border-transparent bg-transparent text-text-muted hover:bg-background",
      },
      size: {
        sm: "px-2 py-1 text-xs",
        md: "h-8 px-3 text-sm",
        lg: "px-3 py-2 text-base sm:h-8 sm:py-0",
      },
      width: { auto: "", full: "w-full", "full-on-phone": "w-full sm:w-auto" },
    },
  },
);

/** The visual role of a button: one main action per view uses `primary` (UI-06). */
export type ButtonVariant = "primary" | "secondary" | "danger" | "ghost";

/**
 * `sm` is the size inside a table row (12 px text), `md` the console and admin size (14 px text),
 * and `lg` the shop size (16 px text).
 */
export type ButtonSize = "sm" | "md" | "lg";

/** `full-on-phone` fills the width below the `sm` breakpoint, as the shop design shows. */
export type ButtonWidth = "auto" | "full" | "full-on-phone";

/** Props of {@link Button}. */
export type ButtonProps = Omit<ComponentProps<"button">, "className" | "style"> & {
  readonly variant?: ButtonVariant;
  readonly size?: ButtonSize;
  readonly width?: ButtonWidth;
  /** An icon before the label. */
  readonly leadingIcon?: LucideIcon;
  /**
   * True while the action of the button waits for `backend`. It looks and reads as disabled and
   * ignores activation, but it keeps the keyboard focus, which a disabled button drops (UI-30).
   */
  readonly isPending?: boolean;
  readonly children: ReactNode;
};

/**
 * Render a button.
 *
 * @param props - The variant, size, width, icon, pending state, and the native button attributes.
 * @returns The button.
 */
export function Button({
  variant = "secondary",
  size = "md",
  width = "auto",
  leadingIcon,
  isPending = false,
  children,
  type = "button",
  onClick,
  ...buttonAttributes
}: ButtonProps) {
  const handleClick = (event: MouseEvent<HTMLButtonElement>) => {
    if (isPending) {
      // A submit button would otherwise send its form again.
      event.preventDefault();
      return;
    }
    onClick?.(event);
  };

  return (
    <button
      type={type}
      className={cn(buttonVariants({ variant, size, width }), FOCUS_RING_CLASSES)}
      aria-disabled={isPending}
      aria-busy={isPending}
      onClick={handleClick}
      {...buttonAttributes}
    >
      {leadingIcon === undefined ? null : <Icon icon={leadingIcon} />}
      {children}
    </button>
  );
}
