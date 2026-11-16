import { screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { getConsoleTicketRoute, recordTicketViewRoute } from "@/test/backend-routes";
import { openConsole, TICKET_PATH, workspaceExample } from "@/test/console-screen";
import { exampleAnswer, holdAnswer, noContentAnswer } from "@/test/fake-backend";
import { testSettings } from "@/test/render-app";

/** A UUID in lowercase, as the contract requires of an `Idempotency-Key`. */
const idempotencyKeyPattern =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

afterEach(() => {
  vi.useRealTimers();
});

describe("Opening a ticket", () => {
  it("records the view with an Idempotency-Key, then loads the workspace (console UI design, Flow)", async () => {
    const view = holdAnswer({ kind: "no_content", status: 204 });
    const { backend } = openConsole(TICKET_PATH, { view: [view.answer] });

    await waitFor(() => {
      expect(backend.requestsTo(recordTicketViewRoute)).toHaveLength(1);
    });
    expect(backend.requestsTo(getConsoleTicketRoute)).toHaveLength(0);
    expect(screen.getByText("Loading the ticket…")).toBeInTheDocument();
    view.release();

    expect(await screen.findByRole("heading", { level: 1, name: "Ticket TCK-1042" })).toBeVisible();
    const [viewRequest] = backend.requestsTo(recordTicketViewRoute);
    expect(viewRequest?.path).toBe("/v1/console/tickets/TCK-1042/views");
    expect(viewRequest?.headers.get("Idempotency-Key")).toMatch(idempotencyKeyPattern);
  });

  it("retries a failed view with the same key, then loads the workspace", async () => {
    const { backend } = openConsole(TICKET_PATH, {
      view: [exampleAnswer(503, "problems", "not-ready"), noContentAnswer],
      settings: { ...testSettings, requestRetryMaxCount: 1 },
    });

    expect(await screen.findByRole("heading", { level: 1, name: "Ticket TCK-1042" })).toBeVisible();
    const keys = backend
      .requestsTo(recordTicketViewRoute)
      .map((request) => request.headers.get("Idempotency-Key"));
    expect(keys).toHaveLength(2);
    expect(new Set(keys).size).toBe(1);
  });

  it("loads the workspace after a view that failed, and says that the view was not recorded", async () => {
    openConsole(TICKET_PATH, { view: [exampleAnswer(503, "problems", "not-ready")] });

    expect(await screen.findByRole("heading", { level: 1, name: "Ticket TCK-1042" })).toBeVisible();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "The opening of this ticket was not recorded. You can keep working on this ticket.",
    );
  });

  it("says that a view without an answer may have been recorded, and offers no retry (ERR-07)", async () => {
    openConsole(TICKET_PATH, { view: [{ kind: "network_error" }] });

    expect(await screen.findByRole("heading", { level: 1, name: "Ticket TCK-1042" })).toBeVisible();
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent(
      "The opening of this ticket may have been recorded. We could not confirm it. You can keep working on this ticket.",
    );
    expect(alert).not.toHaveTextContent(/try again/i);
  });

  it("records the view again when another ticket opens", async () => {
    const { backend, router } = openConsole(TICKET_PATH);
    await screen.findByRole("heading", { level: 1, name: "Ticket TCK-1042" });

    await router.navigate("/console/tickets/TCK-1038");

    await waitFor(() => {
      expect(backend.requestsTo(recordTicketViewRoute).map((request) => request.path)).toEqual([
        "/v1/console/tickets/TCK-1042/views",
        "/v1/console/tickets/TCK-1038/views",
      ]);
    });
  });

  it("sends a new Idempotency-Key each time the same ticket opens again", async () => {
    const { backend, router } = openConsole(TICKET_PATH);
    await screen.findByRole("heading", { level: 1, name: "Ticket TCK-1042" });
    await router.navigate("/console");
    await screen.findByRole("heading", { level: 1, name: "Select a ticket" });

    await router.navigate(TICKET_PATH);

    await waitFor(() => {
      expect(backend.requestsTo(recordTicketViewRoute)).toHaveLength(2);
    });
    const [firstKey, secondKey] = backend
      .requestsTo(recordTicketViewRoute)
      .map((request) => request.headers.get("Idempotency-Key"));
    expect(firstKey).toMatch(idempotencyKeyPattern);
    expect(secondKey).toMatch(idempotencyKeyPattern);
    expect(secondKey).not.toBe(firstKey);
  });
});

describe("A ticket that could not load", () => {
  it("says what happened, with the trace ID, and tries again (UI-25)", async () => {
    const { user } = openConsole(TICKET_PATH, {
      workspace: [
        exampleAnswer(500, "problems", "internal-error"),
        workspaceExample("draft-ready"),
      ],
    });

    expect(
      await screen.findByRole("heading", { level: 1, name: "This ticket could not be loaded" }),
    ).toBeVisible();
    expect(screen.getByText(/Details: trace/)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByRole("heading", { level: 1, name: "Ticket TCK-1042" })).toBeVisible();
  });

  it.each([
    [404, "not-found"],
    [403, "forbidden-role"],
  ])("shows a %i as the permission-denied state, with the trace ID", async (status, problem) => {
    openConsole(TICKET_PATH, { workspace: [exampleAnswer(status, "problems", problem)] });

    expect(
      await screen.findByRole("heading", { level: 1, name: "You cannot open this page" }),
    ).toBeVisible();
    expect(
      screen.getByText("Your role does not allow it. Ask a manager if you need it."),
    ).toBeVisible();
    expect(screen.getByText(/Details: trace/)).toBeVisible();
    expect(screen.queryByRole("button", { name: "Try again" })).not.toBeInTheDocument();
  });

  it("goes to sign-in when the session ended (401)", async () => {
    const { router } = openConsole(TICKET_PATH, {
      workspace: [exampleAnswer(401, "problems", "unauthenticated")],
    });

    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/sign-in");
    });
  });
});
