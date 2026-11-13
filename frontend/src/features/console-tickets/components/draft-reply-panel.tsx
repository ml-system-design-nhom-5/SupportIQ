/**
 * The reply area with a ready draft (console UI design, Actions, Draft editing and citations, and
 * States): the draft with its citation markers, the editor after Edit draft, or the reason codes,
 * the rejected draft, and an empty editor after Reject draft. Warnings sit at the top, next to the
 * action they block, and each needs an acknowledgement (UI-18). AI content carries the `ai` marker
 * (UI-13); text in the editor is staff text.
 */
import { Pencil, Sparkles, X } from "lucide-react";

import {
  Panel,
  PanelHeader,
  PanelSection,
  presentationByAiReasonCode,
  presentationByAiStatus,
  RelativeTime,
  Stack,
  StatusBadge,
  Tag,
  Text,
  WarningList,
} from "@/design-system";
import {
  type CitationContext,
  CitedDraft,
} from "@/features/console-tickets/components/cited-draft";
import { DraftModeActions } from "@/features/console-tickets/components/draft-mode-actions";
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
  const { mode, change } = composer;
  const isRejected = mode === "rejecting";
  return (
    <Panel
      density="compact"
      as="section"
      label={getTitle(mode)}
      {...(isRejected ? {} : { tone: "ai" as const })}
    >
      <DraftHeader mode={mode} generatedAt={context.generatedAt} />
      {isRejected || context.warnings.length === 0 ? null : (
        <PanelSection>
          <WarningList
            warnings={context.warnings.map((warning) => ({
              warningId: warning.warningId,
              title: presentationByAiReasonCode[warning.reasonCode].label,
              description: warning.text,
            }))}
            acknowledgedIds={composer.state.acknowledgedWarningIds}
            onAcknowledgedChange={(warningId, isAcknowledged) => {
              change((state) => acknowledgeWarning(state, { warningId, isAcknowledged }));
            }}
          />
        </PanelSection>
      )}
      <DraftBody composer={composer} draft={draft} context={context} />
      <ReplyActionBar
        composer={composer}
        actions={
          <DraftModeActions
            mode={mode}
            canChange={composer.canChangeDraft}
            handlers={{
              onEdit: () => {
                change((state) => startEditing(state, draft.text));
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
 * Render what the panel holds in its mode.
 *
 * @param props - The composer, the draft, and what the draft needs.
 * @returns The draft, the editor, or the reasons with the rejected draft and the editor.
 */
function DraftBody({ composer, draft, context }: DraftReplyPanelProps) {
  const { state, change } = composer;
  const changeBody = (body: string) => {
    change((current) => ({ ...current, body }));
  };
  if (composer.mode === "editing") {
    return (
      <ReplyEditorSection
        value={state.body}
        onChange={changeBody}
        hints={["Edited text is not checked against the sources."]}
      />
    );
  }
  if (composer.mode !== "rejecting") {
    return (
      <PanelSection>
        <CitedDraft draft={draft} {...context.citations} />
      </PanelSection>
    );
  }
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
}

/**
 * Render the header of the panel in its mode.
 *
 * @param props - The mode and when the suggestion started.
 * @returns The header.
 */
function DraftHeader({
  mode,
  generatedAt,
}: {
  readonly mode: ReplyComposer["mode"];
  readonly generatedAt: string;
}) {
  if (mode === "editing") {
    return (
      <PanelHeader
        icon={Pencil}
        level={2}
        title="Edit draft"
        trailing={
          <Tag tone="ai" icon={Sparkles}>
            Started from AI draft
          </Tag>
        }
      />
    );
  }
  if (mode === "rejecting") {
    return (
      <PanelHeader
        icon={X}
        level={2}
        title="Draft rejected"
        trailing={<Text tone="muted">Your reason improves the AI after review</Text>}
      />
    );
  }
  return (
    <PanelHeader
      icon={Sparkles}
      level={2}
      title="AI draft"
      trailing={
        <Stack direction="row" gap="2" align="center">
          <StatusBadge presentation={presentationByAiStatus.draft_ready} />
          <Text tone="muted">
            Generated <RelativeTime timestamp={generatedAt} />
          </Text>
        </Stack>
      }
    />
  );
}

/**
 * Name the panel in its mode.
 *
 * @param mode - What staff do with the draft.
 * @returns "AI draft", "Edit draft", or "Draft rejected".
 */
function getTitle(mode: ReplyComposer["mode"]): string {
  if (mode === "editing") {
    return "Edit draft";
  }
  return mode === "rejecting" ? "Draft rejected" : "AI draft";
}
