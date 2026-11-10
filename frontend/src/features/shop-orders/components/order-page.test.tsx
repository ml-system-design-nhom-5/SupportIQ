import { act, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import {
  getCurrentSessionRoute,
  getShopOrderRoute,
  listShopTicketsRoute,
} from "@/test/backend-routes";
import { readExampleWith } from "@/test/contract-examples";
import { createFakeBackend, exampleAnswer, type FakeAnswer } from "@/test/fake-backend";
import { renderApp } from "@/test/render-app";

/**
 * Open the order ORD-20931 as a customer.
 *
 * @param orderAnswers - The answers of `getShopOrder`, in order.
 * @returns The rendered app.
 */
function openOrder(...orderAnswers: FakeAnswer[]) {
  const backend = createFakeBackend();
  backend.answer(getCurrentSessionRoute, exampleAnswer(200, "getCurrentSession", "customer"));
  backend.answer(getShopOrderRoute, ...orderAnswers);
  backend.answer(listShopTicketsRoute, exampleAnswer(200, "listShopTickets", "last-page"));
  return renderApp({ path: "/shop/orders/ORD-20931", backend });
}

/**
 * Send the event that the browser sends when the window regains focus.
 */
function refocusWindow(): void {
  act(() => {
    window.dispatchEvent(new Event("focus"));
  });
}

describe("OrderPage", () => {
  it.each([
    ["no member", {}],
    [
      "a line without members",
      readExampleWith("getShopOrder", "refund-under-review", { lines: [{}] }),
    ],
    [
      "a shipment without members",
      readExampleWith("getShopOrder", "refund-under-review", { shipment: {} }),
    ],
    [
      "a total without members",
      readExampleWith("getShopOrder", "refund-under-review", { order_total: {} }),
    ],
    [
      "a refund with only an amount",
      readExampleWith("getShopOrder", "refund-under-review", {
        refund: { refund_amount: { amount_minor: 1, currency: "USD" } },
      }),
    ],
  ])("shows the error state for an order with %s", async (_case, body) => {
    openOrder({ kind: "body", status: 200, body });

    expect(
      await screen.findByRole("heading", { level: 1, name: "This order could not be loaded" }),
    ).toBeVisible();
  });

  it("shows the order with its statuses, dates, lines, and total", async () => {
    openOrder(exampleAnswer(200, "getShopOrder", "refund-under-review"));

    expect(await screen.findByRole("heading", { level: 1, name: "Order ORD-20931" })).toBeVisible();
    const details = screen.getByRole("region", { name: "Order details" });
    expect(details).toHaveTextContent("OrderDeliveredPlaced 2 Oct 2026");
    expect(details).toHaveTextContent("ShipmentDelivered6 Oct 2026");
    expect(details).toHaveTextContent("RefundRefund under reviewRequested 14 Oct 2026");
    expect(within(details).getByRole("link", { name: "Wireless headphones" })).toHaveAttribute(
      "href",
      "/shop/products/PRD-1002",
    );
    expect(within(details).getByText("$89.00")).toBeVisible();
  });

  it("shows No refund and the delivery estimate of an order without a refund", async () => {
    openOrder(exampleAnswer(200, "getShopOrder", "in-transit"));

    const details = await screen.findByRole("region", { name: "Order details" });

    expect(details).toHaveTextContent("ShipmentIn transitExpected 7 Nov 2026");
    expect(details).toHaveTextContent("RefundNo refundNot requested");
  });

  it("leaves the focus out of the message box when the order opens", async () => {
    const { user } = openOrder(exampleAnswer(200, "getShopOrder", "refund-under-review"));

    const box = await screen.findByRole("textbox", { name: "Write to support about this order" });
    // Moving the pointer waits for the browser's task queue, so the effects of the box ran.
    await user.hover(box);

    expect(box).not.toHaveFocus();
  });

  it("moves the focus to the message box with Contact support", async () => {
    const { user } = openOrder(exampleAnswer(200, "getShopOrder", "refund-under-review"));

    await user.click(await screen.findByRole("button", { name: "Contact support" }));

    expect(
      screen.getByRole("textbox", { name: "Write to support about this order" }),
    ).toHaveFocus();
  });

  it("shows a loading state under the path back to My orders", async () => {
    openOrder({ kind: "no_answer" });

    expect(await screen.findByText("Loading the order…")).toBeInTheDocument();
    const breadcrumb = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(within(breadcrumb).getByRole("link", { name: "My orders" })).toHaveAttribute(
      "href",
      "/shop/orders",
    );
  });
});

describe("OrderPage, reloading on focus (shop UI design, Alternatives considered)", () => {
  it("loads the order again when the window regains focus, and shows the change", async () => {
    const { backend } = openOrder(
      exampleAnswer(200, "getShopOrder", "refund-under-review"),
      exampleAnswer(200, "getShopOrder", "in-transit"),
    );
    await screen.findByRole("region", { name: "Order details" });

    refocusWindow();

    await waitFor(() => {
      expect(screen.getByRole("region", { name: "Order details" })).toHaveTextContent("In transit");
    });
    expect(backend.requestsTo(getShopOrderRoute)).toHaveLength(2);
  });

  it("loads the tickets again when the window regains focus, so a reply appears", async () => {
    const backend = createFakeBackend();
    backend.answer(getCurrentSessionRoute, exampleAnswer(200, "getCurrentSession", "customer"));
    backend.answer(getShopOrderRoute, exampleAnswer(200, "getShopOrder", "refund-under-review"));
    backend.answer(
      listShopTicketsRoute,
      exampleAnswer(200, "listShopTickets", "empty"),
      exampleAnswer(200, "listShopTickets", "last-page"),
    );
    renderApp({ path: "/shop/orders/ORD-20931", backend });
    await screen.findByRole("region", { name: "Order details" });
    await waitFor(() => {
      expect(backend.requestsTo(listShopTicketsRoute)).toHaveLength(1);
    });

    refocusWindow();

    expect(await screen.findByText("Reply from support")).toBeVisible();
    expect(backend.requestsTo(listShopTicketsRoute)).toHaveLength(2);
  });

  it("loads the order again when the tab becomes visible again", async () => {
    const { backend } = openOrder(exampleAnswer(200, "getShopOrder", "refund-under-review"));
    await screen.findByRole("region", { name: "Order details" });

    act(() => {
      document.dispatchEvent(new Event("visibilitychange"));
    });

    await waitFor(() => {
      expect(backend.requestsTo(getShopOrderRoute)).toHaveLength(2);
    });
  });

  it("does not load the order again when the tab is hidden", async () => {
    const { backend, user } = openOrder(exampleAnswer(200, "getShopOrder", "refund-under-review"));
    const box = await screen.findByRole("textbox", { name: "Write to support about this order" });
    vi.spyOn(document, "visibilityState", "get").mockReturnValue("hidden");

    act(() => {
      document.dispatchEvent(new Event("visibilitychange"));
    });
    // Typing waits for the browser's task queue, so a reload that started has been sent.
    await user.type(box, "a");

    expect(backend.requestsTo(getShopOrderRoute)).toHaveLength(1);
    vi.restoreAllMocks();
  });

  it("changes nothing when the reload fails, and keeps the text in the message box", async () => {
    const { user, dependencies } = openOrder(
      exampleAnswer(200, "getShopOrder", "refund-under-review"),
      { kind: "ingress", status: 502 },
    );
    const box = await screen.findByRole("textbox", { name: "Write to support about this order" });
    await user.type(box, "Is the refund approved?");

    refocusWindow();

    await waitFor(() => {
      expect(
        dependencies.queryClient.getQueryState(["shop-orders", "order", "ORD-20931"])?.status,
      ).toBe("error");
    });
    expect(screen.getByRole("region", { name: "Order details" })).toHaveTextContent(
      "Refund under review",
    );
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(box).toHaveValue("Is the refund approved?");
  });
});

describe("OrderPage, failures", () => {
  it("shows the not-found state for an unknown order or another customer's (404)", async () => {
    openOrder(exampleAnswer(404, "problems", "not-found"));

    expect(
      await screen.findByRole("heading", { level: 1, name: "This order was not found" }),
    ).toBeVisible();
    expect(screen.getByText("It may not exist, or it belongs to another account.")).toBeVisible();
    expect(screen.getByRole("link", { name: "Back to My orders" })).toHaveAttribute(
      "href",
      "/shop/orders",
    );
  });

  it("shows the permission-denied state for another role (403)", async () => {
    openOrder(exampleAnswer(403, "problems", "forbidden-role"));

    expect(
      await screen.findByRole("heading", { level: 1, name: "The shop is for customer accounts" }),
    ).toBeVisible();
  });

  it("shows the error state for a lost connection", async () => {
    openOrder({ kind: "network_error" });

    expect(
      await screen.findByRole("heading", { level: 1, name: "This order could not be loaded" }),
    ).toBeVisible();
  });
});
