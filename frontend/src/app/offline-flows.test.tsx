import { onlineManager } from "@tanstack/react-query";
import { screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  createShopTicketRoute,
  getCurrentSessionRoute,
  getShopOrderRoute,
  listShopTicketsRoute,
} from "@/test/backend-routes";
import { createFakeBackend, exampleAnswer } from "@/test/fake-backend";
import { renderApp, testSettings } from "@/test/render-app";

describe("a hidden tab (ERR-13)", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("finishes the retries of a send, so the write never waits for the person to return", async () => {
    const backend = createFakeBackend();
    backend.answer(getCurrentSessionRoute, exampleAnswer(200, "getCurrentSession", "customer"));
    backend.answer(getShopOrderRoute, exampleAnswer(200, "getShopOrder", "refund-under-review"));
    backend.answer(listShopTicketsRoute, exampleAnswer(200, "listShopTickets", "last-page"));
    backend.answer(
      createShopTicketRoute,
      exampleAnswer(503, "problems", "not-ready"),
      exampleAnswer(201, "createShopTicket", "created"),
    );
    const { user } = renderApp({
      path: "/shop/orders/ORD-20931",
      backend,
      settings: { ...testSettings, requestRetryMaxCount: 1 },
    });
    const box = await screen.findByRole("textbox", { name: "Write to support about this order" });
    await user.type(box, "Is it shipped?");
    vi.spyOn(document, "visibilityState", "get").mockReturnValue("hidden");

    await user.click(screen.getByRole("button", { name: "Send message" }));

    expect(await screen.findByRole("status")).toHaveTextContent("Message sent.");
    expect(backend.requestsTo(createShopTicketRoute)).toHaveLength(2);
  });
});

describe("a browser that reports that it is offline (shop UI design, States)", () => {
  afterEach(() => {
    onlineManager.setOnline(true);
  });

  it("shows the error of a lost connection when a screen opens, instead of waiting", async () => {
    const backend = createFakeBackend();
    backend.answer(getCurrentSessionRoute, { kind: "network_error" });
    onlineManager.setOnline(false);

    renderApp({ path: "/shop/orders", backend });

    expect(
      await screen.findByRole("heading", { name: "Your session could not be checked" }),
    ).toBeVisible();
    expect(screen.getByText(/The server could not be reached/)).toBeVisible();
    expect(backend.requestsTo(getCurrentSessionRoute)).toHaveLength(1);
  });

  it("shows a failed send at once, keeps the text, and never sends it later", async () => {
    const backend = createFakeBackend();
    backend.answer(getCurrentSessionRoute, exampleAnswer(200, "getCurrentSession", "customer"));
    backend.answer(getShopOrderRoute, exampleAnswer(200, "getShopOrder", "refund-under-review"));
    backend.answer(listShopTicketsRoute, exampleAnswer(200, "listShopTickets", "last-page"));
    backend.answer(createShopTicketRoute, { kind: "network_error" });
    const { user } = renderApp({ path: "/shop/orders/ORD-20931", backend });
    const box = await screen.findByRole("textbox", { name: "Write to support about this order" });
    await user.type(box, "Is it shipped?");
    onlineManager.setOnline(false);

    await user.click(screen.getByRole("button", { name: "Send message" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Your message may have arrived.");
    expect(box).toHaveValue("Is it shipped?");
    onlineManager.setOnline(true);
    await user.click(box);
    expect(backend.requestsTo(createShopTicketRoute)).toHaveLength(1);
  });
});
