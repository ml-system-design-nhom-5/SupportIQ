/**
 * The reply area of the workspace in its state (console UI design, States and Actions): the panel
 * of the state, which fills the rest of the column, with the editor when staff may write and the
 * action bar at its bottom (UI-15, UI-16, placement rule 2). A closed ticket keeps the bar with
 * every action disabled and the reason. A ticket awaiting approval shows the proposal next to the
 * AI draft, and an escalated ticket shows its escalation above the editor (console UI design,
 * States).
 * Send reply opens the confirmation, which the workspace shows (UI-17).
 */
import { RotateCcw } from "lucide-react";

import { Button, PanelSection } from "@/design-system";
import { assertNever, type RequestFailure } from "@/features/backend-requests";
import type { SuggestionRequests } from "@/features/console-tickets/api/use-create-suggestion";
import { DraftModeActions } from "@/features/console-tickets/components/draft-mode-actions";
import {
  type DraftContext,
  DraftReplyPanel,
} from "@/features/console-tickets/components/draft-reply-panel";
import { EscalatedPanel } from "@/features/console-tickets/components/escalated-panel";
import { FailureViewBanner } from "@/features/console-tickets/components/failure-view-banner";
import { ManualHandlingPanel } from "@/features/console-tickets/components/manual-handling-panel";
import { NoDraftPanel } from "@/features/console-tickets/components/no-draft-panel";
import { PendingDraftPanel } from "@/features/console-tickets/components/pending-draft-panel";
import { ProposalPanel } from "@/features/console-tickets/components/proposal-panel";
import { ReplyActionBar } from "@/features/console-tickets/components/reply-action-bar";
import { ReplyEditorSection } from "@/features/console-tickets/components/reply-editor-section";
import { SentReplyPanel } from "@/features/console-tickets/components/sent-reply-panel";
import type { ReplyComposer } from "@/features/console-tickets/components/use-reply-composer";
import type { TicketEscalation } from "@/features/console-tickets/model/manager-handoff";
import { describeAiUnavailable } from "@/features/console-tickets/model/manual-handling";
import { describeSuggestionFailure } from "@/features/console-tickets/model/suggestion-failure";
import type { ReplyAreaState } from "@/features/console-tickets/model/workspace-state";

/** What the reply area needs of the requests to the AI: Try AI again and the outdated draft. */
export type AiRequests = Pick<
  SuggestionRequests,
  "retry" | "isSending" | "retryFailure" | "outdatedDraft"
> & {
  /** True when `backend` allows Try AI again (`retry_suggestion`). */
  readonly canRetry: boolean;
};

/** Props of {@link ReplyArea}. */
type ReplyAreaProps = {
  readonly state: ReplyAreaState;
  readonly draftContext: DraftContext;
  readonly composer: ReplyComposer;
  readonly aiRequests: AiRequests;
  /** The escalation of an escalated ticket, shown above a reply area that does not show it. */
  readonly escalation?: TicketEscalation;
};

/** The states of the reply area that follow the current suggestion. */
type SuggestionReplyAreaState = Exclude<
  ReplyAreaState,
  { readonly kind: "sent" | "proposal" | "escalated" }
>;

/**
 * Render the reply area.
 *
 * @param props - The state, what a draft needs, the composer, the requests to the AI, and the
 *   escalation of an escalated ticket.
 * @returns The panel of the state.
 */
export function ReplyArea(props: ReplyAreaProps) {
  const { state, escalation } = props;
  if (state.kind === "sent" || state.kind === "proposal" || state.kind === "escalated") {
    return <HandedOverReplyArea {...props} state={state} />;
  }
  return (
    <>
      {escalation === undefined ? null : (
        <EscalatedPanel escalation={escalation} height="content" />
      )}
      <SuggestionReplyArea {...props} state={state} />
    </>
  );
}

/**
 * Render the reply area of a ticket that is closed or handed to a manager.
 *
 * @param props - The state, what a draft needs, and the composer.
 * @returns The sent reply, the proposal, or the escalation.
 */
function HandedOverReplyArea({
  state,
  draftContext,
  composer,
}: ReplyAreaProps & { readonly state: Exclude<ReplyAreaState, SuggestionReplyAreaState> }) {
  switch (state.kind) {
    case "sent":
      return (
        <SentReplyPanel reply={state.reply}>
          <ReplyActionBar composer={composer} actions={<UnavailableDraftActions />} />
        </SentReplyPanel>
      );
    case "proposal":
      return <ProposalPanel composer={composer} state={state} context={draftContext} />;
    case "escalated":
      return (
        <EscalatedPanel escalation={state.escalation} height="fill">
          {composer.canWrite ? (
            <WritingTools composer={composer} />
          ) : (
            <ReplyActionBar composer={composer} actions={<UnavailableDraftActions />} />
          )}
        </EscalatedPanel>
      );
    default:
      assertNever(state);
  }
}

/**
 * Render the reply area of the current suggestion.
 *
 * @param props - The state, what a draft needs, the composer, and the requests to the AI.
 * @returns The panel of the state.
 */
function SuggestionReplyArea({
  state,
  draftContext,
  composer,
  aiRequests,
}: ReplyAreaProps & { readonly state: SuggestionReplyAreaState }) {
  switch (state.kind) {
    case "manual_mode":
      return (
        <ManualHandlingPanel aiStatus="manual">
          <WritingTools composer={composer} />
        </ManualHandlingPanel>
      );
    case "ai_unavailable":
      return (
        <ManualHandlingPanel
          aiStatus="unavailable"
          reason={describeAiUnavailable(state.reasonCode)}
        >
          <WritingTools composer={composer} aiRequests={aiRequests} />
        </ManualHandlingPanel>
      );
    case "pending":
      return (
        <PendingDraftPanel
          outdatedDraft={aiRequests.outdatedDraft}
          markerContext={draftContext.citations}
        >
          <ReplyActionBar composer={composer} actions={<UnavailableDraftActions />} />
        </PendingDraftPanel>
      );
    case "draft":
      return <DraftReplyPanel composer={composer} draft={state.draft} context={draftContext} />;
    case "choose_intent":
      return (
        <NoDraftPanel outcome={state}>
          <ReplyActionBar composer={composer} actions={<UnavailableDraftActions />} />
        </NoDraftPanel>
      );
    case "no_draft":
      return (
        <NoDraftPanel outcome={state}>
          <WritingTools composer={composer} />
        </NoDraftPanel>
      );
    default:
      assertNever(state);
  }
}

/**
 * Render the editor and the action bar of a reply without a draft. After an AI failure, Try AI
 * again sits on the left when `backend` allows it (UI-26).
 *
 * @param props - The composer, and the requests to the AI after a failure.
 * @returns The editor, the failure of the last retry, and the action bar.
 */
function WritingTools({
  composer,
  aiRequests,
}: {
  readonly composer: ReplyComposer;
  readonly aiRequests?: AiRequests;
}) {
  return (
    <>
      <ReplyEditorSection
        value={composer.state.body}
        onChange={(body) => {
          composer.change((current) => ({ ...current, body }));
        }}
      />
      {aiRequests?.retryFailure === undefined ? null : (
        <RetryFailureBanner failure={aiRequests.retryFailure} />
      )}
      <ReplyActionBar
        composer={composer}
        actions={
          aiRequests?.canRetry === true ? (
            <Button
              leadingIcon={RotateCcw}
              isPending={aiRequests.isSending}
              onClick={aiRequests.retry}
            >
              Try AI again
            </Button>
          ) : null
        }
      />
    </>
  );
}

/**
 * Render Edit draft and Reject draft, disabled, while no draft is ready: the AI still works, staff
 * choose an intent first, or the ticket is closed.
 *
 * @returns The disabled buttons.
 */
function UnavailableDraftActions() {
  return <DraftModeActions mode="viewing" canChange={false} />;
}

/**
 * Say what happened to Try AI again when it failed (UI-25). After an unknown outcome, it never says
 * that the AI did not start (ERR-16).
 *
 * @param props - The failure of the retry.
 * @returns The banner, announced as an alert.
 */
function RetryFailureBanner({ failure }: { readonly failure: RequestFailure }) {
  return (
    <PanelSection>
      <FailureViewBanner failure={describeSuggestionFailure(failure, "retry")} />
    </PanelSection>
  );
}
