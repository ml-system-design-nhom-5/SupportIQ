/**
 * The sources of a suggestion (console UI design, Sources; UI-20): the KB document versions that
 * the analysis retrieved, ordered by rank, each with the number of its citation markers when the
 * draft cites it. Numbers count from 1 in reading order of the draft, one number per document
 * version, so a marker and its source carry the same number.
 */
import type { DocumentValidityName } from "@/design-system";
import { formatDate } from "@/design-system";
import type { RankedDocument } from "@/features/console-tickets/model/analysis";
import type { Citation, ReadyDraft } from "@/features/console-tickets/model/draft";

/** A source of the Sources panel. */
export type Source = {
  /** Identifies the document version; see {@link buildDocumentKey}. */
  readonly key: string;
  /** The number of its citation markers; absent when the draft does not cite it. */
  readonly number?: number;
  readonly documentId: string;
  readonly version: string;
  readonly title: string;
  readonly validity: DocumentValidityName;
  /** The effective period in words, for example "Since 1 Sep 2026". */
  readonly period: string;
  /** The passage that retrieval matched, highlighted in the full text. */
  readonly snippet: string;
};

/**
 * Build the key of a document version. Document IDs and versions never contain a space
 * (`KbDocumentId`, `KbDocumentVersionTag`), so the key is unique.
 *
 * @param documentId - The `document_id`.
 * @param version - The `version`.
 * @returns For example `SAMPLE-REFUND-001 1.0`.
 */
export function buildDocumentKey(documentId: string, version: string): string {
  return `${documentId} ${version}`;
}

/**
 * Number the KB document versions that a draft cites.
 *
 * @param draft - The ready draft, or undefined when there is none.
 * @returns The number of each cited document version, by its key.
 */
export function numberCitedDocuments(draft: ReadyDraft | undefined): ReadonlyMap<string, number> {
  const numberByKey = new Map<string, number>();
  if (draft === undefined) {
    return numberByKey;
  }
  const citationById = new Map(draft.citations.map((citation) => [citation.citationId, citation]));
  const citedIds = draft.segments.flatMap((segment) => segment.citationIds);
  for (const citation of citedIds.map((citationId) => citationById.get(citationId))) {
    const key = getKbCitationKey(citation);
    if (key !== undefined && !numberByKey.has(key)) {
      numberByKey.set(key, numberByKey.size + 1);
    }
  }
  return numberByKey;
}

/**
 * Build the Sources panel.
 *
 * @param documents - The ranked documents of the analysis.
 * @param numberByKey - The citation numbers of {@link numberCitedDocuments}.
 * @returns The sources, in the order of their rank.
 */
export function buildSources(
  documents: readonly RankedDocument[],
  numberByKey: ReadonlyMap<string, number>,
): readonly Source[] {
  return [...documents]
    .sort((first, second) => first.rank - second.rank)
    .map((document) => {
      const key = buildDocumentKey(document.documentId, document.version);
      const number = numberByKey.get(key);
      return {
        key,
        ...(number === undefined ? {} : { number }),
        documentId: document.documentId,
        version: document.version,
        title: document.title,
        validity: document.validity,
        period: describeEffectivePeriod(document),
        snippet: document.snippet,
      };
    });
}

/**
 * Describe the effective period of a document version.
 *
 * @param document - The start, the optional end, and the validity of the version.
 * @returns "Ended" with the end of an expired version, "Since" with the start of an open-ended
 *   one, otherwise both dates.
 */
export function describeEffectivePeriod(
  document: Pick<RankedDocument, "effectiveStartAt" | "effectiveEndAt" | "validity">,
): string {
  if (document.effectiveEndAt !== undefined && document.validity === "expired") {
    return `Ended ${formatDate(document.effectiveEndAt)}`;
  }
  return describeEffectiveDates(document.effectiveStartAt, document.effectiveEndAt);
}

/**
 * Describe the effective dates of a document version.
 *
 * @param effectiveStartAt - When the version came into effect.
 * @param effectiveEndAt - When it stopped being in effect; undefined when it is open-ended.
 * @returns "Since" with the start of an open-ended version, otherwise both dates.
 */
export function describeEffectiveDates(
  effectiveStartAt: string,
  effectiveEndAt: string | undefined,
): string {
  if (effectiveEndAt === undefined) {
    return `Since ${formatDate(effectiveStartAt)}`;
  }
  return `${formatDate(effectiveStartAt)} to ${formatDate(effectiveEndAt)}`;
}

/**
 * Read the document key of a KB citation.
 *
 * @param citation - A citation, or undefined for an ID that names no citation.
 * @returns The key, or undefined for an order citation or a missing one.
 */
function getKbCitationKey(citation: Citation | undefined): string | undefined {
  return citation?.kind === "kb_document"
    ? buildDocumentKey(citation.documentId, citation.version)
    : undefined;
}

/** A cited or retrieved passage of a document version. */
export type SourcePassage = {
  readonly documentId: string;
  readonly version: string;
  readonly snippet: string;
};

/**
 * Describe the document version that staff open in the side sheet, from a source of the Sources
 * panel or from a KB marker of the draft. The passage is highlighted in the full text.
 *
 * @param passage - The retrieved passage of a source, or the cited passage of a marker.
 * @param source - The source of the version in the Sources panel; undefined when the analysis did
 *   not return the version.
 * @returns The selection, titled with the document ID when the source is unknown.
 */
export function toSourceSelection(
  passage: SourcePassage,
  source: Source | undefined,
): SourceSelection {
  return {
    documentId: passage.documentId,
    version: passage.version,
    title: source?.title ?? passage.documentId,
    highlight: passage.snippet,
    ...(source === undefined ? {} : { source }),
  };
}

/** A source that staff opened in the side sheet. */
export type SourceSelection = {
  readonly documentId: string;
  readonly version: string;
  /** The title, or the document ID when the analysis did not return the version. */
  readonly title: string;
  /** The passage to highlight in the full text: the cited or the retrieved snippet. */
  readonly highlight: string;
  /** The source of the Sources panel, absent when the analysis did not return the version. */
  readonly source?: Source;
};
