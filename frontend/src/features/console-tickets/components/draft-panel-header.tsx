/**
 * The header of the reply area with a ready draft, in the mode of the draft (console UI design,
 * States; state-editing.png, state-rejected.png): AI draft with its status and time, Edit draft
 * marked "Started from AI draft", or Draft rejected. Text that staff wrote themselves and kept over
 * a new draft is a Reply, never marked as started from the AI. Draft rejected takes the focus when
 * it replaces Reject draft, which held it (UI-30).
 */
import { Pencil, PenLine, Sparkles, X } from "lucide-react";
import { useEffect } from "react";

import {
  PanelHeader,
  presentationByAiStatus,
  RelativeTime,
  Stack,
  StatusBadge,
  Tag,
  Text,
} from "@/design-system";
import { assertNever } from "@/features/backend-requests";
import type { ComposerState } from "@/features/console-tickets/model/reply-composer";

/** The ID of the heading Draft rejected, which takes the focus after Reject draft. */
const REJECTED_DRAFT_HEADING_ID = "draft-rejected-heading";

/** Props of {@link DraftPanelHeader}. */
type DraftPanelHeaderProps = {
  readonly state: ComposerState;
  /** When the suggestion started, as an RFC 3339 timestamp. */
  readonly generatedAt: string;
};

/**
 * Render the header in the mode of the draft.
 *
 * @param props - What staff composed and when the suggestion started.
 * @returns The header.
 */
export function DraftPanelHeader({ state, generatedAt }: DraftPanelHeaderProps) {
  switch (state.draftMode) {
    case "viewing":
      return <AiDraftHeader generatedAt={generatedAt} />;
    case "editing":
      return <EditDraftHeader />;
    case "rejecting":
      return <RejectedDraftHeader />;
    case "keeping":
      return state.keptTextOrigin === "edited_draft" ? (
        <EditDraftHeader />
      ) : (
        <PanelHeader icon={PenLine} level={2} title="Reply" />
      );
    default:
      assertNever(state.draftMode);
  }
}

/**
 * Name the reply area in the mode of the draft.
 *
 * @param state - What staff composed.
 * @returns "AI draft", "Edit draft", "Draft rejected", or "Reply", as the header says.
 */
export function getDraftPanelTitle(state: ComposerState): string {
  switch (state.draftMode) {
    case "viewing":
      return "AI draft";
    case "editing":
      return "Edit draft";
    case "rejecting":
      return "Draft rejected";
    case "keeping":
      return state.keptTextOrigin === "edited_draft" ? "Edit draft" : "Reply";
    default:
      assertNever(state.draftMode);
  }
}

/**
 * Render the header of the draft read as is.
 *
 * @param props - When the suggestion started.
 * @returns The header with the status and the time.
 */
function AiDraftHeader({ generatedAt }: { readonly generatedAt: string }) {
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
 * Render the header of an edit of an AI draft.
 *
 * @returns The header marked "Started from AI draft".
 */
function EditDraftHeader() {
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

/**
 * Render the header of a rejected draft, and move the focus to it when it appears: only Reject
 * draft leads to it.
 *
 * @returns The header.
 */
function RejectedDraftHeader() {
  useEffect(() => {
    document.getElementById(REJECTED_DRAFT_HEADING_ID)?.focus();
  }, []);
  return (
    <PanelHeader
      icon={X}
      level={2}
      title="Draft rejected"
      focusTargetId={REJECTED_DRAFT_HEADING_ID}
      trailing={<Text tone="muted">Your reason improves the AI after review</Text>}
    />
  );
}
