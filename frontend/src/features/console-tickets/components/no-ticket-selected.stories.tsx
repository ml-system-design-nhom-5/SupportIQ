import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, screen, userEvent, within } from "storybook/test";

import { NoTicketSelected } from "@/features/console-tickets/components/no-ticket-selected";
import { answerConsole, type ConsoleAnswers } from "@/test/console-screen";
import { ConsoleStoryFrame } from "@/test/console-story-frame";
import { exampleAnswer } from "@/test/fake-backend";
import { withFakeBackend } from "@/test/story-backend";

const meta = {
  title: "Console/Inbox",
  component: NoTicketSelected,
  parameters: { layout: "fullscreen" },
  render: () => (
    <ConsoleStoryFrame>
      <NoTicketSelected />
    </ConsoleStoryFrame>
  ),
} satisfies Meta<typeof NoTicketSelected>;

export default meta;

type Story = StoryObj<typeof meta>;

/**
 * Build the decorator of a story whose console answers as given.
 *
 * @param answers - The answers that differ from the defaults.
 * @returns The decorators of the story.
 */
function withConsole(answers: ConsoleAnswers) {
  return [
    withFakeBackend((backend) => {
      answerConsole(backend, answers);
    }),
  ];
}

export const OpenQueue: Story = { decorators: withConsole({}) };
export const Empty: Story = {
  decorators: withConsole({ queue: [exampleAnswer(200, "listConsoleTickets", "empty")] }),
};
export const Loading: Story = { decorators: withConsole({ queue: [{ kind: "no_answer" }] }) };
export const Error: Story = {
  decorators: withConsole({ queue: [exampleAnswer(500, "problems", "internal-error")] }),
};
export const PermissionDenied: Story = {
  decorators: withConsole({
    session: "customer",
    queue: [exampleAnswer(403, "problems", "forbidden-role")],
  }),
};
export const ManagerQueues: Story = {
  decorators: withConsole({ session: "manager" }),
  play: async ({ canvasElement }) => {
    await userEvent.click(
      await within(canvasElement).findByRole("button", { name: "Ticket status: Open" }),
    );

    await expect(await screen.findAllByRole("menuitemradio")).toHaveLength(4);
  },
};
