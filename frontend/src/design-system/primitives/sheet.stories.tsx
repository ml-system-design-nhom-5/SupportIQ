import type { Meta, StoryObj } from "@storybook/react-vite";
import { FileText } from "lucide-react";
import { expect, fn, screen } from "storybook/test";

import { Sheet } from "@/design-system/primitives/sheet";

const meta = {
  title: "Design system/Primitives/Sheet",
  component: Sheet,
  args: {
    icon: FileText,
    title: "Refund policy",
    returnFocus: { opener: document.body, fallbackId: "opener" },
    onClose: fn(),
    children: <p className="text-sm">The full text of the document version.</p>,
  },
} satisfies Meta<typeof Sheet>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Open: Story = {
  play: async () => {
    const sheet = await screen.findByRole("dialog", { name: "Refund policy" });

    await expect(sheet).toBeVisible();
    await expect(screen.getByRole("button", { name: "Close" })).toBeVisible();
  },
};
