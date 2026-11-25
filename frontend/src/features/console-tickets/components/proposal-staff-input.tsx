/**
 * What staff told the manager with a proposal (the lead's decision of 2026-11-14 for the console
 * UI design, Awaiting approval, manager): what the reply is based on, the staff reason codes, and
 * the staff note, under the proposal text. The note is Confidential: it is shown here and nowhere
 * else, never logged or stored. Text is rendered as text (SEC-22).
 */
import { Chip, Cluster, Stack, Text } from "@/design-system";
import type {
  ProposalBasis,
  ReplyProposal,
} from "@/features/console-tickets/model/manager-handoff";
import { shownStaffReasonCodeLabels } from "@/features/console-tickets/model/staff-reason-codes";

/** What each basis says of the reply; a basis that this version does not know says nothing. */
const basisSentences: Readonly<Record<ProposalBasis, string | undefined>> = {
  ai_draft: "Based on the AI draft.",
  rejected_ai_draft: "Written after staff rejected the AI draft.",
  no_ai_draft: "Written without an AI draft.",
  unknown: undefined,
};

/** Props of {@link ProposalStaffInput}. */
type ProposalStaffInputProps = {
  readonly proposal: ReplyProposal;
};

/**
 * Render the basis, the reasons, and the note of a proposal.
 *
 * @param props - The proposal.
 * @returns The section, or nothing when the proposal carries none of them.
 */
export function ProposalStaffInput({ proposal }: ProposalStaffInputProps) {
  const { reasonCodes, note } = proposal;
  const basisSentence = basisSentences[proposal.basis];
  if (basisSentence === undefined && reasonCodes.length === 0 && note === undefined) {
    return null;
  }
  return (
    <Stack as="section" label="What staff noted" gap="2">
      {basisSentence === undefined ? null : <Text tone="muted">{basisSentence}</Text>}
      {reasonCodes.length === 0 ? null : (
        <Cluster>
          {reasonCodes.map((reasonCode) => (
            <Chip key={reasonCode}>{shownStaffReasonCodeLabels[reasonCode]}</Chip>
          ))}
        </Cluster>
      )}
      {note === undefined ? null : <Text overflow="preserve">{note}</Text>}
    </Stack>
  );
}
