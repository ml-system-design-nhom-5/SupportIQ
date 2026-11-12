/**
 * Hints on hover or keyboard focus, on Radix Tooltip (UI-31). {@link TooltipHint} is the one
 * Radix tooltip of the design system: the hover delay, the portal, and the two looks. {@link Tooltip}
 * is the short hint of a text, which activating the trigger, as a tap on a touch screen does, also
 * shows (shop UI design, States).
 */
import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import { cva } from "class-variance-authority";
import { type ReactElement, type ReactNode, useState } from "react";

import { cn } from "@/design-system/primitives/class-names";
import { FOCUS_RING_CLASSES } from "@/design-system/primitives/focus-ring";

/** The hover delay: the base motion duration of UI-09. */
const HOVER_DELAY_MS = 200;

const contentVariants = cva("z-30 shadow-md", {
  variants: {
    variant: {
      label: "rounded-sm bg-text px-2 py-1 text-xs text-text-inverse",
      card: "flex w-hint flex-col overflow-hidden rounded-md border border-border bg-surface-raised text-sm text-text",
    },
  },
});

/** `label` is a short line of text; `card` holds a few facts, such as the source of a citation. */
export type TooltipHintVariant = "label" | "card";

/** Props of {@link TooltipHint}. */
export type TooltipHintProps = {
  readonly variant: TooltipHintVariant;
  readonly isOpen: boolean;
  readonly onOpenChange: (isOpen: boolean) => void;
  /** The trigger: a button, so it can be focused and activated. */
  readonly trigger: ReactElement;
  /** The hint. It holds text only, so the focus never moves into it. */
  readonly children: ReactNode;
};

/** Props of {@link Tooltip}. */
export type TooltipProps = {
  /** The hint. */
  readonly content: string;
  /** The visible trigger content. It becomes a button, so it can be focused and tapped. */
  readonly children: ReactNode;
};

/**
 * Render a trigger with a hint that the caller opens and closes.
 *
 * @param props - The look, the open state and its handler, the trigger, and the hint.
 * @returns The trigger and, while open, the hint in a portal.
 */
export function TooltipHint({
  variant,
  isOpen,
  onOpenChange,
  trigger,
  children,
}: TooltipHintProps) {
  return (
    <TooltipPrimitive.Provider delayDuration={HOVER_DELAY_MS}>
      <TooltipPrimitive.Root open={isOpen} onOpenChange={onOpenChange}>
        <TooltipPrimitive.Trigger asChild>{trigger}</TooltipPrimitive.Trigger>
        <TooltipPrimitive.Portal>
          <TooltipPrimitive.Content sideOffset={4} className={contentVariants({ variant })}>
            {children}
          </TooltipPrimitive.Content>
        </TooltipPrimitive.Portal>
      </TooltipPrimitive.Root>
    </TooltipPrimitive.Provider>
  );
}

/**
 * Render a trigger with a short hint.
 *
 * @param props - The hint and the trigger content.
 * @returns The trigger button and, while open, the hint.
 */
export function Tooltip({ content, children }: TooltipProps) {
  const [isOpen, setIsOpen] = useState(false);
  return (
    <TooltipHint
      variant="label"
      isOpen={isOpen}
      onOpenChange={setIsOpen}
      trigger={
        <button
          type="button"
          className={cn("cursor-help rounded-sm", FOCUS_RING_CLASSES)}
          onClick={() => {
            setIsOpen(true);
          }}
        >
          {children}
        </button>
      }
    >
      {content}
    </TooltipHint>
  );
}
