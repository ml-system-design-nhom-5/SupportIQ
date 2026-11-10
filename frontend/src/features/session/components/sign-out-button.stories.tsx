import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect } from "storybook/test";

import { SignOutButton } from "@/features/session/components/sign-out-button";
import { deleteCurrentSessionRoute } from "@/test/backend-routes";
import { exampleAnswer } from "@/test/fake-backend";
import { withFakeBackend } from "@/test/story-backend";

const meta = {
  title: "Session/SignOutButton",
  component: SignOutButton,
  args: { placement: "app-bar" },
} satisfies Meta<typeof SignOutButton>;

export default meta;

type Story = StoryObj<typeof meta>;

export const InAppBar: Story = {};
export const InStateMessage: Story = { args: { placement: "state" } };

export const Failed: Story = {
  decorators: [
    withFakeBackend((backend) => {
      backend.answer(deleteCurrentSessionRoute, exampleAnswer(503, "problems", "not-ready"));
    }),
  ],
  play: async ({ canvas, userEvent }) => {
    await userEvent.click(canvas.getByRole("button", { name: "Sign out" }));

    await expect(await canvas.findByRole("alert")).toHaveTextContent("You are still signed in.");
  },
};

/** The story backend never answers, so nobody knows whether sign-out worked. */
export const OutcomeUnknown: Story = {
  play: async ({ canvas, userEvent }) => {
    await userEvent.click(canvas.getByRole("button", { name: "Sign out" }));

    await expect(await canvas.findByRole("alert")).toHaveTextContent(
      "We could not confirm that you signed out.",
    );
  },
};
