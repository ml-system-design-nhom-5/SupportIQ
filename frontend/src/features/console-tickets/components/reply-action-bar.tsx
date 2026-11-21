/**
 * The action bar of the reply area (UI-16; console UI design, Actions and placement rule 2): the
 * actions of the state and Escalate ticket on the left, the main action on the right, and one line
 * above them that says why the main action is disabled, or a note. The main action is Send reply,
 * which opens the confirmation; nothing is sent without it (UI-17, FR-04). When authority is
 * required, Submit for approval replaces it; otherwise Submit for approval sits in the More menu,
 * and in manual handling it is a visible button. A failed send or submission shows its banner
 * above the bar, and a send that a colleague's action refused shows its text under the banner.
 */
import { CircleArrowUp, Clock, Send } from "lucide-react";
import type { ReactNode } from "react";

import {
  ActionBar,
  type ActionMenuItem,
  Button,
  CopyableText,
  PanelSection,
} from "@/design-system";
import { FailureViewBanner } from "@/features/console-tickets/components/failure-view-banner";
import type { ReplyComposer } from "@/features/console-tickets/components/use-reply-composer";
import type { ReplyFailureView } from "@/features/console-tickets/model/reply-failure";

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
  const submitPlace = getSubmitPlace(composer);
  return (
    <>
      {composer.failure === undefined ? null : (
        <FailureSection failure={composer.failure} unsentText={composer.unsentText} />
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
            {submitPlace === "button" ? (
              <SubmitButton composer={composer} variant="secondary" />
            ) : null}
          </>
        }
        moreItems={submitPlace === "menu" ? [toSubmitMenuItem(composer)] : []}
        isMoreDisabled={!composer.canSubmit}
        primaryAction={
          submitPlace === "primary" ? (
            <SubmitButton composer={composer} variant="primary" />
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
 * Render the failure of the last write, and under it the text of a send that a colleague's action
 * refused (console UI design, Flow, step 6).
 *
 * @param props - The failure, and the unsent text when there is one.
 * @returns The section.
 */
function FailureSection({
  failure,
  unsentText,
}: {
  readonly failure: ReplyFailureView;
  readonly unsentText: string | undefined;
}) {
  return (
    <PanelSection>
      <FailureViewBanner failure={failure} />
      {unsentText === undefined ? null : (
        <CopyableText label="Your unsent text">{unsentText}</CopyableText>
      )}
    </PanelSection>
  );
}

/**
 * Render Submit for approval as a button.
 *
 * @param props - The composer, and the variant: `primary` when it is the main action.
 * @returns The button.
 */
function SubmitButton({
  composer,
  variant,
}: {
  readonly composer: ReplyComposer;
  readonly variant: "primary" | "secondary";
}) {
  return (
    <Button
      variant={variant}
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
 * @returns The item, disabled while the submission is blocked. A press while it is sending does
 *   nothing, because the submission ignores it.
 */
function toSubmitMenuItem(composer: ReplyComposer): ActionMenuItem {
  return {
    icon: Clock,
    label: "Submit for approval",
    description: "A manager sends the reply",
    isDisabled: composer.submitBlock !== undefined,
    onSelect: composer.submit,
  };
}
