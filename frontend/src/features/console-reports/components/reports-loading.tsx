/**
 * The report while it loads (UI-24): placeholder panels where the figures will be. The header
 * with the period menu stays usable.
 */
import { Grid, Panel, PanelSection, Skeleton, VisuallyHidden } from "@/design-system";

/** The number of placeholder panels: two rows of the grid. */
const SKELETON_PANEL_COUNT = 6;

const skeletonKeys = Array.from(
  { length: SKELETON_PANEL_COUNT },
  (_, index) => `skeleton-${String(index)}`,
);

/**
 * Render the loading state of the report.
 *
 * @returns The placeholder panels, announced as loading.
 */
export function ReportsLoading() {
  return (
    <>
      <p role="status">
        <VisuallyHidden>Loading the report…</VisuallyHidden>
      </p>
      <Grid>
        {skeletonKeys.map((key) => (
          <Panel key={key} density="compact">
            <PanelSection>
              <Skeleton width="third" />
              <Skeleton width="full" />
              <Skeleton width="three-quarters" />
              <Skeleton width="half" />
            </PanelSection>
          </Panel>
        ))}
      </Grid>
    </>
  );
}
