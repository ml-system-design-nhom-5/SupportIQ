/**
 * The action bar of the reply area (UI-16; console UI design, Actions and placement rule 2): the
 * actions of the state and Escalate ticket on the left, the main action on the right, and one line
 * above them that says why the main action is disabled, or a note. The main action is Send reply,
 * which opens the confirmation; nothing is sent without it (UI-17, FR-04). When authority is
 * required, Submit for approval replaces it; otherwise Submit for approval sits in the More menu,
 * and in manual handling it is a visible button. A failed send or submission shows its banner
 * above the bar.
 */
import { CircleArrowUp, Clock, Send } from "lucide-react";
import type { ReactNode } from "react";

import { ActionBar, type ActionMenuItem, Button, PanelSection } from "@/design-system";
import { FailureViewBanner } from "@/features/console-tickets/components/failure-view-banner";
import type { ReplyComposer } from "@/features/console-tickets/components/use-reply-composer";

/** Where Submit for approval sits: the main action, a visible button, or an item of More. */
type SubmitPlace = "primary" | "button" | "menu";

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
 * @returns The failure banner of the last send or submission, when there is one, and the bar.
 */
export function ReplyActionBar({ composer, actions }: ReplyActionBarProps) {
  const failure = composer.submitFailure ?? composer.sendFailure;
  const submitPlace = getSubmitPlace(composer);
  return (
    <>
      {failure === undefined ? null : (
        <PanelSection>
          <FailureViewBanner failure={failure} />
        </PanelSection>
      )}
      <ActionBar
        {...(composer.barLine === undefined ? {} : { reason: composer.barLine })}
        actions={
          <>
            {actions}
            <Button
              leadingIcon={CircleArrowUp}
              disabled={!composer.escalation.canEscalate}
              onClick={(event) => {
                composer.escalation.open(event.currentTarget);
              }}
            >
              Escalate ticket
            </Button>
            {submitPlace === "button" ? <SubmitButton composer={composer} /> : null}
          </>
        }
        moreItems={submitPlace === "menu" ? [toSubmitMenuItem(composer)] : []}
        primaryAction={
          submitPlace === "primary" ? (
            <SubmitButton composer={composer} isPrimary />
          ) : (
            <Button
              variant="primary"
              leadingIcon={Send}
              disabled={composer.primaryBlock !== undefined}
              onClick={(event) => {
                composer.askToSend(event.currentTarget);
              }}
            >
              Send reply
            </Button>
          )
        }
      />
    </>
  );
}

/**
 * Render Submit for approval as a button.
 *
 * @param props - The composer, and whether it is the main action.
 * @returns The button.
 */
function SubmitButton({
  composer,
  isPrimary = false,
}: {
  readonly composer: ReplyComposer;
  readonly isPrimary?: boolean;
}) {
  return (
    <Button
      variant={isPrimary ? "primary" : "secondary"}
      leadingIcon={Clock}
      disabled={composer.submitBlock !== undefined}
      isPending={composer.isSubmitting}
      onClick={composer.submit}
    >
      Submit for approval
    </Button>
  );
}

/**
 * Choose where Submit for approval sits (UI-16).
 *
 * @param composer - The composer.
 * @returns The main action when it replaces Send reply, a visible button in manual handling, and
 *   an item of More otherwise.
 */
function getSubmitPlace(composer: ReplyComposer): SubmitPlace {
  if (composer.primaryAction === "submit_reply_proposal") {
    return "primary";
  }
  return composer.isManualHandling ? "button" : "menu";
}

/**
 * Describe Submit for approval as an item of More (action-menu.png).
 *
 * @param composer - The composer.
 * @returns The item, disabled while the submission is blocked or sending.
 */
function toSubmitMenuItem(composer: ReplyComposer): ActionMenuItem {
  return {
    icon: Clock,
    label: "Submit for approval",
    description: "A manager sends the reply",
    isDisabled: composer.submitBlock !== undefined || composer.isSubmitting,
    onSelect: composer.submit,
  };
}
