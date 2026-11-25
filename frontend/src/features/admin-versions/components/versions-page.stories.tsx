import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect } from "storybook/test";

import { VersionsPage } from "@/features/admin-versions/components/versions-page";
import { exampleAnswer, type FakeAnswer } from "@/test/fake-backend";
import { withFakeBackend } from "@/test/story-backend";
import { answerVersions, versionsExample } from "@/test/versions-screen";

const meta = {
  title: "Admin/Versions",
  component: VersionsPage,
} satisfies Meta<typeof VersionsPage>;

export default meta;

type Story = StoryObj<typeof meta>;

/**
 * Build the decorators of a story whose versions answer as given, for the admin session.
 *
 * @param versions - The answer of `getAdminVersions`.
 * @returns The decorators of the story.
 */
function withVersions(versions: FakeAnswer) {
  return [
    withFakeBackend((backend) => {
      answerVersions(backend, { versions: [versions] });
    }),
  ];
}

export const Available: Story = {
  decorators: withVersions(versionsExample("ai-service-available")),
  play: async ({ canvas }) => {
    await expect(await canvas.findByText("release-2026-11-12-sample")).toBeVisible();
    await expect(canvas.getByText("Available")).toBeVisible();
  },
};

export const AiServiceUnavailable: Story = {
  decorators: withVersions(versionsExample("ai-service-unavailable")),
  play: async ({ canvas }) => {
    await expect(await canvas.findByRole("alert")).toHaveTextContent(
      "ai-service cannot be reached.",
    );
    await expect(canvas.getAllByText("Unknown")).toHaveLength(7);
    await expect(canvas.getByText("880b33a")).toBeVisible();
  },
};

export const Loading: Story = { decorators: withVersions({ kind: "no_answer" }) };

export const LoadError: Story = {
  decorators: withVersions(exampleAnswer(500, "problems", "internal-error")),
  play: async ({ canvas }) => {
    await expect(
      await canvas.findByRole("heading", { name: "The versions could not be loaded" }),
    ).toBeVisible();
    await expect(canvas.getByRole("button", { name: "Try again" })).toBeVisible();
  },
};

export const PermissionDenied: Story = {
  decorators: withVersions(exampleAnswer(403, "problems", "forbidden-role")),
  play: async ({ canvas }) => {
    await expect(
      await canvas.findByRole("heading", { name: "The admin area is for admin accounts" }),
    ).toBeVisible();
  },
};
