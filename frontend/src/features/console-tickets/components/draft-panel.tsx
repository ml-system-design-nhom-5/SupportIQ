/**
 * The AI draft in the reply area (console UI design, Draft editing and citations; UI-18, UI-20):
 * the warnings at the top, next to the action they block, and the draft with its citation markers.
 * The panel carries the `ai` marker (UI-13).
 */
import { Sparkles } from "lucide-react";

import {
  CitationMarker,
  type CitationSource,
  DraftText,
  OrderCitationMarker,
  Panel,
  PanelHeader,
  PanelSection,
  presentationByAiReasonCode,
  presentationByAiStatus,
  presentationByDocumentValidity,
  RelativeTime,
  Stack,
  StatusBadge,
  Text,
  WarningList,
} from "@/design-system";
import type { ReadyDraft } from "@/features/console-tickets/model/draft";
import {
  buildDraftParagraphs,
  type DraftViewSegment,
  type KbMarker,
} from "@/features/console-tickets/model/draft-view";
import type { SuggestionWarning } from "@/features/console-tickets/model/reason-codes";
import type { Source, SourceSelection } from "@/features/console-tickets/model/sources";

/** What the markers of a draft need. */
type MarkerContext = {
  readonly sourceByKey: ReadonlyMap<string, Source>;
  /** The ID of the ticket's order; undefined when the ticket has none. */
  readonly orderId: string | undefined;
  readonly onOpenSource: (selection: SourceSelection, opener: HTMLElement) => void;
  readonly onOpenOrder: () => void;
};

/** Props of {@link DraftPanel}. */
type DraftPanelProps = MarkerContext & {
  readonly draft: ReadyDraft;
  readonly numberByKey: ReadonlyMap<string, number>;
  readonly warnings: readonly SuggestionWarning[];
  /** When the suggestion started, as an RFC 3339 timestamp. */
  readonly generatedAt: string;
};

/**
 * Render the draft.
 *
 * @param props - The draft, the citation numbers, the warnings, the time, and the marker context.
 * @returns The panel.
 */
export function DraftPanel({
  draft,
  numberByKey,
  warnings,
  generatedAt,
  ...markerContext
}: DraftPanelProps) {
  const paragraphs = buildDraftParagraphs(draft, numberByKey);
  return (
    <Panel density="compact" as="section" label="AI draft" tone="ai">
      <PanelHeader
        icon={Sparkles}
        level={2}
        title="AI draft"
        trailing={
          <Stack direction="row" gap="2" align="center">
            <StatusBadge presentation={presentationByAiStatus.draft_ready} />
            <Text tone="muted">
              Generated <RelativeTime timestamp={generatedAt} />
            </Text>
          </Stack>
        }
      />
      {warnings.length === 0 ? null : (
        <PanelSection>
          <WarningList
            warnings={warnings.map((warning) => ({
              warningId: warning.warningId,
              title: presentationByAiReasonCode[warning.reasonCode].label,
              description: warning.text,
            }))}
          />
        </PanelSection>
      )}
      <PanelSection>
        <DraftText
          paragraphs={paragraphs.map((paragraph) => ({
            paragraphId: paragraph.paragraphId,
            segments: paragraph.segments.map((segment) => ({
              segmentId: segment.segmentId,
              text: segment.text,
              markers: <SegmentMarkers segment={segment} context={markerContext} />,
            })),
          }))}
        />
      </PanelSection>
    </Panel>
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
      {segment.kbMarkers.map((marker) => (
        <CitationMarker
          key={marker.citationId}
          number={marker.number}
          source={toCitationSource(marker, context.sourceByKey.get(marker.documentKey))}
          snippet={marker.snippet}
          onActivate={(opener) => {
            context.onOpenSource(toSourceSelection(marker, context.sourceByKey), opener);
          }}
        />
      ))}
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

/**
 * Describe the source that a KB marker opens: the cited passage is highlighted.
 *
 * @param marker - The marker.
 * @param sourceByKey - The sources of the Sources panel.
 * @returns The selection.
 */
function toSourceSelection(
  marker: KbMarker,
  sourceByKey: ReadonlyMap<string, Source>,
): SourceSelection {
  const source = sourceByKey.get(marker.documentKey);
  return {
    documentId: marker.documentId,
    version: marker.version,
    title: source?.title ?? marker.documentId,
    highlight: marker.snippet,
    ...(source === undefined ? {} : { source }),
  };
}
