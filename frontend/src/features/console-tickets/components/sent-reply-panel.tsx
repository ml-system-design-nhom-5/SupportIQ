/**
 * The reply area of a closed ticket (console UI design, Closed state; state-closed.png): the sent
 * reply, read-only, with who sent it and when, above the action bar whose actions are disabled with
 * the reason. Text is rendered as text (SEC-22).
 */
import { CircleCheck } from "lucide-react";
import type { ReactNode } from "react";

import { Panel, PanelHeader, PanelSection, RelativeTime, Text } from "@/design-system";
import type { SentReply } from "@/features/console-tickets/model/workspace";

/** The ID of the heading, which takes the focus once staff sent the reply (UI-30). */
export const SENT_REPLY_HEADING_ID = "reply-sent-heading";

/** Props of {@link SentReplyPanel}. */
type SentReplyPanelProps = {
  readonly reply: SentReply;
  /** The action bar, with every action disabled. */
  readonly children?: ReactNode;
};

/**
 * Render the sent reply.
 *
 * @param props - The reply and the action bar.
 * @returns The panel.
 */
export function SentReplyPanel({ reply, children }: SentReplyPanelProps) {
  return (
    <Panel density="compact" height="fill" as="section" label="Reply sent">
      <PanelHeader
        icon={CircleCheck}
        level={2}
        title="Reply sent"
        focusTargetId={SENT_REPLY_HEADING_ID}
        trailing={
          <Text tone="muted">
            {reply.sentByName} · <RelativeTime timestamp={reply.sentAt} />
          </Text>
        }
      />
      <PanelSection>
        <Text overflow="preserve">{reply.body}</Text>
      </PanelSection>
      {children}
    </Panel>
  );
}
