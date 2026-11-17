/**
 * The draft part of a suggestion (console UI design, Draft editing and citations), mapped from
 * `DraftPart` (TS-09). A draft exists only when it is ready (CODE-29). A status that this version
 * does not know is `unavailable`, so the ticket is handled manually; a citation of a kind that
 * this version does not know is ignored (CON-22).
 */
import type { AiReasonCodeName } from "@/design-system";
import { requireMembers } from "@/features/backend-requests";
import type {
  CitationContract,
  DraftPartContract,
  ReadyDraftContract,
} from "@/features/console-tickets/api/contract-types";
import {
  type OrderCitationFact,
  toOrderCitationFact,
} from "@/features/console-tickets/model/order-citation";
import { toAiReasonCodes, toFirstReasonCode } from "@/features/console-tickets/model/reason-codes";

/** A citation of a KB document version. */
export type KbCitation = {
  readonly kind: "kb_document";
  readonly citationId: string;
  readonly documentId: string;
  readonly version: string;
  readonly snippet: string;
};

/** A citation of one field of the order context, with its value. */
export type OrderCitation = {
  readonly kind: "order_context";
  readonly citationId: string;
  readonly fact: OrderCitationFact;
};

/** A citation of a draft. */
export type Citation = KbCitation | OrderCitation;

/** One segment of a draft, with pseudonyms restored. */
export type DraftSegment = {
  readonly segmentId: string;
  readonly paragraphIndex: number;
  readonly text: string;
  readonly citationIds: readonly string[];
};

/** A draft for staff to review. Its text is Confidential: shown, never logged. */
export type ReadyDraft = {
  readonly status: "draft_ready";
  readonly segments: readonly DraftSegment[];
  readonly citations: readonly Citation[];
  /** The canonical text that `backend` built, which the reply editor starts from. */
  readonly text: string;
  readonly reasonCodes: readonly AiReasonCodeName[];
  readonly staffNote?: string;
};

/** A draft outcome without a draft. */
export type NoDraft = {
  readonly status: "abstained" | "escalation_recommended" | "llm_unavailable";
  readonly reasonCodes: readonly AiReasonCodeName[];
  readonly staffNote?: string;
};

/** The draft part, by status. */
export type DraftPart =
  | { readonly status: "pending" }
  | ReadyDraft
  | NoDraft
  | { readonly status: "unavailable"; readonly reasonCode: AiReasonCodeName };

/**
 * Map the draft part of a suggestion.
 *
 * @param draft - A `DraftPart`.
 * @returns The part; an unknown status is `unavailable`.
 */
export function toDraftPart(draft: DraftPartContract): DraftPart {
  requireMembers(draft, ["draft_status"]);
  switch (draft.draft_status) {
    case "pending":
      return { status: "pending" };
    case "draft_ready":
      return toReadyDraft(draft);
    case "abstained":
    case "escalation_recommended":
    case "llm_unavailable":
      return {
        status: draft.draft_status,
        reasonCodes: toAiReasonCodes(draft.reason_codes),
        ...(draft.staff_note === undefined ? {} : { staffNote: draft.staff_note }),
      };
    case "unavailable":
      return { status: "unavailable", reasonCode: toFirstReasonCode(draft.reason_codes) };
    default:
      return { status: "unavailable", reasonCode: "unknown" };
  }
}

/**
 * Map a ready draft.
 *
 * @param draft - A `ReadyDraftPart`.
 * @returns The view model, without citations of an unknown kind.
 */
function toReadyDraft(draft: ReadyDraftContract): ReadyDraft {
  requireMembers(draft, ["segments", "citations", "text", "reason_codes"]);
  return {
    status: "draft_ready",
    segments: draft.segments.map((segment) => ({
      segmentId: segment.segment_id,
      paragraphIndex: segment.paragraph_index,
      text: segment.text,
      citationIds: segment.citation_ids,
    })),
    citations: draft.citations.flatMap(toCitations),
    text: draft.text,
    reasonCodes: toAiReasonCodes(draft.reason_codes),
    ...(draft.staff_note === undefined ? {} : { staffNote: draft.staff_note }),
  };
}

/**
 * Map a citation.
 *
 * @param citation - A `CitationView`.
 * @returns The citation, or nothing for a kind or an order field that this version does not know.
 */
function toCitations(citation: CitationContract): readonly Citation[] {
  switch (citation.source_type) {
    case "kb_document":
      return [
        {
          kind: "kb_document",
          citationId: citation.citation_id,
          documentId: citation.document_id,
          version: citation.version,
          snippet: citation.snippet,
        },
      ];
    case "order_context": {
      const fact = toOrderCitationFact(citation.field, citation.value);
      return fact === undefined
        ? []
        : [{ kind: "order_context", citationId: citation.citation_id, fact }];
    }
    default:
      return [];
  }
}
