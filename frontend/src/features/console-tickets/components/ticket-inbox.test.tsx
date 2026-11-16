import { screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { INBOX_POLLING_INTERVAL_MS } from "@/features/console-tickets/model/polling";
import { listConsoleTicketsRoute } from "@/test/backend-routes";
import { openConsole } from "@/test/console-screen";
import { exampleAnswer } from "@/test/fake-backend";

/**
 * Find the inbox, once the session is known.
 *
 * @returns The inbox landmark.
 */
function findInbox(): Promise<HTMLElement> {
  return screen.findByRole("navigation", { name: "Inbox" });
}

describe("The inbox", () => {
  it("lists the open queue oldest first, each ticket with its facts (console UI design, Inbox)", async () => {
    openConsole("/console");

    const list = await screen.findByRole("list", { name: "Open tickets" });
    const links = within(list).getAllByRole("link");
    expect(links.map((link) => link.getAttribute("href"))).toEqual([
      "/console/tickets/TCK-1038",
      "/console/tickets/TCK-1042",
    ]);
    expect(links[0]).toHaveTextContent("No analysisAI unavailableOpened");
    expect(links[1]).toHaveTextContent("Refund statusConfidence High · 88%Draft ready");
    expect(within(await findInbox()).getByText("Oldest first")).toBeVisible();
  });

  it("marks the open ticket in the inbox", async () => {
    openConsole("/console/tickets/TCK-1042");

    expect(await within(await findInbox()).findByRole("link", { current: "page" })).toHaveAttribute(
      "href",
      "/console/tickets/TCK-1042",
    );
  });

  it("offers staff the Open queue only", async () => {
    const { user } = openConsole("/console");

    await user.click(await screen.findByRole("button", { name: "Ticket status: Open" }));

    expect((await screen.findAllByRole("menuitemradio")).map((item) => item.textContent)).toEqual([
      "Open",
    ]);
  });

  it("lets a manager choose another queue, which the address keeps", async () => {
    const { user, backend, router } = openConsole("/console", {
      session: "manager",
      queue: [
        exampleAnswer(200, "listConsoleTickets", "open-queue"),
        exampleAnswer(200, "listConsoleTickets", "closed"),
      ],
    });

    await user.click(await screen.findByRole("button", { name: "Ticket status: Open" }));
    await user.click(await screen.findByRole("menuitemradio", { name: "Closed" }));

    expect(await screen.findByRole("list", { name: "Closed tickets" })).toBeVisible();
    expect(router.state.location.search).toBe("?status=closed");
    expect(backend.requestsTo(listConsoleTicketsRoute).at(-1)?.searchParams.get("status")).toBe(
      "closed",
    );
    expect(within(await findInbox()).getByText("Newest first")).toBeVisible();
    expect(screen.getByRole("link", { name: /TCK-1017/ })).toHaveAttribute(
      "href",
      "/console/tickets/TCK-1017?status=closed",
    );
  });

  it("shows the empty queue in the inbox and next to it", async () => {
    openConsole("/console", { queue: [exampleAnswer(200, "listConsoleTickets", "empty")] });

    expect(await within(await findInbox()).findByText("No open tickets")).toBeVisible();
    expect(screen.getByRole("heading", { level: 1, name: "No open tickets" })).toBeVisible();
  });

  it("asks to select a ticket while the queue has tickets", async () => {
    openConsole("/console");

    expect(await screen.findByRole("heading", { level: 1, name: "Select a ticket" })).toBeVisible();
    expect(screen.getByText("Tickets wait in the inbox, oldest first.")).toBeVisible();
  });

  it("shows skeletons while the queue loads (UI-24)", async () => {
    openConsole("/console", { queue: [{ kind: "no_answer" }] });

    expect(await within(await findInbox()).findByRole("status")).toHaveTextContent(
      "Loading the tickets…",
    );
  });

  it("says that the queue could not load, with the trace ID, and tries again", async () => {
    const { user } = openConsole("/console", {
      queue: [
        exampleAnswer(500, "problems", "internal-error"),
        exampleAnswer(200, "listConsoleTickets", "open-queue"),
      ],
    });

    expect(
      await screen.findByRole("heading", { name: "The inbox could not be loaded" }),
    ).toBeVisible();
    const inbox = await findInbox();
    expect(within(inbox).getByText(/Details: trace/)).toBeVisible();
    await user.click(within(inbox).getByRole("button", { name: "Try again" }));

    expect(await screen.findByRole("list", { name: "Open tickets" })).toBeVisible();
  });

  it("loads the next page of the queue with its cursor (CON-14)", async () => {
    const { user, backend } = openConsole("/console", {
      queue: [
        exampleAnswer(200, "listConsoleTickets", "open-queue"),
        exampleAnswer(200, "listConsoleTickets", "empty"),
      ],
    });

    await user.click(await screen.findByRole("button", { name: "Show more tickets" }));

    await waitFor(() => {
      expect(backend.requestsTo(listConsoleTicketsRoute).at(-1)?.searchParams.get("cursor")).toBe(
        "eyJ0IjoiMTA0MiJ9",
      );
    });
  });

  it("shows the permission-denied state to an account without the console (UI-40)", async () => {
    openConsole("/console", {
      session: "customer",
      queue: [exampleAnswer(403, "problems", "forbidden-role")],
    });

    expect(
      await screen.findByRole("heading", { level: 1, name: "The console is for support accounts" }),
    ).toBeVisible();
    expect(screen.queryByRole("navigation", { name: "Inbox" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign out" })).toBeVisible();
  });
});

describe("The inbox while it is open", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("loads the queue again on its own, so new tickets appear without a click", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    openConsole("/console", {
      queue: [
        exampleAnswer(200, "listConsoleTickets", "empty"),
        exampleAnswer(200, "listConsoleTickets", "open-queue"),
      ],
    });
    expect(await within(await findInbox()).findByText("No open tickets")).toBeVisible();

    await vi.advanceTimersByTimeAsync(INBOX_POLLING_INTERVAL_MS);

    const list = await screen.findByRole("list", { name: "Open tickets" });
    expect(within(list).getAllByRole("link")).toHaveLength(2);
  });

  it("keeps the tickets on screen when a reload fails, and says so", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    openConsole("/console", {
      queue: [
        exampleAnswer(200, "listConsoleTickets", "open-queue"),
        exampleAnswer(500, "problems", "internal-error"),
      ],
    });
    const inbox = await findInbox();
    await within(inbox).findByRole("list", { name: "Open tickets" });

    await vi.advanceTimersByTimeAsync(INBOX_POLLING_INTERVAL_MS);

    expect(await within(inbox).findByRole("alert")).toHaveTextContent(
      "The inbox could not be updated.",
    );
    expect(within(inbox).getAllByRole("link")).toHaveLength(2);
  });

  it("stops asking for a queue that could not load until staff try again", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const { backend } = openConsole("/console", {
      queue: [exampleAnswer(500, "problems", "internal-error")],
    });
    expect(
      await screen.findByRole("heading", { name: "The inbox could not be loaded" }),
    ).toBeVisible();

    await vi.advanceTimersByTimeAsync(INBOX_POLLING_INTERVAL_MS * 2);

    expect(backend.requestsTo(listConsoleTicketsRoute)).toHaveLength(1);
  });

  it("stops asking for the queue after a 403", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const { backend } = openConsole("/console", {
      session: "customer",
      queue: [exampleAnswer(403, "problems", "forbidden-role")],
    });
    await screen.findByRole("heading", { level: 1, name: "The console is for support accounts" });

    await vi.advanceTimersByTimeAsync(INBOX_POLLING_INTERVAL_MS * 2);

    expect(backend.requestsTo(listConsoleTicketsRoute)).toHaveLength(1);
  });
});
