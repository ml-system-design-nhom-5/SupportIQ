import type { Meta, StoryObj } from "@storybook/react-vite";
import { Inbox, Lock, LogOut, RotateCcw, SearchX, TriangleAlert } from "lucide-react";

import { StateMessage } from "@/design-system/components/state-message";
import { Button } from "@/design-system/primitives/button";
import { ButtonLink } from "@/design-system/primitives/button-link";

const meta = {
  title: "Design system/Components/StateMessage",
  component: StateMessage,
  args: { icon: SearchX, headingLevel: 1, title: "This order was not found" },
} satisfies Meta<typeof StateMessage>;

export default meta;

type Story = StoryObj<typeof meta>;

export const NotFound: Story = {
  args: {
    description: "It may not exist, or it belongs to another account.",
    actions: <ButtonLink to="/shop/orders">Back to My orders</ButtonLink>,
  },
};
export const PermissionDenied: Story = {
  args: {
    icon: Lock,
    title: "The shop is for customer accounts",
    description:
      "You are signed in with a support or admin account. Sign out, then sign in with a customer account.",
    actions: <Button leadingIcon={LogOut}>Sign out</Button>,
    traceId: "b7ad6b7169203331b7ad6b7169203331",
  },
};
export const LoadError: Story = {
  args: {
    icon: TriangleAlert,
    title: "Your orders could not be loaded",
    description: "The service is not available right now. Try again in a moment.",
    actions: <Button leadingIcon={RotateCcw}>Try again</Button>,
    traceId: "1c80319c0af7651916cd43dd8448eb21",
  },
};
export const Empty: Story = {
  args: {
    icon: Inbox,
    headingLevel: 2,
    title: "You have no orders yet.",
  },
};
