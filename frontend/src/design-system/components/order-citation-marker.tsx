/**
 * The marker of the order facts that a draft segment states (ADR-0014; console UI design, Draft
 * editing and citations): one marker per segment, in neutral colors and without a number, because
 * order data is not AI output (placement rule 9). Hovering or focusing it lists each cited field
 * with its value and says "From order records, not AI"; activating it opens the order details.
 */
import { Package } from "lucide-react";

import { CitationHint } from "@/design-system/components/citation-hint";
import { OrderRecordHeader } from "@/design-system/components/order-record-header";
import { cn } from "@/design-system/primitives/class-names";
import { DescriptionList } from "@/design-system/primitives/description-list";
import { FOCUS_RING_CLASSES } from "@/design-system/primitives/focus-ring";
import { Icon } from "@/design-system/primitives/icon";

const MARKER_CLASSES =
  "mx-1 inline-flex size-4 items-center justify-center rounded-sm border border-border bg-background align-text-top text-text-muted";

/** One cited order fact. */
export type CitedOrderFact = {
  readonly term: string;
  readonly value: string;
};

/** Props of {@link OrderCitationMarker}. */
export type OrderCitationMarkerProps = {
  /** The ID of the ticket's order; absent when the ticket has none. */
  readonly orderId?: string;
  readonly facts: readonly CitedOrderFact[];
  /** Opens the order details. */
  readonly onActivate: () => void;
};

/**
 * Render the marker with its hint.
 *
 * @param props - The order ID, the cited facts, and the activation handler.
 * @returns The marker.
 */
export function OrderCitationMarker({ orderId, facts, onActivate }: OrderCitationMarkerProps) {
  return (
    <CitationHint
      label="Order facts, from order records, not AI"
      markerClassName={cn(MARKER_CLASSES, FOCUS_RING_CLASSES)}
      marker={<Icon icon={Package} size="xs" />}
      activationHint="Activate the marker to open the order details"
      onActivate={() => {
        onActivate();
      }}
    >
      <OrderRecordHeader title="Order" {...(orderId === undefined ? {} : { orderId })} />
      <div className="p-3">
        <DescriptionList
          items={facts.map((fact) => ({ term: fact.term, description: fact.value }))}
        />
      </div>
    </CitationHint>
  );
}
