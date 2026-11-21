/**
 * The AI recommendation (console UI design, Workspace regions; UI-13): what the AI recommends and
 * its reason codes, marked as an AI suggestion. Staff and managers decide. When drafting failed
 * after the analysis, the panel also says that the AI is unavailable, with the reason.
 */
import { Sparkles } from "lucide-react";

import {
  type AiReasonCodeName,
  Cluster,
  Panel,
  PanelHeader,
  PanelSection,
  presentationByAiReasonCode,
  presentationByAiStatus,
  presentationByRecommendation,
  type RecommendationName,
  StatusBadge,
  Tag,
  Text,
} from "@/design-system";

/** Props of {@link RecommendationPanel}. */
type RecommendationPanelProps = {
  readonly recommendation: RecommendationName;
  readonly reasonCodes: readonly AiReasonCodeName[];
  /** The reason of a draft that failed after the analysis. */
  readonly draftFailure?: AiReasonCodeName;
};

/**
 * Render the recommendation.
 *
 * @param props - The recommendation, its reason codes, and the failure of the draft.
 * @returns The panel.
 */
export function RecommendationPanel({
  recommendation,
  reasonCodes,
  draftFailure,
}: RecommendationPanelProps) {
  return (
    <Panel density="compact" as="section" label="AI recommendation" tone="ai">
      <PanelHeader
        icon={Sparkles}
        level={2}
        title="AI recommendation"
        trailing={<Tag tone="ai">AI suggestion</Tag>}
      />
      <PanelSection>
        <Cluster>
          <StatusBadge presentation={presentationByRecommendation[recommendation]} />
          {reasonCodes.length === 0 ? (
            <Text tone="muted">No escalation reason</Text>
          ) : (
            reasonCodes.map((reasonCode) => (
              <StatusBadge key={reasonCode} presentation={presentationByAiReasonCode[reasonCode]} />
            ))
          )}
        </Cluster>
        {draftFailure === undefined ? null : (
          <Cluster>
            <StatusBadge presentation={presentationByAiStatus.unavailable} />
            <StatusBadge presentation={presentationByAiReasonCode[draftFailure]} />
          </Cluster>
        )}
      </PanelSection>
    </Panel>
  );
}
