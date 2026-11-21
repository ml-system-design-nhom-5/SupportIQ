/**
 * The AI sidebar while the analysis is pending or the ticket loads (UI-24): skeleton panels in the
 * place of the recommendation and the sources.
 */
import { Panel, PanelSection, Skeleton, VisuallyHidden } from "@/design-system";

/**
 * Render the sidebar while the analysis is pending (UI-24).
 *
 * @returns Skeleton panels.
 */
export function SidebarLoading() {
  return (
    <>
      <Panel density="compact" as="section" label="AI recommendation" tone="ai">
        <PanelSection>
          <p role="status">
            <VisuallyHidden>Loading the AI recommendation…</VisuallyHidden>
          </p>
          <Skeleton width="half" />
          <Skeleton width="full" />
        </PanelSection>
      </Panel>
      <Panel density="compact" as="section" label="Sources">
        <PanelSection>
          <Skeleton width="three-quarters" />
          <Skeleton width="full" />
        </PanelSection>
      </Panel>
    </>
  );
}
