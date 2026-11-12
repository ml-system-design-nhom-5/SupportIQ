import { screen } from "@testing-library/react";
import { describe, it } from "vitest";

import { changeOwnPasswordRoute, getCurrentSessionRoute } from "@/test/backend-routes";
import { createFakeBackend, exampleAnswer } from "@/test/fake-backend";
import { expectNotCached } from "@/test/query-caches";
import { renderApp } from "@/test/render-app";

/** Visibly fake passwords of the test. */
const CURRENT_PASSWORD = "not-the-old-password";
const NEW_PASSWORD = "not-the-new-password";

describe("ChangePasswordPage, the passwords (account management design, Shared behavior)", () => {
  it("keeps no password in the query or mutation cache after the change", async () => {
    const backend = createFakeBackend();
    backend.answer(getCurrentSessionRoute, exampleAnswer(200, "getCurrentSession", "customer"));
    backend.answer(changeOwnPasswordRoute, exampleAnswer(201, "changeOwnPassword", "changed"));
    const { user, dependencies } = renderApp({ path: "/change-password", backend });
    await user.type(await screen.findByLabelText("Current password"), CURRENT_PASSWORD);
    await user.type(screen.getByLabelText("New password"), NEW_PASSWORD);
    await user.type(screen.getByLabelText("Confirm new password"), NEW_PASSWORD);

    await user.click(screen.getByRole("button", { name: "Change password" }));

    await screen.findByText("Your password was changed.");
    expectNotCached(dependencies.queryClient, CURRENT_PASSWORD);
    expectNotCached(dependencies.queryClient, NEW_PASSWORD);
  });
});
