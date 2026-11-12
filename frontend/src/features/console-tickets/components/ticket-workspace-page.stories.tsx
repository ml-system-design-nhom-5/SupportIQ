import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, screen, userEvent, within } from "storybook/test";

import { TicketWorkspacePage } from "@/features/console-tickets/components/ticket-workspace-page";
import {
  answerConsole,
  type ConsoleAnswers,
  readSuggestionPart,
  workspaceExample,
  workspaceWithSuggestion,
} from "@/test/console-screen";
import { ConsoleStoryFrame } from "@/test/console-story-frame";
import { exampleAnswer, type FakeAnswer } from "@/test/fake-backend";
import { withFakeBackend } from "@/test/story-backend";

const meta = {
  title: "Console/TicketWorkspace",
  component: TicketWorkspacePage,
  parameters: { layout: "fullscreen" },
  args: { ticketId: "TCK-1042" },
  render: (args) => (
    <ConsoleStoryFrame>
      <TicketWorkspacePage {...args} />
    </ConsoleStoryFrame>
  ),
} satisfies Meta<typeof TicketWorkspacePage>;

export default meta;

type Story = StoryObj<typeof meta>;

/**
 * Build the decorator of a story whose workspace answers as given.
 *
 * @param workspace - The answer of `getConsoleTicket`.
 * @param answers - The other answers that differ from the defaults.
 * @returns The decorators of the story.
 */
function withWorkspace(workspace: FakeAnswer, answers: ConsoleAnswers = {}) {
  return [
    withFakeBackend((backend) => {
      answerConsole(backend, { ...answers, workspace: [workspace] });
    }),
  ];
}

export const DraftReady: Story = { decorators: withWorkspace(workspaceExample("draft-ready")) };
export const Loading: Story = { decorators: withWorkspace({ kind: "no_answer" }) };
export const AnalysisPending: Story = {
  decorators: withWorkspace(workspaceExample("suggestion-pending")),
};
export const Partial: Story = {
  decorators: withWorkspace(
    workspaceWithSuggestion("draft-ready", { draft: { draft_status: "pending" } }),
  ),
};
export const ChooseAnIntent: Story = {
  decorators: withWorkspace(workspaceExample("abstained-low-confidence")),
};
export const Abstained: Story = {
  decorators: withWorkspace(
    workspaceWithSuggestion("draft-ready", {
      draft: {
        ...readSuggestionPart("abstained-low-confidence", "draft"),
        reason_codes: ["no_valid_document"],
      },
    }),
  ),
};
export const EscalationRecommended: Story = {
  decorators: withWorkspace(
    workspaceWithSuggestion("draft-ready", {
      draft: {
        ...readSuggestionPart("escalated", "draft"),
      },
    }),
  ),
};
export const AuthorityRequired: Story = {
  decorators: withWorkspace(workspaceExample("authority-required")),
};
export const IntentChosenByStaff: Story = {
  decorators: withWorkspace(workspaceExample("intent-corrected")),
};
export const AiUnavailable: Story = {
  decorators: withWorkspace(workspaceExample("ai-service-unavailable")),
};
export const PseudonymizationFailed: Story = {
  decorators: withWorkspace(workspaceExample("pseudonymization-failed")),
};
export const DraftingFailed: Story = {
  decorators: withWorkspace(workspaceExample("llm-unavailable")),
};
export const ManualMode: Story = { decorators: withWorkspace(workspaceExample("manual-mode")) };
export const Closed: Story = { decorators: withWorkspace(workspaceExample("closed")) };
export const Error: Story = {
  decorators: withWorkspace(exampleAnswer(500, "problems", "internal-error")),
};
export const NotFound: Story = {
  decorators: withWorkspace(exampleAnswer(404, "problems", "not-found")),
};
export const PermissionDenied: Story = {
  decorators: withWorkspace(exampleAnswer(403, "problems", "forbidden-role")),
};
export const ViewNotRecorded: Story = {
  decorators: withWorkspace(workspaceExample("draft-ready"), {
    view: [exampleAnswer(503, "problems", "not-ready")],
  }),
};
export const KbDocumentOpen: Story = {
  decorators: withWorkspace(workspaceExample("draft-ready")),
  play: async ({ canvasElement }) => {
    const draft = await within(canvasElement).findByRole("region", { name: "AI draft" });
    await userEvent.click(
      within(draft).getByRole("button", { name: "Source 1: Sample refund document" }),
    );

    await expect(
      await screen.findByRole("dialog", { name: "Sample refund document" }),
    ).toBeVisible();
  },
};
export const OrdersOpen: Story = {
  decorators: withWorkspace(workspaceExample("draft-ready")),
  play: async ({ canvasElement }) => {
    await userEvent.click(
      await within(canvasElement).findByRole("button", { name: /^ORD-20931 Delivered/ }),
    );

    await expect(
      await screen.findByRole("dialog", { name: "Orders of this customer" }),
    ).toBeVisible();
  },
};
