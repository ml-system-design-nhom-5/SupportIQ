/**
 * The draft as staff read it (console UI design, Draft editing and citations): paragraphs of
 * segments, a new paragraph where `paragraph_index` changes, and after each segment its KB markers
 * and at most one order marker. The view never rebuilds the reply text from segments: the editor
 * starts from the canonical `text` of `backend`.
 */
import type { Citation, KbCitation, ReadyDraft } from "@/features/console-tickets/model/draft";
import type { OrderCitationFact } from "@/features/console-tickets/model/order-citation";
import { buildDocumentKey } from "@/features/console-tickets/model/sources";

/** A KB citation marker: the number of its source and the passage that supports the segment. */
export type KbMarker = {
  readonly citationId: string;
  readonly number: number;
  readonly documentKey: string;
  readonly documentId: string;
  readonly version: string;
  readonly snippet: string;
};

/** A segment with its markers. */
export type DraftViewSegment = {
  readonly segmentId: string;
  readonly text: string;
  readonly kbMarkers: readonly KbMarker[];
  /** The order facts that the segment cites; empty when it states none. */
  readonly orderFacts: readonly OrderCitationFact[];
};

/** A paragraph of the draft. */
export type DraftViewParagraph = {
  readonly paragraphId: string;
  readonly segments: readonly DraftViewSegment[];
};

/**
 * Build the paragraphs of a draft.
 *
 * @param draft - The ready draft.
 * @param numberByKey - The citation number of each cited document version.
 * @returns The paragraphs in reading order.
 */
export function buildDraftParagraphs(
  draft: ReadyDraft,
  numberByKey: ReadonlyMap<string, number>,
): readonly DraftViewParagraph[] {
  const citationById = new Map(draft.citations.map((citation) => [citation.citationId, citation]));
  const paragraphs: { paragraphId: string; index: number; segments: DraftViewSegment[] }[] = [];
  for (const segment of draft.segments) {
    const citations = segment.citationIds.flatMap((citationId) => {
      const citation = citationById.get(citationId);
      return citation === undefined ? [] : [citation];
    });
    const viewSegment: DraftViewSegment = {
      segmentId: segment.segmentId,
      text: segment.text,
      kbMarkers: buildKbMarkers(citations, numberByKey),
      orderFacts: citations.flatMap((citation) =>
        citation.kind === "order_context" ? [citation.fact] : [],
      ),
    };
    const last = paragraphs.at(-1);
    if (last?.index === segment.paragraphIndex) {
      last.segments.push(viewSegment);
    } else {
      paragraphs.push({
        paragraphId: `paragraph-${String(segment.paragraphIndex)}`,
        index: segment.paragraphIndex,
        segments: [viewSegment],
      });
    }
  }
  return paragraphs.map(({ paragraphId, segments }) => ({ paragraphId, segments }));
}

/**
 * Build the KB markers of a segment: one per cited document version.
 *
 * @param citations - The citations of the segment.
 * @param numberByKey - The citation number of each cited document version.
 * @returns The markers, in the order of the citations.
 */
function buildKbMarkers(
  citations: readonly Citation[],
  numberByKey: ReadonlyMap<string, number>,
): readonly KbMarker[] {
  const kbCitations = citations.filter(
    (citation): citation is KbCitation => citation.kind === "kb_document",
  );
  const markers = kbCitations.flatMap((citation) => {
    const documentKey = buildDocumentKey(citation.documentId, citation.version);
    const number = numberByKey.get(documentKey);
    return number === undefined
      ? []
      : [
          {
            citationId: citation.citationId,
            number,
            documentKey,
            documentId: citation.documentId,
            version: citation.version,
            snippet: citation.snippet,
          },
        ];
  });
  return markers.filter(
    (marker, index) => markers.findIndex((other) => other.number === marker.number) === index,
  );
}
