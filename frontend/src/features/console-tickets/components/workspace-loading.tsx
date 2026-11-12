/**
 * The workspace while the ticket loads (UI-24; console UI design, state-loading.png): skeletons in
 * the header, the message, the intent, the reply area, and the AI sidebar. Only the workspace
 * waits; the inbox stays usable.
 */
import {
  Panel,
  PanelSection,
  Skeleton,
  TicketHeaderSkeleton,
  VisuallyHidden,
  WorkspaceLayout,
} from "@/design-system";
import { SidebarLoading } from "@/features/console-tickets/components/sidebar-loading";

/**
 * Render the loading workspace.
 *
 * @returns The workspace of skeletons, announced as loading.
 */
export function WorkspaceLoading() {
  return (
    <WorkspaceLayout
      header={<TicketHeaderSkeleton />}
      main={
        <>
          <p role="status">
            <VisuallyHidden>Loading the ticket…</VisuallyHidden>
          </p>
          <Panel density="compact">
            <PanelSection>
              <Skeleton width="full" />
              <Skeleton width="half" />
            </PanelSection>
          </Panel>
          <Panel density="compact" tone="ai">
            <PanelSection>
              <Skeleton width="half" />
            </PanelSection>
          </Panel>
          <Panel density="compact" tone="ai">
            <PanelSection>
              <Skeleton width="full" />
              <Skeleton width="three-quarters" />
              <Skeleton width="half" />
            </PanelSection>
          </Panel>
        </>
      }
      sidebar={<SidebarLoading />}
    />
  );
}
