/**
 * A short hint on hover or keyboard focus, on Radix Tooltip (UI-31). Activating the trigger, as a
 * tap on a touch screen does, also shows it (shop UI design, States).
 */
import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import { type ReactNode, useState } from "react";

import { cn } from "@/design-system/primitives/class-names";
import { FOCUS_RING_CLASSES } from "@/design-system/primitives/focus-ring";

/** The hover delay: the base motion duration of UI-09. */
const HOVER_DELAY_MS = 200;

/** Props of {@link Tooltip}. */
export type TooltipProps = {
  /** The hint. */
  readonly content: string;
  /** The visible trigger content. It becomes a button, so it can be focused and tapped. */
  readonly children: ReactNode;
};

/**
 * Render a trigger with a tooltip.
 *
 * @param props - The hint and the trigger content.
 * @returns The trigger button and, while open, the hint.
 */
export function Tooltip({ content, children }: TooltipProps) {
  const [isOpen, setIsOpen] = useState(false);
  return (
    <TooltipPrimitive.Provider delayDuration={HOVER_DELAY_MS}>
      <TooltipPrimitive.Root open={isOpen} onOpenChange={setIsOpen}>
        <TooltipPrimitive.Trigger asChild>
          <button
            type="button"
            className={cn("cursor-help rounded-sm", FOCUS_RING_CLASSES)}
            onClick={() => {
              setIsOpen(true);
            }}
          >
            {children}
          </button>
        </TooltipPrimitive.Trigger>
        <TooltipPrimitive.Portal>
          <TooltipPrimitive.Content
            sideOffset={4}
            className="z-30 rounded-sm bg-text px-2 py-1 text-xs text-text-inverse shadow-md"
          >
            {content}
          </TooltipPrimitive.Content>
        </TooltipPrimitive.Portal>
      </TooltipPrimitive.Root>
    </TooltipPrimitive.Provider>
  );
}
