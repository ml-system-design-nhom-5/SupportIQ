/**
 * The escalation of a ticket in the reply area (console UI design, States, Escalated;
 * state-escalated.png): who escalated it and when, the staff reason codes, and the note, above the
 * editor of the manager. Staff see it read-only, because an escalated ticket is read-only for them
 * (dialog-escalate.png). Text is rendered as text (SEC-22).
 */
import { CircleArrowUp } from "lucide-react";
import type { ReactNode } from "react";

import {
  Cluster,
  Panel,
  PanelHeader,
  type PanelHeight,
  PanelSection,
  RelativeTime,
  Tag,
  Text,
} from "@/design-system";
import type { TicketEscalation } from "@/features/console-tickets/model/manager-handoff";
import { staffReasonCodeLabels } from "@/features/console-tickets/model/staff-reason-codes";

/** The ID of the heading, which takes the focus once staff escalated the ticket (UI-30). */
export const ESCALATED_HEADING_ID = "escalated-heading";

/** Props of {@link EscalatedPanel}. */
type EscalatedPanelProps = {
  readonly escalation: TicketEscalation;
  /** `fill` when the panel is the reply area; `content` above a draft. */
  readonly height: PanelHeight;
  /** The editor and the action bar; absent above a draft. */
  readonly children?: ReactNode;
};

/**
 * Render the escalation.
 *
 * @param props - The escalation, the height of the panel, and the editor with the action bar.
 * @returns The panel.
 */
export function EscalatedPanel({ escalation, height, children }: EscalatedPanelProps) {
  const title = `Escalated by ${escalation.escalatedByName}`;
  return (
    <Panel density="compact" height={height} as="section" label={title}>
      <PanelHeader
        icon={CircleArrowUp}
        level={2}
        title={title}
        focusTargetId={ESCALATED_HEADING_ID}
        trailing={
          <Text tone="muted">
            <RelativeTime timestamp={escalation.escalatedAt} />
          </Text>
        }
      />
      <PanelSection>
        <Cluster>
          {escalation.reasonCodes.map((reasonCode) => (
            <Tag key={reasonCode} tone="neutral">
              {staffReasonCodeLabels[reasonCode]}
            </Tag>
          ))}
        </Cluster>
        {escalation.note === undefined ? null : <Text overflow="preserve">{escalation.note}</Text>}
      </PanelSection>
      {children}
    </Panel>
  );
}
