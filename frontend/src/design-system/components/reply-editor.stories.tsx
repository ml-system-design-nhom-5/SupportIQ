import type { Meta, StoryObj } from "@storybook/react-vite";
import { useState } from "react";
import { expect, fn, userEvent, within } from "storybook/test";

import { ReplyEditor } from "@/design-system/components/reply-editor";

const editedDraft =
  "Thank you for your patience.\n\nYour refund request for order ORD-20931 was received on 14 October and is currently under review. Refund requests are reviewed as described in our refund policy. Please reply with the tracking number of your return.";

const sourcesHint = "Edited text is not checked against the sources.";
const placeholderHint = "Personal data or reserved text: replace before sending";

const meta = {
  title: "Design system/Components/ReplyEditor",
  component: ReplyEditor,
  args: {
    label: "Reply to the customer",
    value: "",
    onChange: fn(),
    markedParts: [],
    placeholder: "Write the reply to the customer",
  },
} satisfies Meta<typeof ReplyEditor>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Empty: Story = {};
export const EditedDraft: Story = {
  args: {
    value: editedDraft,
    markedParts: [{ text: editedDraft, isMarked: false }],
    hints: [sourcesHint],
  },
  play: async ({ canvasElement }) => {
    await expect(
      within(canvasElement).getByRole("textbox", { name: "Reply to the customer" }),
    ).toHaveAccessibleDescription(sourcesHint);
  },
};
export const WithPlaceholder: Story = {
  args: {
    value: "We have sent the return label to [EMAIL]. Please reply with the tracking number.",
    markedParts: [
      { text: "We have sent the return label to ", isMarked: false },
      { text: "[EMAIL]", isMarked: true },
      { text: ". Please reply with the tracking number.", isMarked: false },
    ],
    hints: [sourcesHint, placeholderHint],
  },
  play: async ({ canvasElement }) => {
    await expect(within(canvasElement).getByText("[EMAIL]").tagName).toBe("MARK");
  },
};
export const LongTextGrows: Story = {
  args: {
    value: `${editedDraft}\n\n${editedDraft}\n\n${editedDraft} [NAME]\n`,
    markedParts: [
      { text: `${editedDraft}\n\n${editedDraft}\n\n${editedDraft} `, isMarked: false },
      { text: "[NAME]", isMarked: true },
      { text: "\n", isMarked: false },
    ],
  },
  play: async ({ canvasElement }) => {
    const editor = within(canvasElement).getByRole("textbox", { name: "Reply to the customer" });
    const backdrop = within(canvasElement).getByText("[NAME]").parentElement;

    // Both layers fit their text in the one box, so the marks stay under their text.
    await expect(editor.scrollHeight).toBe(editor.clientHeight);
    await expect(backdrop?.scrollHeight).toBe(backdrop?.clientHeight);
  },
};
export const WithLengthLimit: Story = {
  args: { value: "Hello", markedParts: [{ text: "Hello", isMarked: false }], maxLength: 10 },
  render: (args) => <ControlledEditor {...args} />,
  play: async ({ canvasElement }) => {
    const editor = within(canvasElement).getByRole("textbox", { name: "Reply to the customer" });

    await userEvent.type(editor, " there, friend");

    await expect(editor).toHaveValue("Hello ther");
  },
};

/**
 * Render the editor with its text held in the story. The story marks nothing.
 *
 * @param props - The props of the editor.
 * @returns The editor.
 */
function ControlledEditor(props: Parameters<typeof ReplyEditor>[0]) {
  const [value, setValue] = useState(props.value);
  return (
    <ReplyEditor
      {...props}
      value={value}
      markedParts={[{ text: value, isMarked: false }]}
      onChange={setValue}
    />
  );
}
