/**
 * The reply area of a closed ticket (console UI design, Closed state): the sent reply, read-only,
 * with who sent it and when. Text is rendered as text (SEC-22).
 */
import { CircleCheck } from "lucide-react";

import { Panel, PanelHeader, PanelSection, RelativeTime, Text } from "@/design-system";
import type { SentReply } from "@/features/console-tickets/model/workspace";

/** Props of {@link SentReplyPanel}. */
type SentReplyPanelProps = {
  readonly reply: SentReply;
};

/**
 * Render the sent reply.
 *
 * @param props - The reply.
 * @returns The panel.
 */
export function SentReplyPanel({ reply }: SentReplyPanelProps) {
  return (
    <Panel density="compact" as="section" label="Reply sent">
      <PanelHeader
        icon={CircleCheck}
        level={2}
        title="Reply sent"
        trailing={
          <Text tone="muted">
            {reply.sentByName} · <RelativeTime timestamp={reply.sentAt} />
          </Text>
        }
      />
      <PanelSection>
        <Text overflow="preserve">{reply.body}</Text>
      </PanelSection>
    </Panel>
  );
}
