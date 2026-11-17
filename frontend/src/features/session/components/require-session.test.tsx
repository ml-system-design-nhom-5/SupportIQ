import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { getCurrentSessionRoute, listConsoleTicketsRoute } from "@/test/backend-routes";
import { createFakeBackend, exampleAnswer } from "@/test/fake-backend";
import { renderApp } from "@/test/render-app";

describe("RequireSession", () => {
  it("shows a loading state while the session is checked (UI-24)", () => {
    const backend = createFakeBackend();
    backend.answer(getCurrentSessionRoute, { kind: "no_answer" });

    renderApp({ path: "/console", backend });

    expect(screen.getByRole("status")).toHaveTextContent("Checking your session…");
  });

  it("opens sign-in with a return path when there is no valid session", async () => {
    const backend = createFakeBackend();
    backend.answer(getCurrentSessionRoute, exampleAnswer(401, "problems", "unauthenticated"));
    const { router } = renderApp({ path: "/console?view=inbox#top", backend });

    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/sign-in");
    });
    expect(new URLSearchParams(router.state.location.search).get("returnTo")).toBe(
      "/console?view=inbox#top",
    );
    expect(backend.requestsTo(getCurrentSessionRoute)).toHaveLength(1);
  });

  it("shows an error with Try again when the session cannot be checked", async () => {
    const backend = createFakeBackend();
    backend.answer(
      getCurrentSessionRoute,
      { kind: "network_error" },
      exampleAnswer(200, "getCurrentSession", "staff"),
    );
    backend.answer(listConsoleTicketsRoute, exampleAnswer(200, "listConsoleTickets", "open-queue"));
    const { user } = renderApp({ path: "/console", backend });

    expect(
      await screen.findByRole("heading", { level: 1, name: "Your session could not be checked" }),
    ).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByText("Mai Nguyen")).toBeVisible();
  });
});
