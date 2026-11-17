/**
 * The body of the reply area Reply for approval of a ticket in `awaiting_approval` (UI-19; console
 * UI design, States "Awaiting approval, staff" and "Awaiting approval, manager";
 * workspace-manager.png, state-awaiting-approval-staff.png): the staff proposal, with a strong
 * border, above the AI draft of the ticket in the `ai` tone, marked "For comparison" (UI-13). The
 * two cards stack, as in the mockups at the console width of 1280 px. A proposal without an AI
 * draft (basis `no_ai_draft`) shows the proposal card only. Each card is a region named for
 * assistive technology, with a level 3 heading under the level 2 heading of the reply area.
 */
import { cva } from "class-variance-authority";
import { type LucideIcon, Sparkles, User } from "lucide-react";
import type { ReactNode } from "react";

import { RelativeTime } from "@/design-system/components/relative-time";
import { Tag } from "@/design-system/components/tag";
import { Icon } from "@/design-system/primitives/icon";
import { Text } from "@/design-system/primitives/text";

const cardVariants = cva("flex flex-col gap-2 rounded-md border p-3", {
  variants: {
    tone: { proposal: "border-border-strong", ai: "border-ai/35 bg-ai-subtle/50" },
  },
});

/** The look of a card: `proposal` for the text that a manager sends, `ai` for AI output. */
type ComparisonCardTone = "proposal" | "ai";

/** The staff proposal. */
export type ProposalComparisonProposal = {
  /** Who submitted the proposal, as the console names them, for example "Minh Le (staff)". */
  readonly authorName: string;
  /** When the proposal was submitted, as an RFC 3339 timestamp. */
  readonly submittedAt: string;
  /** The proposal text, or the editor after Edit proposal. */
  readonly content: ReactNode;
};

/** Props of {@link ProposalComparison}. */
export type ProposalComparisonProps = {
  readonly proposal: ProposalComparisonProposal;
  /**
   * The AI draft of the ticket with its citation markers, such as a {@link DraftText}; absent for a
   * proposal without an AI draft.
   */
  readonly aiDraft?: ReactNode;
};

/**
 * Render the staff proposal and, when there is one, the AI draft for comparison.
 *
 * @param props - The proposal and the AI draft.
 * @returns The region "Staff proposal" above the region "AI draft for comparison".
 */
export function ProposalComparison({ proposal, aiDraft }: ProposalComparisonProps) {
  return (
    <div className="flex flex-col gap-3">
      <ComparisonCard
        tone="proposal"
        label="Staff proposal"
        icon={User}
        title="Staff proposal"
        trailing={
          <Text tone="muted">
            {proposal.authorName} · <RelativeTime timestamp={proposal.submittedAt} />
          </Text>
        }
      >
        {proposal.content}
      </ComparisonCard>
      {aiDraft === undefined ? null : (
        <ComparisonCard
          tone="ai"
          label="AI draft for comparison"
          icon={Sparkles}
          title="AI draft"
          trailing={<Tag tone="ai">For comparison</Tag>}
        >
          {aiDraft}
        </ComparisonCard>
      )}
    </div>
  );
}

/** Props of {@link ComparisonCard}. */
type ComparisonCardProps = {
  readonly tone: ComparisonCardTone;
  /** The name of the region. */
  readonly label: string;
  readonly icon: LucideIcon;
  readonly title: string;
  readonly trailing: ReactNode;
  readonly children: ReactNode;
};

/**
 * Render one card of the comparison.
 *
 * @param props - The tone, the region name, the icon, the heading, the trailing content, and the
 *   content.
 * @returns The card, as a named region.
 */
function ComparisonCard({ tone, label, icon, title, trailing, children }: ComparisonCardProps) {
  return (
    <section aria-label={label} className={cardVariants({ tone })}>
      <div className="flex items-center gap-2">
        <Icon icon={icon} />
        <h3 className="text-sm font-semibold text-text">{title}</h3>
        <div className="ml-auto">{trailing}</div>
      </div>
      {children}
    </section>
  );
}
