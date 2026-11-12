/**
 * A citation marker with its hint (UI-20; console UI design, Draft editing and citations):
 * hovering or focusing the marker shows the hint, and activating the marker opens the source.
 * Built on Radix Tooltip (UI-31); the hint holds text only, so the focus never moves into it.
 */
import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import { ChevronRight } from "lucide-react";
import { type ReactNode, useState } from "react";

import { Icon } from "@/design-system/primitives/icon";

/** The hover delay: the base motion duration of UI-09. */
const HOVER_DELAY_MS = 200;

/** Props of {@link CitationHint}. */
export type CitationHintProps = {
  /** The accessible name of the marker, for example "Source 1: Refund policy". */
  readonly label: string;
  /** The classes of the marker: the `ai` tone for a KB marker, neutral for an order marker. */
  readonly markerClassName: string;
  /** The visible content of the marker: its number or its icon. */
  readonly marker: ReactNode;
  /** What activating the marker does, for example "Activate the marker to read the full version". */
  readonly activationHint: string;
  /** Opens the source; receives the marker, which the focus returns to. */
  readonly onActivate: (marker: HTMLElement) => void;
  /** The content of the hint. */
  readonly children: ReactNode;
};

/**
 * Render the marker and, while it is hovered or focused, its hint.
 *
 * @param props - The name, the look, and the content of the marker, the activation, and the hint.
 * @returns The marker button; the hint opens in a portal.
 */
export function CitationHint({
  label,
  markerClassName,
  marker,
  activationHint,
  onActivate,
  children,
}: CitationHintProps) {
  const [isOpen, setIsOpen] = useState(false);
  return (
    <TooltipPrimitive.Provider delayDuration={HOVER_DELAY_MS}>
      <TooltipPrimitive.Root open={isOpen} onOpenChange={setIsOpen}>
        <TooltipPrimitive.Trigger asChild>
          <button
            type="button"
            aria-label={label}
            className={markerClassName}
            onClick={(event) => {
              setIsOpen(false);
              onActivate(event.currentTarget);
            }}
          >
            {marker}
          </button>
        </TooltipPrimitive.Trigger>
        <TooltipPrimitive.Portal>
          <TooltipPrimitive.Content
            sideOffset={4}
            className="z-30 flex w-hint flex-col overflow-hidden rounded-md border border-border bg-surface-raised text-sm text-text shadow-md"
          >
            {children}
            <p className="flex items-center gap-1 px-3 pb-3 text-xs text-text-muted">
              <Icon icon={ChevronRight} />
              {activationHint}
            </p>
          </TooltipPrimitive.Content>
        </TooltipPrimitive.Portal>
      </TooltipPrimitive.Root>
    </TooltipPrimitive.Provider>
  );
}
