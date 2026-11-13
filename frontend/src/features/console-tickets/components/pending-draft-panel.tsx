/**
 * The reply area while the draft is generating (UI-22, UI-24; console UI design, Partial and
 * Intent changed states): a skeleton labeled "Generating draft". After an intent correction, the
 * previous draft stays above the skeleton, marked "Outdated", so staff see what is being replaced.
 * The analysis shows as soon as it is ready.
 */
import { Sparkles } from "lucide-react";
import type { ReactNode } from "react";

import {
  Panel,
  PanelHeader,
  PanelSection,
  presentationByAiStatus,
  Skeleton,
  Stack,
  StatusBadge,
  Tag,
  VisuallyHidden,
} from "@/design-system";
import { CitedDraft, type MarkerContext } from "@/features/console-tickets/components/cited-draft";
import type { ReadyDraft } from "@/features/console-tickets/model/draft";
import { numberCitedDocuments } from "@/features/console-tickets/model/sources";

/** Props of {@link PendingDraftPanel}. */
type PendingDraftPanelProps = {
  /** The draft that an intent correction made outdated; undefined when there is none. */
  readonly outdatedDraft: ReadyDraft | undefined;
  /** What the markers of the outdated draft need. */
  readonly markerContext: MarkerContext;
  /** The action bar of the reply, disabled while the AI works. */
  readonly children?: ReactNode;
};

/**
 * Render the skeleton of the draft, below the outdated draft when there is one.
 *
 * @param props - The outdated draft, what its markers need, and the action bar.
 * @returns The panel, announced as a status.
 */
export function PendingDraftPanel({
  outdatedDraft,
  markerContext,
  children,
}: PendingDraftPanelProps) {
  return (
    <Panel density="compact" as="section" label="AI draft" tone="ai">
      <PanelHeader
        icon={Sparkles}
        level={2}
        title="AI draft"
        trailing={<StatusBadge presentation={presentationByAiStatus.pending} />}
      />
      {outdatedDraft === undefined ? null : (
        <PanelSection>
          <Stack as="section" label="Outdated draft" gap="2" align="start">
            <Tag tone="neutral">Outdated</Tag>
            <CitedDraft
              draft={outdatedDraft}
              numberByKey={numberCitedDocuments(outdatedDraft)}
              sourceByKey={markerContext.sourceByKey}
              orderId={markerContext.orderId}
              onOpenSource={markerContext.onOpenSource}
              onOpenOrder={markerContext.onOpenOrder}
            />
          </Stack>
        </PanelSection>
      )}
      <PanelSection>
        <p role="status">
          <VisuallyHidden>The AI is still working on this ticket.</VisuallyHidden>
        </p>
        <Skeleton width="full" />
        <Skeleton width="three-quarters" />
        <Skeleton width="half" />
      </PanelSection>
      {children}
    </Panel>
  );
}
