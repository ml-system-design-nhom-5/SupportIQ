import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { getCurrentSessionRoute, listConsoleTicketsRoute } from "@/test/backend-routes";
import { readExampleWith } from "@/test/contract-examples";
import { createFakeBackend, exampleAnswer } from "@/test/fake-backend";
import { renderApp } from "@/test/render-app";

describe("StartPage", () => {
  it.each([
    ["customer", "/shop"],
    ["staff", "/console"],
    ["manager", "/console"],
    ["admin", "/admin"],
  ])("opens the area of a %s session: %s", async (example, path) => {
    const backend = createFakeBackend();
    backend.answer(getCurrentSessionRoute, exampleAnswer(200, "getCurrentSession", example));
    backend.answer(listConsoleTicketsRoute, exampleAnswer(200, "listConsoleTickets", "open-queue"));

    const { router } = renderApp({ path: "/", backend });

    await waitFor(() => {
      expect(router.state.location.pathname).toBe(path);
    });
  });

  it("opens sign-in without a session", async () => {
    const backend = createFakeBackend();
    backend.answer(getCurrentSessionRoute, exampleAnswer(401, "problems", "unauthenticated"));

    const { router } = renderApp({ path: "/", backend });

    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/sign-in");
    });
  });

  it("says that a role this version does not know has no area (CON-22)", async () => {
    const backend = createFakeBackend();
    backend.answer(getCurrentSessionRoute, {
      kind: "body",
      status: 200,
      body: readExampleWith("getCurrentSession", "staff", { role: "auditor" }),
    });

    renderApp({ path: "/", backend });

    expect(
      await screen.findByRole("heading", {
        level: 1,
        name: "This account has no area in this version",
      }),
    ).toBeVisible();
    expect(screen.getByRole("button", { name: "Sign out" })).toBeEnabled();
  });
});
