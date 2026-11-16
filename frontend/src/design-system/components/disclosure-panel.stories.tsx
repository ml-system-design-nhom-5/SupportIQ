import type { Meta, StoryObj } from "@storybook/react-vite";
import { Code } from "lucide-react";
import { expect } from "storybook/test";

import { DisclosurePanel } from "@/design-system/components/disclosure-panel";
import { DescriptionList } from "@/design-system/primitives/description-list";

const meta = {
  title: "Design system/Components/DisclosurePanel",
  component: DisclosurePanel,
  decorators: [
    (Story) => (
      <section aria-label="AI details" className="flex w-ai-sidebar flex-col gap-4">
        <Story />
      </section>
    ),
  ],
  args: {
    title: "Developer details",
    icon: Code,
    children: (
      <DescriptionList
        items={[
          { term: "Trace", description: "4bf92f3577b34da6a3ce929d0e0e4736" },
          { term: "Release", description: "release-2026-11-12-sample" },
          { term: "Status", description: "draft_ready" },
        ]}
      />
    ),
  },
} satisfies Meta<typeof DisclosurePanel>;

export default meta;

type Story = StoryObj<typeof meta>;

/** The row of the mockups: closed, so the content is not rendered. */
export const Closed: Story = {
  play: async ({ canvas }) => {
    await expect(canvas.getByRole("button", { name: "Developer details" })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
    await expect(canvas.queryByText("Release")).not.toBeInTheDocument();
  },
};
export const Open: Story = { args: { isDefaultOpen: true } };
/** Below panels whose headings are level 3, so its heading is level 3 too (UI-30). */
export const HeadingLevel3: Story = {
  args: { level: 3 },
  play: async ({ canvas }) => {
    await expect(
      canvas.getByRole("heading", { level: 3, name: "Developer details" }),
    ).toContainElement(canvas.getByRole("button", { name: "Developer details" }));
  },
};
/** A person opens the closed panel. */
export const OpenedByClick: Story = {
  play: async ({ canvas, userEvent }) => {
    const button = canvas.getByRole("button", { name: "Developer details" });
    await userEvent.click(button);

    await expect(button).toHaveAttribute("aria-expanded", "true");
    await expect(canvas.getByText("release-2026-11-12-sample")).toBeVisible();
  },
};
