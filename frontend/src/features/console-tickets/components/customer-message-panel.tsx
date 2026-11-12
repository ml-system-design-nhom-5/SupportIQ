/**
 * The customer message (console UI design, Workspace regions): the text exactly as written, as
 * plain text (SEC-22), with the customer and the time.
 */
import { MessageSquare } from "lucide-react";

import { Panel, PanelHeader, PanelSection, RelativeTime, Text } from "@/design-system";

/** Props of {@link CustomerMessagePanel}. */
type CustomerMessagePanelProps = {
  readonly customerName: string;
  readonly body: string;
  /** When the customer sent it, as an RFC 3339 timestamp. */
  readonly sentAt: string;
};

/**
 * Render the customer message.
 *
 * @param props - The customer, the text, and the time.
 * @returns The panel.
 */
export function CustomerMessagePanel({ customerName, body, sentAt }: CustomerMessagePanelProps) {
  return (
    <Panel density="compact" as="section" label="Customer message">
      <PanelHeader icon={MessageSquare} level={2} title="Customer message" />
      <PanelSection>
        <Text overflow="preserve">{body}</Text>
        <Text tone="muted">
          {customerName} · <RelativeTime timestamp={sentAt} />
        </Text>
      </PanelSection>
    </Panel>
  );
}
