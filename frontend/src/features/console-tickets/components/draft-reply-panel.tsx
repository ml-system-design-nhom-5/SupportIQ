/**
 * The reply area with a ready draft (console UI design, Actions, Draft editing and citations, and
 * States): the draft with its citation markers, the editor after Edit draft, or the reason codes,
 * the rejected draft, and an empty editor after Reject draft. When a new draft replaced the one that
 * staff worked on, their text stays in the editor and the new draft shows above it, read-only
 * (Errors and guardrails, "The draft was superseded"). Warnings sit at the top, next to the action
 * they block, and each needs an acknowledgement (UI-18). AI content carries the `ai` marker
 * (UI-13); text in the editor is staff text.
 */
import {
  Panel,
  PanelSection,
  presentationByAiReasonCode,
  Stack,
  StatusBanner,
  Tag,
  WarningList,
} from "@/design-system";
import { assertNever } from "@/features/backend-requests";
import {
  type CitationContext,
  CitedDraft,
} from "@/features/console-tickets/components/cited-draft";
import { DraftModeActions } from "@/features/console-tickets/components/draft-mode-actions";
import {
  DraftPanelHeader,
  getDraftPanelTitle,
} from "@/features/console-tickets/components/draft-panel-header";
import { RejectionReasons } from "@/features/console-tickets/components/rejection-reasons";
import { ReplyActionBar } from "@/features/console-tickets/components/reply-action-bar";
import { ReplyEditorSection } from "@/features/console-tickets/components/reply-editor-section";
import type { ReplyComposer } from "@/features/console-tickets/components/use-reply-composer";
import type { ReadyDraft } from "@/features/console-tickets/model/draft";
import type { SuggestionWarning } from "@/features/console-tickets/model/reason-codes";
import {
  acknowledgeWarning,
  discardEdits,
  rejectDraft,
  startEditing,
  toggleReasonCode,
} from "@/features/console-tickets/model/reply-composer";

/** The hint under the editor of a reply that is sent as an edit of the AI draft. */
const EDITED_TEXT_HINT = "Edited text is not checked against the sources.";

/** What a draft needs: its warnings, its time, and its citations. */
export type DraftContext = {
  readonly warnings: readonly SuggestionWarning[];
  /** When the suggestion started, as an RFC 3339 timestamp. */
  readonly generatedAt: string;
  readonly citations: CitationContext;
};

/** Props of {@link DraftReplyPanel}. */
type DraftReplyPanelProps = {
  readonly composer: ReplyComposer;
  readonly draft: ReadyDraft;
  readonly context: DraftContext;
};

/**
 * Render the reply area of a ready draft.
 *
 * @param props - The composer, the draft, and what the draft needs.
 * @returns The panel with its action bar.
 */
export function DraftReplyPanel({ composer, draft, context }: DraftReplyPanelProps) {
  const { state, change } = composer;
  const isRejected = state.draftMode === "rejecting";
  return (
    <Panel
      density="compact"
      height="fill"
      as="section"
      label={getDraftPanelTitle(state)}
      {...(isRejected ? {} : { tone: "ai" as const })}
    >
      <DraftPanelHeader state={state} generatedAt={context.generatedAt} />
      {isRejected || context.warnings.length === 0 ? null : (
        <PanelSection>
          <WarningList
            warnings={context.warnings.map((warning) => ({
              warningId: warning.warningId,
              title: presentationByAiReasonCode[warning.reasonCode].label,
              description: warning.text,
            }))}
            acknowledgedIds={state.acknowledgedWarningIds}
            onAcknowledgedChange={(warningId, isAcknowledged) => {
              change((current) => acknowledgeWarning(current, { warningId, isAcknowledged }));
            }}
          />
        </PanelSection>
      )}
      <DraftBody composer={composer} draft={draft} context={context} />
      <ReplyActionBar
        composer={composer}
        actions={
          <DraftModeActions
            mode={state.draftMode}
            canChange={composer.canChangeDraft}
            handlers={{
              onEdit: () => {
                change((current) => startEditing(current, draft.text));
              },
              onDiscard: () => {
                change(discardEdits);
              },
              onReject: () => {
                change(rejectDraft);
              },
            }}
          />
        }
      />
    </Panel>
  );
}

/**
 * Render what the panel holds in the mode of the draft.
 *
 * @param props - The composer, the draft, and what the draft needs.
 * @returns The draft; the editor; the new draft above the kept text; or the reasons with the
 *   rejected draft and the editor.
 */
function DraftBody({ composer, draft, context }: DraftReplyPanelProps) {
  const { state, change } = composer;
  const changeBody = (body: string) => {
    change((current) => ({ ...current, body }));
  };
  switch (state.draftMode) {
    case "viewing":
      return (
        <PanelSection>
          <CitedDraft draft={draft} {...context.citations} />
        </PanelSection>
      );
    case "editing":
      return (
        <ReplyEditorSection value={state.body} onChange={changeBody} hints={[EDITED_TEXT_HINT]} />
      );
    case "keeping":
      return (
        <>
          <PanelSection>
            <StatusBanner tone="info" lead="The AI made a new draft.">
              Your text is kept below it.
            </StatusBanner>
            <CitedDraft draft={draft} {...context.citations} />
          </PanelSection>
          <ReplyEditorSection value={state.body} onChange={changeBody} hints={[EDITED_TEXT_HINT]} />
        </>
      );
    case "rejecting":
      return (
        <>
          <RejectionReasons
            reasonCodes={state.reasonCodes}
            note={state.note}
            onToggle={(reasonCode) => {
              change((current) => toggleReasonCode(current, reasonCode));
            }}
            onNoteChange={(note) => {
              change((current) => ({ ...current, note }));
            }}
          />
          <PanelSection>
            <Stack gap="2" align="start">
              <Tag tone="neutral">Rejected</Tag>
              <CitedDraft draft={draft} tone="muted" {...context.citations} />
            </Stack>
          </PanelSection>
          <ReplyEditorSection value={state.body} onChange={changeBody} />
        </>
      );
    default:
      assertNever(state.draftMode);
  }
}
