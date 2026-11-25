/**
 * Read the full text of a KB document version for its side sheet
 * (`getConsoleKbDocumentVersion`, UI-20). A version never changes, so the cached text stays fresh.
 */
import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { useBackendClient } from "@/api/client";
import { requestData } from "@/features/backend-requests";
import { consoleQueryKeys } from "@/features/console-tickets/api/console-query-keys";
import {
  type KbDocumentVersion,
  toKbDocumentVersion,
} from "@/features/console-tickets/model/kb-document";

/**
 * Read a KB document version.
 *
 * @param documentId - The `document_id`.
 * @param version - The `version`.
 * @returns The query of the version.
 */
export function useKbDocumentVersion(
  documentId: string,
  version: string,
): UseQueryResult<KbDocumentVersion> {
  const client = useBackendClient();
  return useQuery({
    queryKey: consoleQueryKeys.kbDocumentVersion(documentId, version),
    queryFn: ({ signal }) =>
      requestData(
        () =>
          client.GET("/v1/console/kb-documents/{document_id}/versions/{version}", {
            params: { path: { document_id: documentId, version } },
            signal,
          }),
        toKbDocumentVersion,
      ),
    staleTime: Infinity,
  });
}
