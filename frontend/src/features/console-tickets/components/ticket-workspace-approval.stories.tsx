import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, screen, userEvent, within } from "storybook/test";

import { TicketWorkspacePage } from "@/features/console-tickets/components/ticket-workspace-page";
import {
  answerConsole,
  type ConsoleAnswers,
  readSuggestionPart,
  workspaceExample,
  workspaceWith,
  workspaceWithSuggestion,
} from "@/test/console-screen";
import { ConsoleStoryFrame } from "@/test/console-story-frame";
import { readOperationExample } from "@/test/contract-examples";
import { exampleAnswer } from "@/test/fake-backend";
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

/** What the play functions of this file read of the story context. */
type PlayContext = { readonly canvasElement: HTMLElement };

/** The reply that staff write in manual handling. */
const STAFF_TEXT = "Here is the return label.";

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

/**
 * Write a reply in manual handling and press Submit for approval, as staff do.
 *
 * @param context - The story context.
 * @param context.canvasElement - The element that holds the story.
 * @returns The editor, which keeps the text whatever the outcome.
 */
async function submitManualReply({ canvasElement }: PlayContext): Promise<HTMLElement> {
  const canvas = within(canvasElement);
  const editor = await canvas.findByRole("textbox", { name: "Reply to the customer" });
  await userEvent.type(editor, STAFF_TEXT);
  await userEvent.click(canvas.getByRole("button", { name: "Submit for approval" }));
  return editor;
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
export const SubmitRefused: Story = {
  decorators: withAnswers({
    workspace: [workspaceExample("manual-mode")],
    proposal: [exampleAnswer(409, "problems", "invalid-ticket-state")],
  }),
  play: async (context) => {
    const editor = await submitManualReply(context);

    await expect(await within(context.canvasElement).findByRole("alert")).toHaveTextContent(
      "The reply was not submitted. This ticket was already handled. It now shows its current state.",
    );
    await expect(editor).toHaveValue(STAFF_TEXT);
  },
};
export const SubmitOutcomeUnknown: Story = {
  decorators: withAnswers({
    workspace: [workspaceExample("manual-mode")],
    proposal: [{ kind: "network_error" }],
  }),
  play: async (context) => {
    const editor = await submitManualReply(context);

    await expect(await within(context.canvasElement).findByRole("alert")).toHaveTextContent(
      "The reply may have been submitted. We could not confirm it. Submitting the same reply again is safe: a manager gets it once.",
    );
    await expect(editor).toHaveValue(STAFF_TEXT);
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
export const AwaitingApprovalManagerWithReasons: Story = {
  decorators: withAnswers({
    session: "manager",
    workspace: [
      workspaceWith("awaiting-approval", {
        proposal: {
          ...readOperationExample("getConsoleTicket", 200, "awaiting-approval").proposal,
          basis: "rejected_ai_draft",
          staff_reason_codes: ["kb_gap", "other"],
          note: "The customer called us about the label.",
        },
      }),
    ],
  }),
  play: async ({ canvasElement }) => {
    await expect(
      await within(canvasElement).findByRole("region", { name: "What staff noted" }),
    ).toHaveTextContent("Written after staff rejected the AI draft.");
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
      await within(canvasElement).findByRole("region", { name: "Escalated by Mai Nguyen (staff)" }),
    ).toHaveTextContent("The customer asks to talk to a person.");
  },
};
export const EscalatedStaff: Story = {
  // The example is the view of a manager; an escalated ticket is read-only for staff. The staff
  // session is the account that escalated it.
  decorators: withAnswers({ workspace: [workspaceWith("escalated", { allowed_actions: [] })] }),
  play: async ({ canvasElement }) => {
    const escalation = await within(canvasElement).findByRole("region", {
      name: "Escalated by Mai Nguyen (you)",
    });

    await expect(escalation).toHaveTextContent(
      "This ticket is read-only for you. A manager sends the reply.",
    );
    await expect(within(escalation).queryByRole("textbox")).toBeNull();
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
