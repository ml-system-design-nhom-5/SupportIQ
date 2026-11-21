/**
 * The loading state while the session is checked (UI-24): skeletons where the screen will be.
 */
import { PageColumn, Skeleton, Stack, VisuallyHidden } from "@/design-system";

/**
 * Render the loading state of a screen whose session is being checked.
 *
 * @returns A busy main region with skeletons.
 */
export function SessionLoading() {
  return (
    <PageColumn area="shop">
      <Stack gap="3">
        <p role="status">
          <VisuallyHidden>Checking your session…</VisuallyHidden>
        </p>
        <Skeleton width="third" />
        <Skeleton width="full" height="block" />
        <Skeleton width="three-quarters" />
      </Stack>
    </PageColumn>
  );
}
