/**
 * The versions while they load (UI-24): skeleton rows in the place of the two panels, announced as
 * loading. The `ai-service` placeholder has one row per asset and the `backend` placeholder one
 * row for the build, so the panels replace them without a jump.
 */
import { Panel, PanelSection, Skeleton, Stack, VisuallyHidden } from "@/design-system";
import { buildAssetVersionRows } from "@/features/admin-versions/model/versions-in-use";

/** The keys of the skeleton rows of `ai-service`: the terms of its assets. */
const aiServiceRowKeys = buildAssetVersionRows({ status: "unavailable" }).map((row) => row.term);

/** The key of the skeleton row of `backend`: its build. */
const backendRowKeys = ["build"];

/** Props of {@link SkeletonPanel}. */
type SkeletonPanelProps = {
  /** One stable key per placeholder row (TS-24). */
  readonly rowKeys: readonly string[];
};

/**
 * Render the loading state of the versions.
 *
 * @returns The placeholder panels, announced as loading.
 */
export function VersionsLoading() {
  return (
    <Stack gap="4">
      <p role="status">
        <VisuallyHidden>Loading the versions…</VisuallyHidden>
      </p>
      <SkeletonPanel rowKeys={aiServiceRowKeys} />
      <SkeletonPanel rowKeys={backendRowKeys} />
    </Stack>
  );
}

/**
 * Render a placeholder panel: a header bar and one bar per row.
 *
 * @param props - The keys of the rows.
 * @returns The panel.
 */
function SkeletonPanel({ rowKeys }: SkeletonPanelProps) {
  return (
    <Panel>
      <PanelSection>
        <Skeleton width="third" />
      </PanelSection>
      <PanelSection>
        {rowKeys.map((key) => (
          <Skeleton key={key} width="half" />
        ))}
      </PanelSection>
    </Panel>
  );
}
