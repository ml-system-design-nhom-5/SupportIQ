/**
 * The reply area in manual handling (UI-26; console UI design, AI unavailable and Manual mode):
 * the manual-process instructions and the reminder to route refund decisions and disputes to a
 * manager. Every non-AI tool keeps working.
 */
import { User } from "lucide-react";
import type { ReactNode } from "react";

import {
  type AiStatusName,
  Panel,
  PanelHeader,
  PanelSection,
  presentationByAiStatus,
  StatusBadge,
  StatusBanner,
  Text,
} from "@/design-system";
import {
  MANUAL_PROCESS_INSTRUCTIONS,
  MANUAL_REMINDER_LEAD,
  MANUAL_REMINDER_TEXT,
} from "@/features/console-tickets/model/manual-handling";

/** Props of {@link ManualHandlingPanel}. */
type ManualHandlingPanelProps = {
  /** `unavailable` after an AI failure, `manual` for a ticket in manual mode. */
  readonly aiStatus: Extract<AiStatusName, "unavailable" | "manual">;
  /** Why the AI did not help, after an AI failure. */
  readonly reason?: string;
  /** The editor and the action bar of the reply. */
  readonly children?: ReactNode;
};

/**
 * Render the manual-handling panel.
 *
 * @param props - The AI status, the reason, and the editor with the action bar.
 * @returns The panel.
 */
export function ManualHandlingPanel({ aiStatus, reason, children }: ManualHandlingPanelProps) {
  return (
    <Panel density="compact" as="section" label="Manual handling">
      <PanelHeader
        icon={User}
        level={2}
        title="Manual handling"
        trailing={<StatusBadge presentation={presentationByAiStatus[aiStatus]} />}
      />
      <PanelSection>
        {reason === undefined ? null : <Text>{reason}</Text>}
        <Text>{MANUAL_PROCESS_INSTRUCTIONS}</Text>
        <StatusBanner tone="warning" lead={MANUAL_REMINDER_LEAD}>
          {MANUAL_REMINDER_TEXT}
        </StatusBanner>
      </PanelSection>
      {children}
    </Panel>
  );
}
