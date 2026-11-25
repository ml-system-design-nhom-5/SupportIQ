import type { Meta, StoryObj } from "@storybook/react-vite";
import { useState } from "react";
import { expect, screen } from "storybook/test";

import { Tooltip, TooltipHint } from "@/design-system/primitives/tooltip";

const meta = {
  title: "Design system/Primitives/Tooltip",
  component: Tooltip,
  args: { content: "2 Oct 2026, 19:30", children: "3 weeks ago" },
} satisfies Meta<typeof Tooltip>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Closed: Story = {};

export const OpenOnFocus: Story = {
  play: async ({ userEvent }) => {
    await userEvent.tab();

    await expect(await screen.findByRole("tooltip")).toHaveTextContent("2 Oct 2026, 19:30");
  },
};

/**
 * Render a card hint that is open, as a citation marker shows its source.
 *
 * @returns The trigger and the hint.
 */
function OpenCardHint() {
  const [isOpen, setIsOpen] = useState(true);
  return (
    <TooltipHint
      variant="card"
      isOpen={isOpen}
      onOpenChange={setIsOpen}
      trigger={<button type="button">Source 1</button>}
    >
      <p className="p-3">Refund policy · refund-policy · v3</p>
    </TooltipHint>
  );
}

export const CardHint: Story = {
  render: () => <OpenCardHint />,
  play: async () => {
    await expect(await screen.findByRole("tooltip")).toHaveTextContent("Refund policy");
  },
};
