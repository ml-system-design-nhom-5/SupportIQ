import type { Meta, StoryObj } from "@storybook/react-vite";
import { useState } from "react";
import { expect, screen, userEvent, within } from "storybook/test";

import { Popover } from "@/design-system/primitives/popover";

const meta = {
  title: "Design system/Primitives/Popover",
  component: Popover,
  args: {
    trigger: <button type="button">Open details</button>,
    label: "Details",
    isOpen: false,
    onOpenChange: () => undefined,
    children: <p className="p-4">Content with its own controls.</p>,
  },
  render: (args) => <ControlledPopover {...args} />,
} satisfies Meta<typeof Popover>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Narrow: Story = {
  play: async ({ canvasElement }) => {
    await userEvent.click(within(canvasElement).getByRole("button", { name: "Open details" }));

    await expect(await screen.findByRole("dialog", { name: "Details" })).toBeVisible();
  },
};
export const Wide: Story = { args: { width: "wide", isOpen: true } };

/**
 * Render the popover with its open state held in the story.
 *
 * @param props - The props of the popover.
 * @returns The popover.
 */
function ControlledPopover(props: Parameters<typeof Popover>[0]) {
  const [isOpen, setIsOpen] = useState(props.isOpen);
  return <Popover {...props} isOpen={isOpen} onOpenChange={setIsOpen} />;
}
