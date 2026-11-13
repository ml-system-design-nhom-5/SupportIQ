import type { Meta, StoryObj } from "@storybook/react-vite";
import { fn } from "storybook/test";

import { ConfirmDialog } from "@/design-system/primitives/confirm-dialog";

const meta = {
  title: "Design system/Primitives/ConfirmDialog",
  component: ConfirmDialog,
  args: {
    isOpen: true,
    text: {
      title: "Make Mai Nguyen a manager?",
      description:
        "Mai Nguyen will be able to send replies on tickets that require authority and to view reports. Mai Nguyen will be signed out of every session.",
      confirmLabel: "Make manager",
      pendingLabel: "Making manager…",
    },
    returnFocus: { opener: document.body, fallbackId: "row" },
    isPending: false,
    onConfirm: fn(),
    onCancel: fn(),
  },
} satisfies Meta<typeof ConfirmDialog>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {};
export const Danger: Story = {
  args: {
    text: {
      title: "Deactivate Minh Le?",
      description:
        "Minh Le will be signed out of every session and cannot sign in until an admin reactivates the account.",
      confirmLabel: "Deactivate",
      pendingLabel: "Deactivating…",
    },
    tone: "danger",
  },
};
export const CancelLabel: Story = {
  args: {
    text: {
      title: "Send this reply to Linh Tran?",
      description: "The customer sees it in the shop right away. A sent reply cannot be changed.",
      confirmLabel: "Send reply",
      pendingLabel: "Sending…",
      cancelLabel: "Keep editing",
    },
  },
};
export const Pending: Story = { args: { isPending: true } };
export const Closed: Story = { args: { isOpen: false } };
