import { act, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { listShopTicketsRoute } from "@/test/backend-routes";
import { readExampleItemPageWith } from "@/test/contract-examples";
import { exampleAnswer } from "@/test/fake-backend";
import { BOX_NAME, openOrderSupport } from "@/test/order-support-screen";

describe("OrderSupportSection, tickets", () => {
  it("lists the order's tickets oldest first, with the reply or the no-reply line", async () => {
    const { backend } = openOrderSupport();

    const list = await screen.findByRole("list", { name: "Tickets about this order" });
    const items = within(list).getAllByRole("listitem");

    expect(items.map((item) => item.id)).toEqual(["ticket-TCK-1017", "ticket-TCK-1042"]);
    expect(items[0]).toHaveTextContent("Replied");
    expect(items[0]).toHaveTextContent("Reply from support");
    expect(items[1]).toHaveTextContent("Received");
    expect(items[1]).toHaveTextContent(
      "No reply yet. A person from our support team replies here.",
    );
    expect(backend.requestsTo(listShopTicketsRoute)[0]?.searchParams.get("order_id")).toBe(
      "ORD-20931",
    );
  });

  it("shows only the message box when the order has no ticket", async () => {
    openOrderSupport({ tickets: [exampleAnswer(200, "listShopTickets", "empty")] });

    expect(await screen.findByRole("textbox", { name: BOX_NAME })).toBeVisible();
    await waitFor(() => {
      expect(screen.queryByText("Loading your tickets…")).not.toBeInTheDocument();
    });
    expect(
      screen.queryByRole("list", { name: "Tickets about this order" }),
    ).not.toBeInTheDocument();
  });

  it("loads earlier tickets with Show earlier tickets and keeps them oldest first", async () => {
    const { user } = openOrderSupport({
      tickets: [
        exampleAnswer(200, "listShopTickets", "first-page"),
        exampleAnswer(200, "listShopTickets", "last-page"),
      ],
    });
    await screen.findByRole("list", { name: "Tickets about this order" });

    await user.click(screen.getByRole("button", { name: "Show earlier tickets" }));

    await waitFor(() => {
      const list = screen.getByRole("list", { name: "Tickets about this order" });
      expect(
        within(list)
          .getAllByRole("listitem")
          .map((item) => item.id),
      ).toEqual(["ticket-TCK-1017", "ticket-TCK-1038", "ticket-TCK-1042"]);
    });
    expect(screen.queryByRole("button", { name: "Show earlier tickets" })).not.toBeInTheDocument();
  });

  it("shows the tickets error with Try again while the message box keeps working", async () => {
    openOrderSupport({ tickets: [exampleAnswer(503, "problems", "not-ready")] });

    expect(
      await screen.findByRole("heading", { level: 2, name: "Your tickets could not be loaded" }),
    ).toBeVisible();
    expect(screen.getByRole("textbox", { name: BOX_NAME })).toBeEnabled();
  });

  it("renders HTML in a message as text (SEC-22)", async () => {
    openOrderSupport({
      tickets: [
        {
          kind: "body",
          status: 200,
          body: readExampleItemPageWith(
            { folder: "listShopTickets", name: "last-page", index: 0 },
            { message: "<img src=x onerror=alert(1)>" },
          ),
        },
      ],
    });

    expect(await screen.findByText("<img src=x onerror=alert(1)>")).toBeVisible();
  });
});

describe("OrderSupportSection, earlier tickets", () => {
  it("loads them when the click on the button is what returns focus to the window", async () => {
    const { user, backend } = openOrderSupport({
      tickets: [
        exampleAnswer(200, "listShopTickets", "first-page"),
        { kind: "no_answer" },
        exampleAnswer(200, "listShopTickets", "last-page"),
      ],
    });
    const showEarlier = await screen.findByRole("button", { name: "Show earlier tickets" });

    act(() => {
      window.dispatchEvent(new Event("focus"));
    });
    await waitFor(() => {
      expect(backend.requestsTo(listShopTicketsRoute)).toHaveLength(2);
    });
    await user.click(showEarlier);

    await waitFor(() => {
      expect(backend.requestsTo(listShopTicketsRoute).at(-1)?.searchParams.has("cursor")).toBe(
        true,
      );
    });
    expect(backend.requestsTo(listShopTicketsRoute)).toHaveLength(3);
  });

  it("shows the failure with its trace ID and keeps the tickets", async () => {
    const { user } = openOrderSupport({
      tickets: [
        exampleAnswer(200, "listShopTickets", "first-page"),
        exampleAnswer(503, "problems", "not-ready"),
      ],
    });

    await user.click(await screen.findByRole("button", { name: "Show earlier tickets" }));

    const banner = await screen.findByRole("alert");
    expect(banner).toHaveTextContent("Earlier tickets could not be loaded.");
    expect(banner).toHaveTextContent("Details: trace");
    expect(screen.getByRole("list", { name: "Tickets about this order" })).toBeVisible();
  });
});

describe("OrderSupportSection, a ticket list of the wrong shape", () => {
  it.each([
    ["no member", { items: [{}] }],
    [
      "a reply without members",
      readExampleItemPageWith(
        { folder: "listShopTickets", name: "last-page", index: 0 },
        { reply: {} },
      ),
    ],
  ])(
    "shows the tickets error for a ticket with %s, and the box keeps its text",
    async (_case, body) => {
      const { user } = openOrderSupport({ tickets: [{ kind: "body", status: 200, body }] });
      await user.type(await screen.findByRole("textbox", { name: BOX_NAME }), "Still here");

      expect(
        await screen.findByRole("heading", { level: 2, name: "Your tickets could not be loaded" }),
      ).toBeVisible();
      expect(screen.getByRole("textbox", { name: BOX_NAME })).toHaveValue("Still here");
    },
  );
});

describe("OrderSupportSection, another order", () => {
  it("starts with an empty box on a cached order, so the text never goes to it", async () => {
    const { user, router } = openOrderSupport();
    await screen.findByRole("textbox", { name: BOX_NAME });
    await act(() => router.navigate("/shop/orders/ORD-20990"));
    await screen.findByRole("textbox", { name: BOX_NAME });
    await act(() => router.navigate("/shop/orders/ORD-20931"));
    await user.type(await screen.findByRole("textbox", { name: BOX_NAME }), "About this order");

    await act(() => router.navigate("/shop/orders/ORD-20990"));

    expect(screen.getByRole("textbox", { name: BOX_NAME })).toHaveValue("");
  });
});
