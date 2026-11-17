/**
 * A KB document version in full (UI-20; console UI design, KB document version), mapped from
 * `KbDocumentVersion` (TS-09). KB text is untrusted data and is shown as plain text (SEC-22).
 */
import { formatDate } from "@/design-system";
import { requireMembers } from "@/features/backend-requests";
import type { KbDocumentVersionContract } from "@/features/console-tickets/api/contract-types";
import { describeEffectiveDates } from "@/features/console-tickets/model/sources";

/** One KB document version. */
export type KbDocumentVersion = {
  readonly documentId: string;
  readonly version: string;
  readonly title: string;
  readonly body: string;
  readonly effectiveStartAt: string;
  readonly effectiveEndAt?: string;
  /** A role or a team, never a person's name. */
  readonly owner: string;
  readonly source: string;
  /** Absent when the source does not give it; it is never invented (DATA-13). */
  readonly lastReviewedAt?: string;
};

/** One line of the details of a version. */
export type KbDocumentDetail = {
  readonly term: string;
  readonly value: string;
};

/**
 * Map a KB document version.
 *
 * @param document - A `KbDocumentVersion`.
 * @returns The view model.
 */
export function toKbDocumentVersion(document: KbDocumentVersionContract): KbDocumentVersion {
  requireMembers(document, [
    "document_id",
    "version",
    "title",
    "body",
    "effective_start_at",
    "owner",
    "source",
  ]);
  return {
    documentId: document.document_id,
    version: document.version,
    title: document.title,
    body: document.body,
    effectiveStartAt: document.effective_start_at,
    ...(document.effective_end_at === undefined
      ? {}
      : { effectiveEndAt: document.effective_end_at }),
    owner: document.owner,
    source: document.source,
    ...(document.last_reviewed_at === undefined
      ? {}
      : { lastReviewedAt: document.last_reviewed_at }),
  };
}

/**
 * List the details of a version for its side sheet.
 *
 * @param document - The version.
 * @returns The effective period, the owner, the source, and the last review when it is known.
 */
export function buildKbDocumentDetails(document: KbDocumentVersion): readonly KbDocumentDetail[] {
  return [
    {
      term: "In effect",
      value: describeEffectiveDates(document.effectiveStartAt, document.effectiveEndAt),
    },
    { term: "Owner", value: document.owner },
    { term: "Source", value: document.source },
    ...(document.lastReviewedAt === undefined
      ? []
      : [{ term: "Last reviewed", value: formatDate(document.lastReviewedAt) }]),
  ];
}
