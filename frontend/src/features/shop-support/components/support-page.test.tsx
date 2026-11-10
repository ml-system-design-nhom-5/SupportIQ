import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  getCurrentSessionRoute,
  getShopOrderRoute,
  listShopTicketsRoute,
} from "@/test/backend-routes";
import {
  countExampleItems,
  MAX_PAGE_LIMIT,
  readFullPageOfExampleItem,
} from "@/test/contract-examples";
import { createFakeBackend, exampleAnswer, type FakeAnswer } from "@/test/fake-backend";
import { renderApp } from "@/test/render-app";

/**
 * Open Support as a customer, with the given answers to `listShopTickets`.
 *
 * @param answers - The answers of the ticket list, in order.
 * @returns The rendered app.
 */
function openSupport(...answers: FakeAnswer[]) {
  const backend = createFakeBackend();
  backend.answer(getCurrentSessionRoute, exampleAnswer(200, "getCurrentSession", "customer"));
  backend.answer(getShopOrderRoute, exampleAnswer(200, "getShopOrder", "refund-under-review"));
  backend.answer(listShopTicketsRoute, ...answers);
  return renderApp({ path: "/shop/support", backend });
}

/**
 * Wait for the ticket rows and read their links.
 *
 * @returns The links of the rows, in order.
 */
function findTicketLinks(): Promise<HTMLElement[]> {
  return waitFor(() =>
    within(screen.getByRole("list", { name: "Your messages to support" })).getAllByRole("link"),
  );
}

describe("SupportPage", () => {
  it("shows the largest page and the page after it without a duplicate or a lost ticket", async () => {
    const fullPage = readFullPageOfExampleItem(
      { folder: "listShopTickets", name: "first-page", index: 0 },
      "ticket_id",
    );
    const { user } = openSupport(
      { kind: "body", status: 200, body: fullPage },
      exampleAnswer(200, "listShopTickets", "last-page"),
    );
    expect(await findTicketLinks()).toHaveLength(MAX_PAGE_LIMIT);

    await user.click(screen.getByRole("button", { name: "Show more messages" }));

    await waitFor(async () => {
      expect(await findTicketLinks()).toHaveLength(
        MAX_PAGE_LIMIT + countExampleItems("listShopTickets", "last-page"),
      );
    });
    const hrefs = (await findTicketLinks()).map((link) => link.getAttribute("href"));
    expect(new Set(hrefs).size).toBe(hrefs.length);
  });

  it("shows a loading state until the first page arrives (UI-24)", async () => {
    openSupport({ kind: "no_answer" });

    expect(await screen.findByText("Loading your messages…")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "Support" })).toBeVisible();
  });

  it("shows every ticket with its excerpt, IDs, time, and status, and asks for no order", async () => {
    const { backend } = openSupport(exampleAnswer(200, "listShopTickets", "last-page"));

    const [newest, oldest] = await findTicketLinks();

    expect(newest).toHaveTextContent("I asked for a refund for the headphones");
    expect(newest).toHaveTextContent("TCK-1042 · Order ORD-20931 · 47 minutes ago");
    expect(newest).toHaveTextContent("Received");
    expect(oldest).toHaveTextContent("Replied");
    expect(backend.requestsTo(listShopTicketsRoute)[0]?.searchParams.has("order_id")).toBe(false);
  });

  it("opens the order page at that ticket", async () => {
    const { user, router } = openSupport(exampleAnswer(200, "listShopTickets", "last-page"));
    await findTicketLinks();

    await user.click(screen.getByRole("link", { name: /TCK-1042/ }));

    await waitFor(() => {
      expect(document.activeElement).toHaveAttribute("id", "ticket-TCK-1042");
    });
    expect(router.state.location.pathname).toBe("/shop/orders/ORD-20931");
    expect(router.state.location.hash).toBe("#ticket-TCK-1042");
  });

  it("follows next_cursor with Show more messages and stops (CON-14)", async () => {
    const { user, backend } = openSupport(
      exampleAnswer(200, "listShopTickets", "first-page"),
      exampleAnswer(200, "listShopTickets", "last-page"),
    );
    await findTicketLinks();

    await user.click(screen.getByRole("button", { name: "Show more messages" }));

    await waitFor(async () => {
      expect(await findTicketLinks()).toHaveLength(3);
    });
    expect(
      backend.requestsTo(listShopTicketsRoute).map((request) => request.searchParams.get("cursor")),
    ).toEqual([null, "eyJ0IjoiMTAzOCJ9"]);
    expect(screen.queryByRole("button", { name: "Show more messages" })).not.toBeInTheDocument();
  });

  it("says that the customer has not written yet", async () => {
    openSupport(exampleAnswer(200, "listShopTickets", "empty"));

    expect(
      await screen.findByRole("heading", {
        level: 2,
        name: "You have not written to support yet.",
      }),
    ).toBeVisible();
  });
});

describe("SupportPage, failures", () => {
  it("shows the permission-denied state for another role (403)", async () => {
    openSupport(exampleAnswer(403, "problems", "forbidden-role"));

    expect(
      await screen.findByRole("heading", { level: 1, name: "The shop is for customer accounts" }),
    ).toBeVisible();
  });

  it("shows the error state and loads again with Try again", async () => {
    const { user } = openSupport(
      { kind: "ingress", status: 502 },
      exampleAnswer(200, "listShopTickets", "last-page"),
    );

    expect(
      await screen.findByRole("heading", { level: 1, name: "Your messages could not be loaded" }),
    ).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Try again" }));

    expect(await findTicketLinks()).toHaveLength(2);
  });

  it("keeps the tickets shown when the next page fails", async () => {
    const { user } = openSupport(exampleAnswer(200, "listShopTickets", "first-page"), {
      kind: "network_error",
    });
    await findTicketLinks();

    await user.click(screen.getByRole("button", { name: "Show more messages" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "More messages could not be loaded.",
    );
    expect(await findTicketLinks()).toHaveLength(2);
  });
});
