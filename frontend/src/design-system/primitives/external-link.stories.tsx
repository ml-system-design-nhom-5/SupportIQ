import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect } from "storybook/test";

import { ExternalLink } from "@/design-system/primitives/external-link";

const meta = {
  title: "Design system/Primitives/ExternalLink",
  component: ExternalLink,
  args: {
    href: "http://localhost:3000/explore?trace=4bf92f3577b34da6a3ce929d0e0e4736",
    children: "Open in Grafana",
  },
} satisfies Meta<typeof ExternalLink>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {
  play: async ({ canvas, args }) => {
    const link = canvas.getByRole("link", { name: "Open in Grafana (opens in a new tab)" });
    await expect(link).toHaveAttribute("href", args.href);
    await expect(link).toHaveAttribute("target", "_blank");
    await expect(link).toHaveAttribute("rel", "noreferrer");
  },
};
export const Strong: Story = { args: { emphasis: "strong" } };
