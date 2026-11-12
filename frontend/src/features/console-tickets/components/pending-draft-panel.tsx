/**
 * The reply area while the draft is generating (UI-22, UI-24; console UI design, Partial state):
 * a skeleton labeled "Generating draft". The analysis shows as soon as it is ready.
 */
import { Sparkles } from "lucide-react";

import {
  Panel,
  PanelHeader,
  PanelSection,
  presentationByAiStatus,
  Skeleton,
  StatusBadge,
  VisuallyHidden,
} from "@/design-system";

/**
 * Render the skeleton of the draft.
 *
 * @returns The panel, announced as a status.
 */
export function PendingDraftPanel() {
  return (
    <Panel density="compact" as="section" label="AI draft" tone="ai">
      <PanelHeader
        icon={Sparkles}
        level={2}
        title="AI draft"
        trailing={<StatusBadge presentation={presentationByAiStatus.pending} />}
      />
      <PanelSection>
        <p role="status">
          <VisuallyHidden>The AI is still working on this ticket.</VisuallyHidden>
        </p>
        <Skeleton width="full" />
        <Skeleton width="three-quarters" />
        <Skeleton width="half" />
      </PanelSection>
    </Panel>
  );
}
