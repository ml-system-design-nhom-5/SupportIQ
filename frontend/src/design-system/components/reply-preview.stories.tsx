import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, fn, screen, within } from "storybook/test";

import { ReplyPreview } from "@/design-system/components/reply-preview";
import { ConfirmDialog } from "@/design-system/primitives/confirm-dialog";

const longReply =
  "Thank you for your patience.\n\nYour refund request for order ORD-20931 was received on 14 October and is currently under review. Refund requests are reviewed as described in our refund policy. If you have the tracking number for your return, please reply with it so we can confirm that the return has arrived.";

const meta = {
  title: "Design system/Components/ReplyPreview",
  component: ReplyPreview,
  args: { text: "Thank you for your patience. Your parcel is on its way." },
} satisfies Meta<typeof ReplyPreview>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Short: Story = {};
export const LongIsClamped: Story = {
  args: { text: longReply },
  play: async ({ canvasElement }) => {
    const clamped = within(canvasElement).getByText(/Thank you for your patience/);

    await expect(clamped.scrollHeight).toBeGreaterThan(clamped.clientHeight);
  },
};
export const InConfirmSendDialog: Story = {
  args: { text: longReply },
  render: (args) => (
    <ConfirmDialog
      isOpen
      text={{
        title: "Send this reply to Linh Tran?",
        description: (
          <>
            The customer sees it in the shop right away. A sent reply cannot be changed.
            <ReplyPreview {...args} />
          </>
        ),
        confirmLabel: "Send reply",
        pendingLabel: "Sending…",
        cancelLabel: "Keep editing",
      }}
      returnFocus={{ opener: document.body, fallbackId: "send-reply" }}
      isPending={false}
      onConfirm={fn()}
      onCancel={fn()}
    />
  ),
  play: async () => {
    const dialog = await screen.findByRole("alertdialog", {
      name: "Send this reply to Linh Tran?",
    });

    await expect(within(dialog).getByRole("button", { name: "Keep editing" })).toHaveFocus();
  },
};
