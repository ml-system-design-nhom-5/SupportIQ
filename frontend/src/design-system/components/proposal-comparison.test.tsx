import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  ProposalComparison,
  type ProposalComparisonProposal,
} from "@/design-system/components/proposal-comparison";
import { renderUi } from "@/test/render-app";

/** A proposal submitted 12 minutes before the test clock (2026-11-05T09:00:00Z). */
const proposal: ProposalComparisonProposal = {
  authorName: "Minh Le (staff)",
  submittedAt: "2026-11-05T08:48:00Z",
  content: <p>I have passed your refund request to a manager.</p>,
};

describe("ProposalComparison", () => {
  it("shows the staff proposal with its author and time above the AI draft (UI-19)", () => {
    renderUi(<ProposalComparison proposal={proposal} aiDraft={<p>A manager will reply.</p>} />);

    const proposalCard = screen.getByRole("region", { name: "Staff proposal" });
    expect(
      within(proposalCard).getByRole("heading", { level: 3, name: "Staff proposal" }),
    ).toBeVisible();
    expect(proposalCard).toHaveTextContent("Minh Le (staff) · 12 minutes ago");
    expect(
      within(proposalCard).getByText("I have passed your refund request to a manager."),
    ).toBeVisible();
    const draftCard = screen.getByRole("region", { name: "AI draft for comparison" });
    expect(proposalCard.compareDocumentPosition(draftCard)).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
  });

  it("marks the AI draft as AI output for comparison (UI-13)", () => {
    renderUi(<ProposalComparison proposal={proposal} aiDraft={<p>A manager will reply.</p>} />);

    const draftCard = screen.getByRole("region", { name: "AI draft for comparison" });
    expect(within(draftCard).getByRole("heading", { level: 3, name: "AI draft" })).toBeVisible();
    expect(within(draftCard).getByText("For comparison")).toBeVisible();
    expect(within(draftCard).getByText("A manager will reply.")).toBeVisible();
  });

  it("shows the proposal only when it has no AI draft", () => {
    renderUi(<ProposalComparison proposal={proposal} />);

    expect(screen.getByRole("region", { name: "Staff proposal" })).toBeVisible();
    expect(
      screen.queryByRole("region", { name: "AI draft for comparison" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("For comparison")).not.toBeInTheDocument();
  });
});
