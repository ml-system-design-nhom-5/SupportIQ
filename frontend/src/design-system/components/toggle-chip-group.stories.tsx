import type { Meta, StoryObj } from "@storybook/react-vite";
import { useState } from "react";
import { expect, fn, userEvent, within } from "storybook/test";

import { ToggleChipGroup } from "@/design-system/components/toggle-chip-group";

const meta = {
  title: "Design system/Components/ToggleChipGroup",
  component: ToggleChipGroup,
  args: {
    label: "Why did you reject it?",
    options: [
      { value: "wrong_intent", label: "Wrong intent" },
      { value: "wrong_source", label: "Wrong source" },
      { value: "unsupported_claim", label: "Unsupported claim" },
      { value: "kb_gap", label: "KB gap" },
      { value: "missing_case_info", label: "Missing case info" },
      { value: "tone_or_clarity", label: "Tone or clarity" },
      { value: "case_exception", label: "Case exception" },
      { value: "other", label: "Other" },
    ],
    selected: new Set<string>(),
    onToggle: fn(),
  },
} satisfies Meta<typeof ToggleChipGroup<string>>;

export default meta;

type Story = StoryObj<typeof meta>;

export const NoneSelected: Story = {};
export const OneSelected: Story = { args: { selected: new Set(["unsupported_claim"]) } };
export const TwoSelected: Story = { args: { selected: new Set(["wrong_source", "kb_gap"]) } };
export const LabelHidden: Story = {
  args: { label: "Why do you escalate this ticket?", labelVisibility: "hidden" },
  play: async ({ canvasElement }) => {
    await expect(
      within(canvasElement).getByRole("group", { name: "Why do you escalate this ticket?" }),
    ).toBeVisible();
  },
};
export const WithError: Story = {
  args: {
    label: "Why do you escalate this ticket?",
    labelVisibility: "hidden",
    error: "Choose at least one reason.",
  },
  play: async ({ canvasElement }) => {
    await expect(
      within(canvasElement).getByRole("group", { name: "Why do you escalate this ticket?" }),
    ).toHaveAccessibleDescription("Choose at least one reason.");
  },
};
export const ToggleOnAndOff: Story = {
  render: (args) => <ControlledGroup {...args} />,
  play: async ({ canvasElement }) => {
    const group = within(canvasElement).getByRole("group", { name: "Why did you reject it?" });
    const chip = within(group).getByRole("button", { name: "Unsupported claim" });

    await userEvent.click(chip);
    await expect(chip).toHaveAttribute("aria-pressed", "true");
    await userEvent.click(chip);
    await expect(chip).toHaveAttribute("aria-pressed", "false");
  },
};

/**
 * Render the group with the chips that are on held in the story.
 *
 * @param props - The props of the group.
 * @returns The group.
 */
function ControlledGroup(props: Parameters<typeof ToggleChipGroup<string>>[0]) {
  const [selected, setSelected] = useState<ReadonlySet<string>>(props.selected);
  const handleToggle = (value: string) => {
    setSelected((current) => {
      const next = new Set(current);
      if (!next.delete(value)) {
        next.add(value);
      }
      return next;
    });
  };
  return <ToggleChipGroup {...props} selected={selected} onToggle={handleToggle} />;
}
