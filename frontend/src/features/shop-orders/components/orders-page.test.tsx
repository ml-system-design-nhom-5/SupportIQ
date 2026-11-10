import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { getCurrentSessionRoute, listShopOrdersRoute } from "@/test/backend-routes";
import {
  countExampleItems,
  MAX_PAGE_LIMIT,
  readExampleItemPageWith,
  readFullPageOfExampleItem,
} from "@/test/contract-examples";
import { createFakeBackend, exampleAnswer, type FakeAnswer } from "@/test/fake-backend";
import { renderApp } from "@/test/render-app";

/**
 * Open My orders as a customer, with the given answers to `listShopOrders`.
 *
 * @param answers - The answers of the order list, in order.
 * @returns The rendered app.
 */
function openOrders(...answers: FakeAnswer[]) {
  const backend = createFakeBackend();
  backend.answer(getCurrentSessionRoute, exampleAnswer(200, "getCurrentSession", "customer"));
  backend.answer(listShopOrdersRoute, ...answers);
  return renderApp({ path: "/shop/orders", backend });
}

/**
 * Wait for the order rows and read their links.
 *
 * @returns The links of the rows, in order.
 */
function findOrderLinks(): Promise<HTMLElement[]> {
  return waitFor(() =>
    within(screen.getByRole("list", { name: "Your orders" })).getAllByRole("link"),
  );
}

describe("OrdersPage", () => {
  it("shows the error state with Try again when a success body has the wrong shape", async () => {
    openOrders({ kind: "body", status: 200, body: {} });

    expect(
      await screen.findByRole("heading", { name: "Your orders could not be loaded" }),
    ).toBeVisible();
    expect(screen.getByRole("button", { name: "Try again" })).toBeEnabled();
  });

  it("shows the largest page and the page after it without a duplicate or a lost order", async () => {
    const fullPage = readFullPageOfExampleItem(
      { folder: "listShopOrders", name: "first-page", index: 0 },
      "order_id",
    );
    const { user } = openOrders(
      { kind: "body", status: 200, body: fullPage },
      exampleAnswer(200, "listShopOrders", "last-page"),
    );
    expect(await findOrderLinks()).toHaveLength(MAX_PAGE_LIMIT);

    await user.click(screen.getByRole("button", { name: "Show more orders" }));

    await waitFor(async () => {
      expect(await findOrderLinks()).toHaveLength(
        MAX_PAGE_LIMIT + countExampleItems("listShopOrders", "last-page"),
      );
    });
    const hrefs = (await findOrderLinks()).map((link) => link.getAttribute("href"));
    expect(new Set(hrefs).size).toBe(hrefs.length);
  });

  it("shows a loading state until the first page arrives (UI-24)", async () => {
    openOrders({ kind: "no_answer" });

    expect(await screen.findByText("Loading your orders…")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "My orders" })).toBeVisible();
  });

  it("shows each order with its ID, date, products, statuses, and total, newest first", async () => {
    openOrders(exampleAnswer(200, "listShopOrders", "first-page"));

    const [first, second] = await findOrderLinks();

    expect(first).toHaveAttribute("href", "/shop/orders/ORD-20990");
    expect(first).toHaveTextContent("Order ORD-20990");
    expect(first).toHaveTextContent("Placed 28 Oct 2026");
    expect(first).toHaveTextContent("Desk lamp, Notebook set × 2");
    expect(first).toHaveTextContent("OrderShipped");
    expect(first).toHaveTextContent("ShipmentIn transit");
    expect(first).toHaveTextContent("$42.50");
    expect(second).toHaveTextContent("Order ORD-20955");
  });

  it("shows the refund status of an order with a refund", async () => {
    openOrders(exampleAnswer(200, "listShopOrders", "last-page"));

    const [withRefund, withoutRefund] = await findOrderLinks();

    expect(withRefund).toHaveTextContent("Refund under review");
    expect(withoutRefund).not.toHaveTextContent("Refund");
  });

  it("follows next_cursor with Show more orders, without duplicates, and stops (CON-14)", async () => {
    const { user, backend } = openOrders(
      exampleAnswer(200, "listShopOrders", "first-page"),
      exampleAnswer(200, "listShopOrders", "last-page"),
    );
    await findOrderLinks();

    await user.click(screen.getByRole("button", { name: "Show more orders" }));

    await waitFor(async () => {
      expect(await findOrderLinks()).toHaveLength(4);
    });
    expect(
      backend.requestsTo(listShopOrdersRoute).map((request) => request.searchParams.get("cursor")),
    ).toEqual([null, "eyJvIjoyfQ"]);
    expect(screen.queryByRole("button", { name: "Show more orders" })).not.toBeInTheDocument();
  });

  it("says that there is no order yet", async () => {
    openOrders(exampleAnswer(200, "listShopOrders", "empty"));

    expect(
      await screen.findByRole("heading", { level: 2, name: "You have no orders yet." }),
    ).toBeVisible();
  });

  it("shows a safe label for a status that this version does not know (CON-22)", async () => {
    openOrders({
      kind: "body",
      status: 200,
      body: readExampleItemPageWith(
        { folder: "listShopOrders", name: "last-page", index: 1 },
        { order_status: "on_hold" },
      ),
    });

    const [row] = await findOrderLinks();

    expect(row).toHaveTextContent("OrderStatus unknown");
  });
});

describe("OrdersPage, failures", () => {
  it("shows the permission-denied state for another role (403)", async () => {
    openOrders(exampleAnswer(403, "problems", "forbidden-role"));

    expect(
      await screen.findByRole("heading", { level: 1, name: "The shop is for customer accounts" }),
    ).toBeVisible();
  });

  it("shows the error state with the trace ID and loads again with Try again", async () => {
    const { user } = openOrders(
      exampleAnswer(500, "problems", "internal-error"),
      exampleAnswer(200, "listShopOrders", "last-page"),
    );

    expect(
      await screen.findByRole("heading", { level: 1, name: "Your orders could not be loaded" }),
    ).toBeVisible();
    expect(screen.getByText("319c0af7651916cd43dd8448eb211c80")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Try again" }));

    expect(await findOrderLinks()).toHaveLength(2);
  });

  it("shows the trace ID when backend answers the next page with a problem (UI-25)", async () => {
    const { user } = openOrders(
      exampleAnswer(200, "listShopOrders", "first-page"),
      exampleAnswer(503, "problems", "not-ready"),
    );
    await findOrderLinks();

    await user.click(screen.getByRole("button", { name: "Show more orders" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Details: trace");
  });

  it("keeps the orders shown when the next page fails", async () => {
    const { user } = openOrders(exampleAnswer(200, "listShopOrders", "first-page"), {
      kind: "ingress",
      status: 504,
    });
    await findOrderLinks();

    await user.click(screen.getByRole("button", { name: "Show more orders" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("More orders could not be loaded.");
    expect(await findOrderLinks()).toHaveLength(2);
    expect(screen.getByRole("button", { name: "Show more orders" })).toBeEnabled();
  });
});
