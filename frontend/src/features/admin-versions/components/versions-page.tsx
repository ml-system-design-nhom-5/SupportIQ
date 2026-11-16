/**
 * The Versions screen (`/admin/versions`, admin UI design, Versions in use; UI-45): the build of
 * `backend` and the release and asset versions that `ai-service` serves, or that they are unknown
 * when `backend` could not read them. The screen is read-only and says so: versions change only
 * through the release process. While the versions load, skeleton panels stand in for them
 * (UI-24). When they cannot be loaded, the screen shows the error state with Try again, or the
 * permission-denied state for a `403` (UI-23, UI-25).
 */
import { PageHeader, Stack, Text } from "@/design-system";
import { useVersionsInUse } from "@/features/admin-versions/api/use-versions-in-use";
import { VersionsDeveloperDetails } from "@/features/admin-versions/components/versions-developer-details";
import { VersionsLoading } from "@/features/admin-versions/components/versions-loading";
import { VersionsPanels } from "@/features/admin-versions/components/versions-panels";
import { getRequestFailure } from "@/features/backend-requests";
import { AreaLoadFailure } from "@/features/session";

/** The title of the browser tab. */
const DOCUMENT_TITLE = "Versions in use · SupportIQ Admin";

/**
 * Render the Versions screen.
 *
 * @returns The screen in the state of its data.
 */
export function VersionsPage() {
  const versionsQuery = useVersionsInUse();
  const loadFailure = getRequestFailure(versionsQuery.error);

  if (versionsQuery.data === undefined && loadFailure !== undefined) {
    return (
      <>
        <title>{DOCUMENT_TITLE}</title>
        <AreaLoadFailure
          area="admin"
          title="The versions could not be loaded"
          failure={loadFailure}
          headingLevel={1}
          isRetrying={versionsQuery.isFetching}
          onRetry={() => {
            void versionsQuery.refetch();
          }}
        />
      </>
    );
  }
  return (
    <Stack gap="4">
      <title>{DOCUMENT_TITLE}</title>
      <PageHeader
        title="Versions in use"
        density="compact"
        action={
          <Text tone="muted">Read-only. Versions change only through the release process.</Text>
        }
      />
      {versionsQuery.data === undefined ? (
        <VersionsLoading />
      ) : (
        <>
          <VersionsPanels versions={versionsQuery.data} />
          <VersionsDeveloperDetails versions={versionsQuery.data} />
        </>
      )}
    </Stack>
  );
}
