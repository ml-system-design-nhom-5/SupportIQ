import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, screen, userEvent, within } from "storybook/test";

import { TicketWorkspacePage } from "@/features/console-tickets/components/ticket-workspace-page";
import { answerConsole, type ConsoleAnswers, workspaceExample } from "@/test/console-screen";
import { ConsoleStoryFrame } from "@/test/console-story-frame";
import { exampleAnswer } from "@/test/fake-backend";
import { withFakeBackend } from "@/test/story-backend";

const meta = {
  title: "Console/TicketWorkspace/Reply",
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

/**
 * Build the decorator of a story whose console answers as given.
 *
 * @param answers - The answers that differ from the defaults: the draft-ready workspace.
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
 * Reject the draft, as staff do.
 *
 * @param context - The story context.
 * @param context.canvasElement - The element that holds the story.
 * @returns The queries of the region "Draft rejected".
 */
async function rejectDraft({ canvasElement }: PlayContext) {
  const canvas = within(canvasElement);
  await userEvent.click(await canvas.findByRole("button", { name: "Reject draft" }));
  return within(canvas.getByRole("region", { name: "Draft rejected" }));
}

/**
 * Acknowledge the warning of the draft and open the confirmation of Send reply (UI-17, UI-18).
 *
 * @param context - The story context.
 * @param context.canvasElement - The element that holds the story.
 * @returns The open confirmation.
 */
async function openConfirmation({ canvasElement }: PlayContext): Promise<HTMLElement> {
  const canvas = within(canvasElement);
  await userEvent.click(await canvas.findByRole("checkbox", { name: /^I have checked this/ }));
  await userEvent.click(canvas.getByRole("button", { name: "Send reply" }));
  return screen.findByRole("alertdialog", { name: "Send this reply to Lan Tran?" });
}

/**
 * Send the draft as is: open the confirmation and confirm it.
 *
 * @param context - The story context.
 */
async function sendDraft(context: PlayContext): Promise<void> {
  const dialog = await openConfirmation(context);
  await userEvent.click(within(dialog).getByRole("button", { name: "Send reply" }));
}

export const Editing: Story = {
  decorators: withAnswers({}),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.click(await canvas.findByRole("button", { name: "Edit draft" }));

    await expect(canvas.getByRole("region", { name: "Edit draft" })).toHaveTextContent(
      "Edited text is not checked against the sources.",
    );
  },
};
export const Rejected: Story = {
  decorators: withAnswers({}),
  play: async (context) => {
    const rejected = await rejectDraft(context);
    await userEvent.click(rejected.getByRole("button", { name: "Unsupported claim" }));

    await expect(rejected.getByRole("button", { name: "Unsupported claim" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  },
};
export const RejectedWithOther: Story = {
  decorators: withAnswers({}),
  play: async (context) => {
    const rejected = await rejectDraft(context);
    await userEvent.click(rejected.getByRole("button", { name: "Other" }));

    await expect(
      rejected.getByRole("textbox", { name: "Note for the reason Other" }),
    ).toBeVisible();
  },
};
export const PlaceholderInTheEditor: Story = {
  decorators: withAnswers({ workspace: [workspaceExample("manual-mode")] }),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    // user-event reads "[[" as one "[".
    await userEvent.type(
      await canvas.findByRole("textbox", { name: "Reply to the customer" }),
      "We sent the label to [[EMAIL].",
    );

    await expect(canvas.getByRole("button", { name: "Send reply" })).toBeDisabled();
    await expect(canvas.getByText("[EMAIL]").tagName).toBe("MARK");
  },
};
export const ConfirmSendOpen: Story = {
  decorators: withAnswers({}),
  play: async (context) => {
    const dialog = await openConfirmation(context);

    await expect(dialog).toHaveTextContent("A sent reply cannot be changed.");
  },
};
export const SendRefused: Story = {
  decorators: withAnswers({ reply: [exampleAnswer(409, "problems", "suggestion-superseded")] }),
  play: async (context) => {
    await sendDraft(context);

    await expect(await within(context.canvasElement).findByRole("alert")).toHaveTextContent(
      "The reply was not sent. The AI made a new draft for this ticket.",
    );
  },
};
export const SendOutcomeUnknown: Story = {
  decorators: withAnswers({ reply: [{ kind: "network_error" }] }),
  play: async (context) => {
    await sendDraft(context);

    await expect(await within(context.canvasElement).findByRole("alert")).toHaveTextContent(
      "The reply may have been sent. We could not confirm it.",
    );
  },
};
export const AiUnavailableWithTryAiAgain: Story = {
  decorators: withAnswers({ workspace: [workspaceExample("ai-service-unavailable")] }),
  play: async ({ canvasElement }) => {
    await expect(
      await within(canvasElement).findByRole("button", { name: "Try AI again" }),
    ).toBeEnabled();
  },
};
