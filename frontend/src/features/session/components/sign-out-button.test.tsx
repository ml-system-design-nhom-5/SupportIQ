import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { chooseFromAccountMenu } from "@/test/account-menu";
import { deleteCurrentSessionRoute, getCurrentSessionRoute } from "@/test/backend-routes";
import {
  createFakeBackend,
  exampleAnswer,
  type FakeAnswer,
  noContentAnswer,
} from "@/test/fake-backend";
import { renderApp, testSettings } from "@/test/render-app";

/**
 * Open the console as staff, with the given answer to sign-out, and choose Sign out in the account
 * menu. Automatic retries are on, so a test can show that sign-out does not use them.
 *
 * @param signOutAnswer - What `deleteCurrentSession` answers.
 * @returns The rendered app.
 */
async function openConsoleAndSignOut(signOutAnswer: FakeAnswer) {
  const backend = createFakeBackend();
  backend.answer(getCurrentSessionRoute, exampleAnswer(200, "getCurrentSession", "staff"));
  backend.answer(deleteCurrentSessionRoute, signOutAnswer);
  const rendered = renderApp({
    path: "/console",
    backend,
    settings: { ...testSettings, requestRetryMaxCount: 2 },
  });
  await chooseFromAccountMenu(rendered.user, "Sign out");
  return rendered;
}

describe("Sign out in the account menu", () => {
  it("signs out without an Idempotency-Key and opens sign-in without a return path", async () => {
    const { backend, router } = await openConsoleAndSignOut(noContentAnswer);

    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/sign-in");
    });
    expect(router.state.location.search).toBe("");
    expect(backend.requestsTo(deleteCurrentSessionRoute)[0]?.headers.has("Idempotency-Key")).toBe(
      false,
    );
  });

  it("removes every cached response of the account (switching accounts)", async () => {
    const { dependencies, router } = await openConsoleAndSignOut(noContentAnswer);

    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/sign-in");
    });
    const cachedKeys = dependencies.queryClient
      .getQueryCache()
      .getAll()
      .map((query) => query.queryKey);
    expect(cachedKeys).toEqual([["session", "current"]]);
    expect(dependencies.queryClient.getQueryData(["session", "current"])).toEqual({
      kind: "signed_out",
      reason: "signed_out_by_user",
    });
  });

  it("treats a 401 as signed out, because the session already ended (CON-13)", async () => {
    const { router } = await openConsoleAndSignOut(
      exampleAnswer(401, "problems", "unauthenticated"),
    );

    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/sign-in");
    });
    expect(router.state.location.search).toBe("");
  });

  it.each([
    ["a lost connection", { kind: "network_error" } as const],
    ["a 504 from the ingress", { kind: "ingress", status: 504 } as const],
  ])("does not claim that the person is still signed in after %s", async (_case, answer) => {
    const { router } = await openConsoleAndSignOut(answer);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "We could not confirm that you signed out. Try again.",
    );
    expect(router.state.location.pathname).toBe("/console");
  });

  it("says that the person is still signed in when sign-out fails, and never retries", async () => {
    const { backend, router } = await openConsoleAndSignOut(
      exampleAnswer(503, "problems", "not-ready"),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "You are still signed in. Try again.",
    );
    expect(router.state.location.pathname).toBe("/console");
    expect(backend.requestsTo(deleteCurrentSessionRoute)).toHaveLength(1);
    expect(screen.getByText(/Details: trace/)).toBeVisible();
  });
});
