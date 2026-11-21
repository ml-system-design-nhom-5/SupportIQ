/**
 * A citation marker with its hint (UI-20; console UI design, Draft editing and citations):
 * hovering or focusing the marker shows the hint, and activating the marker opens the source.
 * Built on {@link TooltipHint} (UI-31); the hint holds text only, so the focus never moves into it.
 */
import { ChevronRight } from "lucide-react";
import { type ReactNode, useState } from "react";

import { Icon } from "@/design-system/primitives/icon";
import { TooltipHint } from "@/design-system/primitives/tooltip";

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
    <TooltipHint
      variant="card"
      isOpen={isOpen}
      onOpenChange={setIsOpen}
      trigger={
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
      }
    >
      {children}
      <p className="flex items-center gap-1 px-3 pb-3 text-xs text-text-muted">
        <Icon icon={ChevronRight} />
        {activationHint}
      </p>
    </TooltipHint>
  );
}
