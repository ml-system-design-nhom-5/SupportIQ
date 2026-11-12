/**
 * The reply area of the workspace in its state (console UI design, States). The editor and the
 * action bar come with the reply actions.
 */
import { assertNever } from "@/features/backend-requests";
import { CitedDraft, type MarkerContext } from "@/features/console-tickets/components/cited-draft";
import { DraftPanel } from "@/features/console-tickets/components/draft-panel";
import { ManualHandlingPanel } from "@/features/console-tickets/components/manual-handling-panel";
import { NoDraftPanel } from "@/features/console-tickets/components/no-draft-panel";
import { PendingDraftPanel } from "@/features/console-tickets/components/pending-draft-panel";
import { SentReplyPanel } from "@/features/console-tickets/components/sent-reply-panel";
import { describeAiUnavailable } from "@/features/console-tickets/model/manual-handling";
import type { SuggestionWarning } from "@/features/console-tickets/model/reason-codes";
import type { ReplyAreaState } from "@/features/console-tickets/model/workspace-state";

/** Props of {@link ReplyArea}. */
type ReplyAreaProps = {
  readonly state: ReplyAreaState;
  /** What a draft needs: its warnings, its time, its citation numbers, and its markers. */
  readonly draftContext: MarkerContext & {
    readonly warnings: readonly SuggestionWarning[];
    readonly generatedAt: string;
    readonly numberByKey: ReadonlyMap<string, number>;
  };
};

/**
 * Render the reply area.
 *
 * @param props - The state and what a draft needs.
 * @returns The panel of the state.
 */
export function ReplyArea({ state, draftContext }: ReplyAreaProps) {
  switch (state.kind) {
    case "sent":
      return <SentReplyPanel reply={state.reply} />;
    case "manual_mode":
      return <ManualHandlingPanel aiStatus="manual" />;
    case "ai_unavailable":
      return (
        <ManualHandlingPanel
          aiStatus="unavailable"
          reason={describeAiUnavailable(state.reasonCode)}
        />
      );
    case "pending":
      return <PendingDraftPanel />;
    case "draft": {
      const { warnings, generatedAt, ...citedDraftContext } = draftContext;
      return (
        <DraftPanel warnings={warnings} generatedAt={generatedAt}>
          <CitedDraft draft={state.draft} {...citedDraftContext} />
        </DraftPanel>
      );
    }
    case "choose_intent":
    case "no_draft":
      return <NoDraftPanel outcome={state} />;
    default:
      assertNever(state);
  }
}
