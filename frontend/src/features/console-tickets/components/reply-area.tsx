/**
 * The reply area of the workspace in its state (console UI design, States). The editor and the
 * action bar come with the reply actions.
 */
import { assertNever } from "@/features/backend-requests";
import { DraftPanel } from "@/features/console-tickets/components/draft-panel";
import { ManualHandlingPanel } from "@/features/console-tickets/components/manual-handling-panel";
import { NoDraftPanel } from "@/features/console-tickets/components/no-draft-panel";
import { PendingDraftPanel } from "@/features/console-tickets/components/pending-draft-panel";
import { SentReplyPanel } from "@/features/console-tickets/components/sent-reply-panel";
import { describeAiUnavailable } from "@/features/console-tickets/model/manual-handling";
import type { SuggestionWarning } from "@/features/console-tickets/model/reason-codes";
import type { Source, SourceSelection } from "@/features/console-tickets/model/sources";
import type { ReplyAreaState } from "@/features/console-tickets/model/workspace-state";

/** Props of {@link ReplyArea}. */
type ReplyAreaProps = {
  readonly state: ReplyAreaState;
  /** What a draft needs: its warnings, its time, its sources, and its marker handlers. */
  readonly draftContext: {
    readonly warnings: readonly SuggestionWarning[];
    readonly generatedAt: string;
    readonly numberByKey: ReadonlyMap<string, number>;
    readonly sourceByKey: ReadonlyMap<string, Source>;
    /** The ID of the ticket's order; undefined when the ticket has none. */
    readonly orderId: string | undefined;
    readonly onOpenSource: (selection: SourceSelection, opener: HTMLElement) => void;
    readonly onOpenOrder: () => void;
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
    case "draft":
      return <DraftPanel draft={state.draft} {...draftContext} />;
    case "choose_intent":
    case "no_draft":
      return <NoDraftPanel outcome={state} />;
    default:
      assertNever(state);
  }
}
