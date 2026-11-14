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
import { withFakeBackend } from "@/test/story-backend";

const meta = {
  title: "Console/TicketWorkspace/Approval",
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
 * Build the decorator of a story whose console answers as given.
 *
 * @param answers - The answers that differ from the defaults: a staff session and the draft-ready
 *   workspace.
 * @returns The decorators of the story.
 */
function withAnswers(answers: ConsoleAnswers) {
  return [
    withFakeBackend((backend) => {
      answerConsole(backend, answers);
    }),
  ];
}

export const AuthorityRequired: Story = {
  decorators: withAnswers({ workspace: [workspaceExample("authority-required")] }),
  play: async ({ canvasElement }) => {
    await expect(
      await within(canvasElement).findByRole("button", { name: "Submit for approval" }),
    ).toBeEnabled();
  },
};
export const SubmitInTheMoreMenu: Story = {
  decorators: withAnswers({}),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    // More is disabled while its only item is: a proposal needs every warning acknowledged.
    await userEvent.click(await canvas.findByRole("checkbox", { name: /^I have checked this/ }));
    await userEvent.click(canvas.getByRole("button", { name: "More actions" }));

    await expect(
      await screen.findByRole("menuitem", { name: /^Submit for approval/ }),
    ).toBeVisible();
  },
};
export const SubmitInManualHandling: Story = {
  decorators: withAnswers({ workspace: [workspaceExample("manual-mode")] }),
  play: async ({ canvasElement }) => {
    await expect(
      await within(canvasElement).findByRole("button", { name: "Submit for approval" }),
    ).toBeDisabled();
  },
};
export const AwaitingApprovalManager: Story = {
  decorators: withAnswers({
    session: "manager",
    workspace: [workspaceExample("awaiting-approval")],
  }),
  play: async ({ canvasElement }) => {
    await expect(
      await within(canvasElement).findByRole("region", { name: "Staff proposal" }),
    ).toBeVisible();
  },
};
export const EditProposal: Story = {
  decorators: withAnswers({
    session: "manager",
    workspace: [workspaceExample("awaiting-approval")],
  }),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.click(await canvas.findByRole("button", { name: "Edit proposal" }));

    await expect(canvas.getByRole("textbox", { name: "Reply to the customer" })).toBeVisible();
  },
};
export const AwaitingApprovalStaff: Story = {
  decorators: withAnswers({ workspace: [workspaceExample("read-only-for-staff")] }),
  play: async ({ canvasElement }) => {
    await expect(
      await within(canvasElement).findByText(
        "This ticket is read-only for you. A manager sends the reply.",
      ),
    ).toBeVisible();
  },
};
export const EscalatedManager: Story = {
  decorators: withAnswers({ session: "manager", workspace: [workspaceExample("escalated")] }),
  play: async ({ canvasElement }) => {
    await expect(
      await within(canvasElement).findByRole("region", { name: "Escalated by Mai Nguyen" }),
    ).toHaveTextContent("The customer asks to talk to a person.");
  },
};
export const EscalatedWithReadyDraft: Story = {
  decorators: withAnswers({
    session: "manager",
    workspace: [
      workspaceWithSuggestion("escalated", { draft: readSuggestionPart("draft-ready", "draft") }),
    ],
  }),
  play: async ({ canvasElement }) => {
    await expect(
      await within(canvasElement).findByRole("region", { name: "AI draft" }),
    ).toBeVisible();
  },
};
export const EscalateDialogOpen: Story = {
  decorators: withAnswers({}),
  play: async ({ canvasElement }) => {
    await userEvent.click(
      await within(canvasElement).findByRole("button", { name: "Escalate ticket" }),
    );

    await expect(
      await screen.findByRole("dialog", { name: "Escalate ticket TCK-1042 to a manager?" }),
    ).toBeVisible();
  },
};
