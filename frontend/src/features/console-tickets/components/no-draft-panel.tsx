/**
 * The reply area when the AI made no draft (console UI design, States): "No draft is created until
 * you choose an intent" after an abstention for low confidence (UI-42), otherwise the reason codes
 * of the abstention (ESC-02, ESC-04) or of the escalation recommendation (ESC-03). The area shows
 * no draft and no filler text.
 */
import { PenLine, Sparkles } from "lucide-react";

import {
  Cluster,
  Panel,
  PanelHeader,
  PanelSection,
  presentationByAiReasonCode,
  presentationByAiStatus,
  StatusBadge,
  Text,
} from "@/design-system";
import type { NoDraftReplyState } from "@/features/console-tickets/model/workspace-state";

/** Props of {@link NoDraftPanel}. */
type NoDraftPanelProps = {
  readonly outcome: NoDraftReplyState;
};

/**
 * Render the reply area without a draft.
 *
 * @param props - The outcome.
 * @returns The panel.
 */
export function NoDraftPanel({ outcome }: NoDraftPanelProps) {
  if (outcome.kind === "choose_intent") {
    return (
      <Panel density="compact" as="section" label="AI draft">
        <PanelHeader icon={Sparkles} level={2} title="AI draft" />
        <PanelSection layout="centered">
          <Text tone="muted">No draft is created until you choose an intent.</Text>
        </PanelSection>
      </Panel>
    );
  }
  const isEscalation = outcome.status === "escalation_recommended";
  return (
    <Panel density="compact" as="section" label="Reply">
      <PanelHeader
        icon={PenLine}
        level={2}
        title="Reply"
        trailing={<StatusBadge presentation={presentationByAiStatus[outcome.status]} />}
      />
      <PanelSection>
        <Text>
          {isEscalation
            ? "The AI recommends an escalation. You decide whether a manager is needed."
            : "The AI made no draft for this ticket."}
        </Text>
        <Cluster>
          {outcome.reasonCodes.map((reasonCode) => (
            <StatusBadge key={reasonCode} presentation={presentationByAiReasonCode[reasonCode]} />
          ))}
        </Cluster>
      </PanelSection>
    </Panel>
  );
}
