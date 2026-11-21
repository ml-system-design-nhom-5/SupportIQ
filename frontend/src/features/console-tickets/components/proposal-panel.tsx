/**
 * The reply area of a ticket awaiting approval (console UI design, States; workspace-manager.png,
 * state-awaiting-approval-staff.png): the staff proposal next to the AI draft, which is shown for
 * comparison. A manager sends the proposal as is, or turns it into the editor with Edit proposal
 * and sends the edited text; both use the basis `reply_proposal` (FR-06). Staff read it, with
 * every action disabled. Text is rendered as text (SEC-22).
 */
import { Clock, Pencil, X } from "lucide-react";

import {
  Button,
  Panel,
  PanelHeader,
  PanelSection,
  ProposalComparison,
  Stack,
  Text,
} from "@/design-system";
import { CitedDraft } from "@/features/console-tickets/components/cited-draft";
import type { DraftContext } from "@/features/console-tickets/components/draft-reply-panel";
import { ProposalStaffInput } from "@/features/console-tickets/components/proposal-staff-input";
import { ReplyActionBar } from "@/features/console-tickets/components/reply-action-bar";
import { ReplyEditorField } from "@/features/console-tickets/components/reply-editor-field";
import type { ReplyComposer } from "@/features/console-tickets/components/use-reply-composer";
import { describeHandoffAuthor } from "@/features/console-tickets/model/manager-handoff";
import {
  discardEdits,
  EDITED_TEXT_HINT,
  startEditing,
} from "@/features/console-tickets/model/reply-composer";
import type { ReplyAreaState } from "@/features/console-tickets/model/workspace-state";
import { useSignedInAccountId, useSignedInRole } from "@/features/session";

/** The ID of the heading, which takes the focus once staff submitted the reply (UI-30). */
export const PROPOSAL_HEADING_ID = "reply-for-approval-heading";

/** Props of {@link ProposalPanel}. */
type ProposalPanelProps = {
  readonly composer: ReplyComposer;
  readonly state: Extract<ReplyAreaState, { readonly kind: "proposal" }>;
  readonly context: DraftContext;
};

/**
 * Render the proposal and the AI draft.
 *
 * @param props - The composer, the proposal with the AI draft, and what the draft needs.
 * @returns The panel with its action bar.
 */
export function ProposalPanel({ composer, state, context }: ProposalPanelProps) {
  const { proposal, draft } = state;
  const signedInAccountId = useSignedInAccountId();
  const isManager = useSignedInRole() === "manager";
  // Only a manager edits a proposal; staff never get the editor, whatever they composed before.
  const isEditing = composer.canEditProposal && composer.state.draftMode === "editing";
  return (
    <Panel density="compact" height="fill" as="section" label="Reply for approval">
      <PanelHeader
        icon={Clock}
        level={2}
        title="Reply for approval"
        focusTargetId={PROPOSAL_HEADING_ID}
        trailing={
          <Text tone="muted">
            {composer.canEditProposal
              ? "Send it as proposed, or edit it first"
              : "Waiting for a manager"}
          </Text>
        }
      />
      <PanelSection>
        <ProposalComparison
          proposal={{
            authorName: describeHandoffAuthor(proposal.proposedBy, signedInAccountId),
            submittedAt: proposal.createdAt,
            content: (
              <Stack gap="3">
                {isEditing ? (
                  <ReplyEditorField
                    value={composer.state.body}
                    onChange={(body) => {
                      composer.change((current) => ({ ...current, body }));
                    }}
                    hints={[EDITED_TEXT_HINT]}
                  />
                ) : (
                  <Text overflow="preserve">{proposal.body}</Text>
                )}
                {/* A manager sees why staff wrote it so (the lead's decision of 2026-11-14). */}
                {isManager ? <ProposalStaffInput proposal={proposal} /> : null}
              </Stack>
            ),
          }}
          {...(draft === undefined
            ? {}
            : { aiDraft: <CitedDraft draft={draft} {...context.citations} /> })}
        />
      </PanelSection>
      <ReplyActionBar
        composer={composer}
        actions={
          <ProposalActions composer={composer} proposalBody={proposal.body} isEditing={isEditing} />
        }
      />
    </Panel>
  );
}

/**
 * Render Edit proposal, or Discard edits while the proposal is in the editor, and Reject draft,
 * which a proposal does not allow (console UI design, Actions).
 *
 * @param props - The composer, the text of the proposal, and whether it is in the editor.
 * @returns The buttons.
 */
function ProposalActions({
  composer,
  proposalBody,
  isEditing,
}: {
  readonly composer: ReplyComposer;
  readonly proposalBody: string;
  /** True while the manager edits the proposal. */
  readonly isEditing: boolean;
}) {
  // Staff never edit a proposal; their disabled button reads as in the mockup.
  const editLabel = composer.canEditProposal ? "Edit proposal" : "Edit draft";
  return (
    <>
      {isEditing ? (
        <Button
          leadingIcon={Pencil}
          onClick={() => {
            composer.change(discardEdits);
          }}
        >
          Discard edits
        </Button>
      ) : (
        <Button
          leadingIcon={Pencil}
          disabled={!composer.canEditProposal}
          onClick={() => {
            composer.change((current) => startEditing(current, proposalBody));
          }}
        >
          {editLabel}
        </Button>
      )}
      <Button leadingIcon={X} disabled>
        Reject draft
      </Button>
    </>
  );
}
