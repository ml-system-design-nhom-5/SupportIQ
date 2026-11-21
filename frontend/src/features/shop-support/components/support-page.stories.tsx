import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect } from "storybook/test";

import { SupportPage } from "@/features/shop-support/components/support-page";
import { listShopTicketsRoute } from "@/test/backend-routes";
import { exampleAnswer } from "@/test/fake-backend";
import { withFakeBackend } from "@/test/story-backend";

const meta = {
  title: "Shop/Support",
  component: SupportPage,
} satisfies Meta<typeof SupportPage>;

export default meta;

type Story = StoryObj<typeof meta>;

export const WithTickets: Story = {
  decorators: [
    withFakeBackend((backend) => {
      backend.answer(listShopTicketsRoute, exampleAnswer(200, "listShopTickets", "last-page"));
    }),
  ],
};

export const WithNextPage: Story = {
  decorators: [
    withFakeBackend((backend) => {
      backend.answer(listShopTicketsRoute, exampleAnswer(200, "listShopTickets", "first-page"));
    }),
  ],
};

export const Loading: Story = {
  decorators: [
    withFakeBackend((backend) => {
      backend.answer(listShopTicketsRoute, { kind: "no_answer" });
    }),
  ],
};

export const NoTickets: Story = {
  decorators: [
    withFakeBackend((backend) => {
      backend.answer(listShopTicketsRoute, exampleAnswer(200, "listShopTickets", "empty"));
    }),
  ],
};

export const PermissionDenied: Story = {
  decorators: [
    withFakeBackend((backend) => {
      backend.answer(listShopTicketsRoute, exampleAnswer(403, "problems", "forbidden-role"));
    }),
  ],
};

export const LoadError: Story = {
  decorators: [
    withFakeBackend((backend) => {
      backend.answer(listShopTicketsRoute, { kind: "ingress", status: 502 });
    }),
  ],
};

export const LoadingMore: Story = {
  decorators: [
    withFakeBackend((backend) => {
      backend.answer(listShopTicketsRoute, exampleAnswer(200, "listShopTickets", "first-page"), {
        kind: "no_answer",
      });
    }),
  ],
  play: async ({ canvas, userEvent }) => {
    await userEvent.click(await canvas.findByRole("button", { name: "Show more messages" }));

    await expect(await canvas.findByRole("button", { name: "Loading…" })).toHaveAttribute(
      "aria-disabled",
      "true",
    );
  },
};

export const LoadingMoreFailed: Story = {
  decorators: [
    withFakeBackend((backend) => {
      backend.answer(listShopTicketsRoute, exampleAnswer(200, "listShopTickets", "first-page"), {
        kind: "network_error",
      });
    }),
  ],
  play: async ({ canvas, userEvent }) => {
    await userEvent.click(await canvas.findByRole("button", { name: "Show more messages" }));

    await expect(await canvas.findByRole("alert")).toHaveTextContent(
      "More messages could not be loaded.",
    );
  },
};
