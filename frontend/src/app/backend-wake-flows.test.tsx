import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  checkLivenessRoute,
  createSessionRoute,
  getCurrentSessionRoute,
  listShopProductsRoute,
} from "@/test/backend-routes";
import {
  createFakeBackend,
  exampleAnswer,
  type FakeAnswer,
  noContentAnswer,
} from "@/test/fake-backend";
import { renderApp, testSettings } from "@/test/render-app";

/** Settings with a wake origin, so the app sends wake requests (backend wake-up design). */
const wakeSettings = { ...testSettings, backendWakeOrigin: "https://backend.example.test" };

/**
 * Open sign-in with a wake origin, and send the credentials.
 *
 * @param signInAnswer - The answer of `createSession`.
 * @returns The fake backend.
 */
async function signInWith(signInAnswer: FakeAnswer) {
  const backend = createFakeBackend();
  backend.answer(checkLivenessRoute, noContentAnswer);
  backend.answer(createSessionRoute, signInAnswer);
  const { user } = renderApp({ path: "/sign-in", backend, settings: wakeSettings });
  await user.type(screen.getByRole("textbox", { name: "Login name" }), "customer-1");
  await user.type(screen.getByLabelText("Password"), "not-a-real-password");
  await user.click(screen.getByRole("button", { name: "Sign in" }));
  await waitFor(() => {
    expect(backend.requestsTo(createSessionRoute)).toHaveLength(1);
  });
  return backend;
}

describe("The wake request when the app starts (backend wake-up design, rule 4)", () => {
  it("is sent once", async () => {
    const backend = createFakeBackend();
    backend.answer(checkLivenessRoute, noContentAnswer);
    const { user } = renderApp({ path: "/sign-in", backend, settings: wakeSettings });

    // Typing waits for the browser's task queue, so a request that the app started has been sent.
    await user.type(screen.getByRole("textbox", { name: "Login name" }), "c");

    expect(backend.requestsTo(checkLivenessRoute)).toHaveLength(1);
  });

  it("is not sent without a wake origin (rule 9)", async () => {
    const backend = createFakeBackend();
    const { user } = renderApp({ path: "/sign-in", backend });

    await user.type(screen.getByRole("textbox", { name: "Login name" }), "c");

    expect(backend.requests).toHaveLength(0);
  });
});

describe("The wake request after a failure (backend wake-up design, rule 4)", () => {
  it("is sent again after a query fails with 502", async () => {
    const backend = createFakeBackend();
    backend.answer(checkLivenessRoute, noContentAnswer);
    backend.answer(getCurrentSessionRoute, exampleAnswer(200, "getCurrentSession", "customer"));
    backend.answer(listShopProductsRoute, { kind: "ingress", status: 502 });

    renderApp({ path: "/shop", backend, settings: wakeSettings });

    await waitFor(() => {
      expect(backend.requestsTo(checkLivenessRoute)).toHaveLength(2);
    });
  });

  it("is sent again after sign-in fails with 502, and sign-in is not sent again (rule 7)", async () => {
    const backend = await signInWith({ kind: "ingress", status: 502 });

    await waitFor(() => {
      expect(backend.requestsTo(checkLivenessRoute)).toHaveLength(2);
    });
    expect(backend.requestsTo(createSessionRoute)).toHaveLength(1);
  });

  it.each([
    [401, "invalid-credentials"],
    [422, "invalid-request"],
    [500, "internal-error"],
  ])("is not sent after a failure with %i", async (status, problem) => {
    const backend = await signInWith(exampleAnswer(status, "problems", problem));

    await screen.findByRole("alert");
    expect(backend.requestsTo(checkLivenessRoute)).toHaveLength(1);
  });
});
