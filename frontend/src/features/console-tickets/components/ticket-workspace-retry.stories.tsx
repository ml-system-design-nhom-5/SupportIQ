import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, userEvent, within } from "storybook/test";

import { TicketWorkspacePage } from "@/features/console-tickets/components/ticket-workspace-page";
import { answerConsole, type ConsoleAnswers, workspaceExample } from "@/test/console-screen";
import { ConsoleStoryFrame } from "@/test/console-story-frame";
import { exampleAnswer } from "@/test/fake-backend";
import { withFakeBackend } from "@/test/story-backend";

const meta = {
  title: "Console/TicketWorkspace/Try AI again",
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
 * @param answers - The answers that differ from the defaults; the ai-service-unavailable
 *   workspace, which allows `retry_suggestion`, by default.
 * @returns The decorators of the story.
 */
function withAnswers(answers: ConsoleAnswers) {
  return [
    withFakeBackend((backend) => {
      answerConsole(backend, {
        workspace: [workspaceExample("ai-service-unavailable")],
        ...answers,
      });
    }),
  ];
}

/**
 * Use Try AI again, as staff do.
 *
 * @param context - The story context.
 * @param context.canvasElement - The element that holds the story.
 */
async function tryAiAgain({ canvasElement }: { readonly canvasElement: HTMLElement }) {
  await userEvent.click(await within(canvasElement).findByRole("button", { name: "Try AI again" }));
}

export const RetryRefused: Story = {
  decorators: withAnswers({ suggestion: [exampleAnswer(422, "problems", "nothing-to-retry")] }),
  play: async (context) => {
    await tryAiAgain(context);

    await expect(await within(context.canvasElement).findByRole("alert")).toHaveTextContent(
      "The AI did not start again. This ticket changed in the meantime.",
    );
  },
};
export const RetryOutcomeUnknown: Story = {
  decorators: withAnswers({ suggestion: [{ kind: "network_error" }] }),
  play: async (context) => {
    await tryAiAgain(context);

    await expect(await within(context.canvasElement).findByRole("alert")).toHaveTextContent(
      "The AI may have started again. The server could not be reached.",
    );
  },
};
export const WithoutRetry: Story = {
  decorators: withAnswers({ workspace: [workspaceExample("pseudonymization-failed")] }),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByRole("heading", { level: 1, name: /^Ticket / });

    await expect(canvas.queryByRole("button", { name: "Try AI again" })).toBeNull();
  },
};
