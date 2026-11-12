/**
 * A panel that opens from a button and holds content with its own controls, on Radix Popover
 * (UI-31; console UI design, Order chip). Radix moves the focus into the panel, closes it on Escape
 * or a click outside, and returns the focus to the button. The caller controls whether it is open,
 * so another control, such as an order citation marker, can open it as well.
 */
import * as PopoverPrimitive from "@radix-ui/react-popover";
import { cva } from "class-variance-authority";
import type { ReactElement, ReactNode } from "react";

const contentVariants = cva(
  "z-20 flex flex-col overflow-hidden rounded-lg border border-border bg-surface-raised text-sm text-text shadow-md",
  { variants: { width: { narrow: "w-popover", wide: "w-popover-wide" } } },
);

/** `narrow` holds one record; `wide` holds a list next to a preview. */
export type PopoverWidth = "narrow" | "wide";

/** Props of {@link Popover}. */
export type PopoverProps = {
  /** The button that opens the popover: an element that takes a ref, such as a `button`. */
  readonly trigger: ReactElement;
  /** The accessible name of the popover. */
  readonly label: string;
  readonly isOpen: boolean;
  readonly onOpenChange: (isOpen: boolean) => void;
  readonly width?: PopoverWidth;
  readonly children: ReactNode;
};

/**
 * Render the button and, while open, the popover.
 *
 * @param props - The button, the name, the open state and its handler, the width, and the content.
 * @returns The button; the popover opens in a portal.
 */
export function Popover({
  trigger,
  label,
  isOpen,
  onOpenChange,
  width = "narrow",
  children,
}: PopoverProps) {
  return (
    <PopoverPrimitive.Root open={isOpen} onOpenChange={onOpenChange}>
      <PopoverPrimitive.Trigger asChild>{trigger}</PopoverPrimitive.Trigger>
      <PopoverPrimitive.Portal>
        <PopoverPrimitive.Content
          aria-label={label}
          align="start"
          sideOffset={4}
          className={contentVariants({ width })}
        >
          {children}
        </PopoverPrimitive.Content>
      </PopoverPrimitive.Portal>
    </PopoverPrimitive.Root>
  );
}
