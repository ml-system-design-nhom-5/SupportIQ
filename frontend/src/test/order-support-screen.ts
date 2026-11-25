/**
 * Support for this order in tests: open the order page with fake answers, and send a message.
 */
import { screen } from "@testing-library/react";

import {
  createShopTicketRoute,
  getCurrentSessionRoute,
  getShopOrderRoute,
  listShopTicketsRoute,
} from "@/test/backend-routes";
import { createFakeBackend, exampleAnswer, type FakeAnswer } from "@/test/fake-backend";
import { renderApp, testSettings } from "@/test/render-app";

export const BOX_NAME = "Write to support about this order";

/** What the order page of a test receives. */
export type SupportAnswers = {
  readonly tickets?: readonly FakeAnswer[];
  readonly creates?: readonly FakeAnswer[];
  readonly settings?: typeof testSettings;
};

/**
 * Open the order ORD-20931 as a customer with the given ticket answers.
 *
 * @param answers - The answers of `listShopTickets` and `createShopTicket`, and the settings.
 * @returns The rendered app.
 */
export function openOrderSupport(answers: SupportAnswers = {}) {
  const backend = createFakeBackend();
  backend.answer(getCurrentSessionRoute, exampleAnswer(200, "getCurrentSession", "customer"));
  backend.answer(getShopOrderRoute, exampleAnswer(200, "getShopOrder", "refund-under-review"));
  backend.answer(
    listShopTicketsRoute,
    ...(answers.tickets ?? [exampleAnswer(200, "listShopTickets", "last-page")]),
  );
  backend.answer(
    createShopTicketRoute,
    ...(answers.creates ?? [exampleAnswer(201, "createShopTicket", "created")]),
  );
  return renderApp({
    path: "/shop/orders/ORD-20931",
    backend,
    settings: answers.settings ?? testSettings,
  });
}

/**
 * Type a message and choose Send message.
 *
 * @param user - The user-event instance.
 * @param message - The text to type.
 */
export async function sendMessage(user: ReturnType<typeof renderApp>["user"], message: string) {
  await user.type(await screen.findByRole("textbox", { name: BOX_NAME }), message);
  await user.click(screen.getByRole("button", { name: "Send message" }));
}
