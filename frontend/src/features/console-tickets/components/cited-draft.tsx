/**
 * The text of an AI draft with its citation markers (console UI design, Draft editing and
 * citations; UI-20): after each segment, its KB markers in the `ai` tone, then one neutral order
 * marker when the segment states order facts. A KB marker opens its document version; the order
 * marker opens the order chip popover. AI text is shown exactly as `backend` returns it; a
 * placeholder in it is highlighted and named under the draft (UI-43).
 */
import { Info } from "lucide-react";

import {
  CitationMarker,
  type CitationSource,
  DraftText,
  type DraftTextTone,
  InlineMessage,
  MarkedText,
  OrderCitationMarker,
  presentationByDocumentValidity,
  Stack,
} from "@/design-system";
import type { ReadyDraft } from "@/features/console-tickets/model/draft";
import {
  buildDraftParagraphs,
  type DraftViewSegment,
  type KbMarker,
} from "@/features/console-tickets/model/draft-view";
import {
  hasPlaceholder,
  PLACEHOLDER_LABEL,
  splitPlaceholders,
} from "@/features/console-tickets/model/placeholders";
import {
  type Source,
  type SourceSelection,
  toSourceSelection,
} from "@/features/console-tickets/model/sources";

/** What the markers of a draft need. */
export type MarkerContext = {
  readonly sourceByKey: ReadonlyMap<string, Source>;
  /** The ID of the ticket's order; undefined when the ticket has none. */
  readonly orderId: string | undefined;
  readonly onOpenSource: (selection: SourceSelection, opener: HTMLElement) => void;
  /** Opens the order chip popover; receives the marker, which the focus returns to. */
  readonly onOpenOrder: (opener: HTMLElement) => void;
};

/** What the citations of a draft need: the number of each cited document version and the markers. */
export type CitationContext = MarkerContext & {
  readonly numberByKey: ReadonlyMap<string, number>;
};

/** Props of {@link CitedDraft}. */
type CitedDraftProps = CitationContext & {
  readonly draft: ReadyDraft;
  /** `muted` for a rejected or an outdated draft. */
  readonly tone?: DraftTextTone;
};

/**
 * Render the draft with its markers.
 *
 * @param props - The draft, the citation numbers, the tone, and what the markers need.
 * @returns The draft text and, when it holds a placeholder, the line that names it.
 */
export function CitedDraft({
  draft,
  numberByKey,
  tone = "default",
  ...markerContext
}: CitedDraftProps) {
  return (
    <Stack gap="3">
      <DraftText
        tone={tone}
        paragraphs={buildDraftParagraphs(draft, numberByKey).map((paragraph) => ({
          paragraphId: paragraph.paragraphId,
          segments: paragraph.segments.map((segment) => ({
            segmentId: segment.segmentId,
            text: <MarkedText parts={splitPlaceholders(segment.text)} />,
            markers: <SegmentMarkers segment={segment} context={markerContext} />,
          })),
        }))}
      />
      {hasPlaceholder(draft.text) ? (
        <InlineMessage tone="muted" icon={Info}>
          {`${PLACEHOLDER_LABEL}.`}
        </InlineMessage>
      ) : null}
    </Stack>
  );
}

/**
 * Render the markers of a segment: its KB markers, then one order marker when it states order
 * facts.
 *
 * @param props - The segment and the marker context.
 * @returns The markers.
 */
function SegmentMarkers({
  segment,
  context,
}: {
  readonly segment: DraftViewSegment;
  readonly context: MarkerContext;
}) {
  const orderIdProps = context.orderId === undefined ? {} : { orderId: context.orderId };
  return (
    <>
      {segment.kbMarkers.map((marker) => {
        const source = context.sourceByKey.get(marker.documentKey);
        return (
          <CitationMarker
            key={marker.citationId}
            number={marker.number}
            source={toCitationSource(marker, source)}
            snippet={marker.snippet}
            onActivate={(opener) => {
              context.onOpenSource(toSourceSelection(marker, source), opener);
            }}
          />
        );
      })}
      {segment.orderFacts.length === 0 ? null : (
        <OrderCitationMarker
          {...orderIdProps}
          facts={segment.orderFacts}
          onActivate={context.onOpenOrder}
        />
      )}
    </>
  );
}

/**
 * Describe the source of a KB marker for its hint.
 *
 * @param marker - The marker.
 * @param source - Its source in the Sources panel, when the analysis returned the version.
 * @returns The title, the ID, the version, and the validity with its period when known.
 */
function toCitationSource(marker: KbMarker, source: Source | undefined): CitationSource {
  const identity = { documentId: marker.documentId, version: marker.version };
  if (source === undefined) {
    return { ...identity, title: marker.documentId };
  }
  return {
    ...identity,
    title: source.title,
    validity: presentationByDocumentValidity[source.validity],
    period: source.period,
  };
}
