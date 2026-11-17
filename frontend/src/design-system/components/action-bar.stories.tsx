import type { Meta, StoryObj } from "@storybook/react-vite";
import { CircleArrowUp, Clock, Pencil, Send, X } from "lucide-react";
import { expect, fn, screen, userEvent, within } from "storybook/test";

import { ActionBar } from "@/design-system/components/action-bar";
import { Button } from "@/design-system/primitives/button";

const submitForApproval = {
  icon: Clock,
  label: "Submit for approval",
  description: "A manager sends the reply",
  onSelect: fn(),
};

const meta = {
  title: "Design system/Components/ActionBar",
  component: ActionBar,
  args: {
    actions: (
      <>
        <Button leadingIcon={Pencil}>Edit draft</Button>
        <Button leadingIcon={X}>Reject draft</Button>
        <Button leadingIcon={CircleArrowUp}>Escalate ticket</Button>
      </>
    ),
    moreItems: [submitForApproval],
    primaryAction: (
      <Button variant="primary" leadingIcon={Send}>
        Send reply
      </Button>
    ),
  },
} satisfies Meta<typeof ActionBar>;

export default meta;

type Story = StoryObj<typeof meta>;

export const DraftReady: Story = {};
export const SendBlockedByWarning: Story = {
  args: {
    reason: "Acknowledge 1 warning to send the reply.",
    primaryAction: (
      <Button variant="primary" leadingIcon={Send} disabled>
        Send reply
      </Button>
    ),
  },
};
export const MoreMenuOpen: Story = {
  play: async ({ canvasElement }) => {
    const more = within(canvasElement).getByRole("button", { name: "More actions" });
    await userEvent.click(more);

    const menuItem = await screen.findByRole("menuitem", {
      name: "Submit for approval A manager sends the reply",
    });
    await expect(menuItem).toBeVisible();
    // The menu opens in the element after More, which generates no box, so it adds no gap.
    const menuHolder = more.nextElementSibling;
    await expect(menuHolder).toContainElement(menuItem);
    await expect(menuHolder?.getClientRects()).toHaveLength(0);
  },
};
export const MoreMenuByKeyboard: Story = {
  play: async ({ canvasElement }) => {
    within(canvasElement).getByRole("button", { name: "More actions" }).focus();
    await userEvent.keyboard("{Enter}");

    await expect(
      await screen.findByRole("menuitem", { name: /^Submit for approval/ }),
    ).toHaveFocus();
  },
};
export const MoreItemDisabled: Story = {
  args: {
    reason: "Write a reply to submit it for approval.",
    moreItems: [
      { ...submitForApproval, isDisabled: true },
      { icon: X, label: "Discard edits", onSelect: fn() },
    ],
  },
  play: async ({ canvasElement }) => {
    await userEvent.click(within(canvasElement).getByRole("button", { name: "More actions" }));

    await expect(
      await screen.findByRole("menuitem", { name: /^Submit for approval/ }),
    ).toHaveAttribute("aria-disabled", "true");
  },
};
export const EveryActionDisabled: Story = {
  args: {
    reason: "The AI is still working on this ticket.",
    actions: (
      <>
        <Button leadingIcon={Pencil} disabled>
          Edit draft
        </Button>
        <Button leadingIcon={X} disabled>
          Reject draft
        </Button>
        <Button leadingIcon={CircleArrowUp} disabled>
          Escalate ticket
        </Button>
      </>
    ),
    moreItems: [{ ...submitForApproval, isDisabled: true }],
    primaryAction: (
      <Button variant="primary" leadingIcon={Send} disabled>
        Send reply
      </Button>
    ),
  },
  play: async ({ canvasElement }) => {
    const more = within(canvasElement).getByRole("button", { name: "More actions" });
    await expect(more).toBeEnabled();
    await userEvent.click(more);

    await expect(
      await screen.findByRole("menuitem", { name: /^Submit for approval/ }),
    ).toHaveAttribute("aria-disabled", "true");
  },
};
export const MoreDisabledForManager: Story = {
  args: {
    reason: "Reject draft and Escalate ticket are not available while the ticket awaits approval.",
    actions: (
      <>
        <Button leadingIcon={Pencil}>Edit proposal</Button>
        <Button leadingIcon={X} disabled>
          Reject draft
        </Button>
        <Button leadingIcon={CircleArrowUp} disabled>
          Escalate ticket
        </Button>
      </>
    ),
    isMoreDisabled: true,
  },
  play: async ({ canvasElement }) => {
    await expect(
      within(canvasElement).getByRole("button", { name: "More actions" }),
    ).toBeDisabled();
  },
};
export const ManualHandlingWithoutMore: Story = {
  args: {
    reason: "Write a reply to send it or to submit it for approval.",
    actions: (
      <>
        <Button leadingIcon={CircleArrowUp}>Escalate ticket</Button>
        <Button leadingIcon={Clock} disabled>
          Submit for approval
        </Button>
      </>
    ),
    moreItems: [],
    primaryAction: (
      <Button variant="primary" leadingIcon={Send} disabled>
        Send reply
      </Button>
    ),
  },
  play: async ({ canvasElement }) => {
    await expect(
      within(canvasElement).queryByRole("button", { name: "More actions" }),
    ).not.toBeInTheDocument();
  },
};
