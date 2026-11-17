/**
 * Read the versions in use (`getAdminVersions`). The read changes nothing. It runs when the screen
 * opens and when the admin selects Try again, never at an interval or on window focus: versions
 * change only through the release process, and when `ai-service` cannot be reached the screen asks
 * the admin to reload the page later (admin UI design, Versions in use).
 */
import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { useBackendClient } from "@/api/client";
import { versionQueryKeys } from "@/features/admin-versions/api/version-query-keys";
import {
  toVersionsInUse,
  type VersionsInUse,
} from "@/features/admin-versions/model/versions-in-use";
import { requestData } from "@/features/backend-requests";

/**
 * Read the versions in use.
 *
 * @returns The query of the versions.
 */
export function useVersionsInUse(): UseQueryResult<VersionsInUse> {
  const client = useBackendClient();
  return useQuery({
    queryKey: versionQueryKeys.versions(),
    queryFn: ({ signal }) =>
      requestData(() => client.GET("/v1/admin/versions", { signal }), toVersionsInUse),
  });
}
