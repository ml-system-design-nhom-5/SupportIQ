import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, screen, userEvent, within } from "storybook/test";

import { TicketWorkspacePage } from "@/features/console-tickets/components/ticket-workspace-page";
import {
  answerConsole,
  type ConsoleAnswers,
  workspaceExample,
  workspaceWithSuggestion,
} from "@/test/console-screen";
import { ConsoleStoryFrame } from "@/test/console-story-frame";
import { readOperationExample } from "@/test/contract-examples";
import { exampleAnswer } from "@/test/fake-backend";
import { withFakeBackend } from "@/test/story-backend";

const meta = {
  title: "Console/TicketWorkspace/Intent correction",
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
 * @param answers - The answers that differ from the defaults.
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
 * Use the first candidate of the strip, as staff do.
 *
 * @param context - The story context.
 * @param context.canvasElement - The element that holds the story.
 */
async function chooseRequestRefund({ canvasElement }: { readonly canvasElement: HTMLElement }) {
  await userEvent.click(
    await within(canvasElement).findByRole("button", { name: "Use Request refund 7%" }),
  );
}

export const Correctable: Story = { decorators: withAnswers({}) };
export const CorrectableWhileGenerating: Story = {
  decorators: withAnswers({
    workspace: [workspaceWithSuggestion("draft-ready", { draft: { draft_status: "pending" } })],
  }),
};
export const IntentChanged: Story = {
  decorators: withAnswers({
    workspace: [
      workspaceExample("draft-ready"),
      workspaceWithSuggestion(
        "draft-ready",
        readOperationExample("createSuggestion", 202, "intent-override"),
      ),
    ],
  }),
  play: async (context) => {
    await chooseRequestRefund(context);

    await expect(
      await within(context.canvasElement).findByRole("region", { name: "Outdated draft" }),
    ).toBeVisible();
  },
};
export const OtherIntentOpen: Story = {
  decorators: withAnswers({}),
  play: async ({ canvasElement }) => {
    await userEvent.click(
      await within(canvasElement).findByRole("button", { name: "Other intent" }),
    );

    await expect(await screen.findByRole("menuitem", { name: "Request refund" })).toBeVisible();
  },
};
export const ChooseAnIntent: Story = {
  decorators: withAnswers({ workspace: [workspaceExample("abstained-low-confidence")] }),
};
export const CorrectionFailed: Story = {
  decorators: withAnswers({ suggestion: [exampleAnswer(409, "problems", "suggestion-pending")] }),
  play: async (context) => {
    await chooseRequestRefund(context);

    await expect(await within(context.canvasElement).findByRole("alert")).toHaveTextContent(
      "The intent was not changed.",
    );
  },
};
