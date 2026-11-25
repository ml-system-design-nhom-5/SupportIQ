import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect } from "storybook/test";

import { OrderSupportSection } from "@/features/shop-support/components/order-support-section";
import { createShopTicketRoute, listShopTicketsRoute } from "@/test/backend-routes";
import { exampleAnswer } from "@/test/fake-backend";
import { withFakeBackend } from "@/test/story-backend";

const BOX_NAME = "Write to support about this order";

const meta = {
  title: "Shop/Support for this order",
  component: OrderSupportSection,
  args: { orderId: "ORD-20931", messageBoxId: "order-message" },
} satisfies Meta<typeof OrderSupportSection>;

export default meta;

type Story = StoryObj<typeof meta>;

export const ReceivedAndReplied: Story = {
  decorators: [
    withFakeBackend((backend) => {
      backend.answer(listShopTicketsRoute, exampleAnswer(200, "listShopTickets", "last-page"));
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

export const LoadingTickets: Story = {
  decorators: [
    withFakeBackend((backend) => {
      backend.answer(listShopTicketsRoute, { kind: "no_answer" });
    }),
  ],
};

export const TicketsFailed: Story = {
  decorators: [
    withFakeBackend((backend) => {
      backend.answer(listShopTicketsRoute, exampleAnswer(503, "problems", "not-ready"));
    }),
  ],
};

export const EarlierTicketsAvailable: Story = {
  decorators: [
    withFakeBackend((backend) => {
      backend.answer(listShopTicketsRoute, exampleAnswer(200, "listShopTickets", "first-page"));
    }),
  ],
};

export const LoadingEarlierTickets: Story = {
  decorators: [
    withFakeBackend((backend) => {
      backend.answer(listShopTicketsRoute, exampleAnswer(200, "listShopTickets", "first-page"), {
        kind: "no_answer",
      });
    }),
  ],
  play: async ({ canvas, userEvent }) => {
    await userEvent.click(await canvas.findByRole("button", { name: "Show earlier tickets" }));

    await expect(await canvas.findByRole("button", { name: "Loading…" })).toHaveAttribute(
      "aria-disabled",
      "true",
    );
  },
};

export const EarlierTicketsFailed: Story = {
  decorators: [
    withFakeBackend((backend) => {
      backend.answer(
        listShopTicketsRoute,
        exampleAnswer(200, "listShopTickets", "first-page"),
        exampleAnswer(503, "problems", "not-ready"),
      );
    }),
  ],
  play: async ({ canvas, userEvent }) => {
    await userEvent.click(await canvas.findByRole("button", { name: "Show earlier tickets" }));

    await expect(await canvas.findByRole("alert")).toHaveTextContent("Details: trace");
  },
};

export const Sending: Story = {
  decorators: [
    withFakeBackend((backend) => {
      backend.answer(listShopTicketsRoute, exampleAnswer(200, "listShopTickets", "empty"));
      backend.answer(createShopTicketRoute, { kind: "no_answer" });
    }),
  ],
  play: async ({ canvas, userEvent }) => {
    await userEvent.type(await canvas.findByRole("textbox", { name: BOX_NAME }), "Hello");
    await userEvent.click(canvas.getByRole("button", { name: "Send message" }));

    await expect(await canvas.findByRole("button", { name: "Sending…" })).toHaveAttribute(
      "aria-disabled",
      "true",
    );
  },
};

export const Sent: Story = {
  decorators: [
    withFakeBackend((backend) => {
      backend.answer(listShopTicketsRoute, exampleAnswer(200, "listShopTickets", "last-page"));
      backend.answer(createShopTicketRoute, exampleAnswer(201, "createShopTicket", "created"));
    }),
  ],
  play: async ({ canvas, userEvent }) => {
    await userEvent.type(await canvas.findByRole("textbox", { name: BOX_NAME }), "Hello");
    await userEvent.click(canvas.getByRole("button", { name: "Send message" }));

    await expect(await canvas.findByRole("status")).toHaveTextContent("Message sent.");
  },
};

export const SendFailed: Story = {
  decorators: [
    withFakeBackend((backend) => {
      backend.answer(listShopTicketsRoute, exampleAnswer(200, "listShopTickets", "empty"));
      backend.answer(createShopTicketRoute, exampleAnswer(503, "problems", "not-ready"));
    }),
  ],
  play: async ({ canvas, userEvent }) => {
    await userEvent.type(await canvas.findByRole("textbox", { name: BOX_NAME }), "Hello");
    await userEvent.click(canvas.getByRole("button", { name: "Send message" }));

    await expect(await canvas.findByRole("alert")).toHaveTextContent("Your message was not sent.");
  },
};

export const SendOutcomeUnknown: Story = {
  decorators: [
    withFakeBackend((backend) => {
      backend.answer(listShopTicketsRoute, exampleAnswer(200, "listShopTickets", "empty"));
      backend.answer(createShopTicketRoute, { kind: "ingress", status: 504 });
    }),
  ],
  play: async ({ canvas, userEvent }) => {
    await userEvent.type(await canvas.findByRole("textbox", { name: BOX_NAME }), "Hello");
    await userEvent.click(canvas.getByRole("button", { name: "Send message" }));

    await expect(await canvas.findByRole("alert")).toHaveTextContent(
      "Your message may have arrived.",
    );
  },
};
