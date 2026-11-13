/**
 * The action bar of the reply area (UI-16; console UI design, placement rule 2): the actions of the
 * state on the left, Send reply on the right, and one line above them that says why Send reply is
 * disabled. Send reply opens the confirmation; nothing is sent without it (UI-17, FR-04). A failed
 * send shows its banner above the bar.
 */
import { Send } from "lucide-react";
import type { ReactNode } from "react";

import { ActionBar, Button, PanelSection } from "@/design-system";
import { SendFailureBanner } from "@/features/console-tickets/components/send-failure-banner";
import type { ReplyComposer } from "@/features/console-tickets/components/use-reply-composer";

/** Props of {@link ReplyActionBar}. */
type ReplyActionBarProps = {
  readonly composer: ReplyComposer;
  /** The actions of the state, such as Edit draft and Reject draft. */
  readonly actions?: ReactNode;
};

/**
 * Render the action bar.
 *
 * @param props - The composer and the actions of the state.
 * @returns The failure banner of the last send, when there is one, and the bar.
 */
export function ReplyActionBar({ composer, actions }: ReplyActionBarProps) {
  const { sendBlock, sendFailure } = composer;
  return (
    <>
      {sendFailure === undefined ? null : (
        <PanelSection>
          <SendFailureBanner failure={sendFailure} />
        </PanelSection>
      )}
      <ActionBar
        {...(sendBlock === undefined ? {} : { reason: sendBlock })}
        actions={actions}
        primaryAction={
          <Button
            variant="primary"
            leadingIcon={Send}
            disabled={sendBlock !== undefined}
            onClick={(event) => {
              composer.askToSend(event.currentTarget);
            }}
          >
            Send reply
          </Button>
        }
      />
    </>
  );
}
