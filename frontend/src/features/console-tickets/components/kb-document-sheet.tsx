/**
 * The full text of a KB document version in a side sheet over the workspace (UI-20; console UI
 * design, kb-document.png), with the cited or retrieved passage highlighted, so staff check a
 * citation against its source without leaving the ticket. KB text is plain text (SEC-22).
 */
import { FileSearch, FileText } from "lucide-react";

import {
  DescriptionList,
  type DialogReturnFocus,
  Identifier,
  KbDocumentText,
  presentationByDocumentValidity,
  Sheet,
  Skeleton,
  Stack,
  StateMessage,
  StatusBadge,
  VisuallyHidden,
} from "@/design-system";
import { describeFailure, FailureState, getRequestFailure } from "@/features/backend-requests";
import { useKbDocumentVersion } from "@/features/console-tickets/api/use-kb-document-version";
import { buildKbDocumentDetails } from "@/features/console-tickets/model/kb-document";
import type { SourceSelection } from "@/features/console-tickets/model/sources";

/** Props of {@link KbDocumentSheet}. */
type KbDocumentSheetProps = {
  readonly selection: SourceSelection;
  readonly returnFocus: DialogReturnFocus;
  readonly onClose: () => void;
};

/**
 * Render the side sheet of a document version.
 *
 * @param props - The opened source, the focus target, and the close handler.
 * @returns The open sheet.
 */
export function KbDocumentSheet({ selection, returnFocus, onClose }: KbDocumentSheetProps) {
  const documentQuery = useKbDocumentVersion(selection.documentId, selection.version);
  const document = documentQuery.data;
  const failure = getRequestFailure(documentQuery.error);
  return (
    <Sheet
      icon={FileText}
      title={document?.title ?? selection.title}
      returnFocus={returnFocus}
      onClose={onClose}
    >
      <Stack direction="row" gap="2" align="center" shouldWrap>
        <Identifier size="xs">{`${selection.documentId} · ${selection.version}`}</Identifier>
        {selection.source === undefined ? null : (
          <StatusBadge presentation={presentationByDocumentValidity[selection.source.validity]} />
        )}
      </Stack>
      {document === undefined ? (
        <DocumentState
          failure={failure}
          isRetrying={documentQuery.isFetching}
          onRetry={() => {
            void documentQuery.refetch();
          }}
        />
      ) : (
        <>
          <DescriptionList
            items={buildKbDocumentDetails(document).map((detail) => ({
              term: detail.term,
              description: detail.value,
            }))}
          />
          <KbDocumentText body={document.body} highlight={selection.highlight} />
        </>
      )}
    </Sheet>
  );
}

/**
 * Render the loading or the error state of the document.
 *
 * @param props - The failure, when the read failed, and its retry.
 * @returns The skeleton, "not found", or the error state.
 */
function DocumentState({
  failure,
  isRetrying,
  onRetry,
}: {
  readonly failure: ReturnType<typeof getRequestFailure>;
  readonly isRetrying: boolean;
  readonly onRetry: () => void;
}) {
  if (failure === undefined) {
    return (
      <Stack gap="2">
        <p role="status">
          <VisuallyHidden>Loading the document…</VisuallyHidden>
        </p>
        <Skeleton width="full" />
        <Skeleton width="three-quarters" />
      </Stack>
    );
  }
  const description = describeFailure(failure);
  if (description.category === "not_found") {
    return (
      <StateMessage
        icon={FileSearch}
        headingLevel={2}
        title="This document version was not found"
        description="The knowledge base no longer holds it."
        {...(description.traceId === undefined ? {} : { traceId: description.traceId })}
      />
    );
  }
  return (
    <FailureState
      title="This document could not be loaded"
      failure={failure}
      headingLevel={2}
      isRetrying={isRetrying}
      onRetry={onRetry}
    />
  );
}
