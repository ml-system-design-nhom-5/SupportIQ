import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { chooseAndConfirm, openAccounts } from "@/test/accounts-screen";
import {
  changeAccountRoleRoute,
  changeAccountStatusRoute,
  listAdminAccountsRoute,
} from "@/test/backend-routes";
import { exampleAnswer } from "@/test/fake-backend";
import { testSettings } from "@/test/render-app";

describe("AccountsPage, a change with an unknown outcome", () => {
  it.each([
    ["a lost connection", { kind: "network_error" } as const],
    ["a 502 from the ingress", { kind: "ingress", status: 502 } as const],
    ["a 504 from the ingress", { kind: "ingress", status: 504 } as const],
    ["a 201 with an empty body", { kind: "body", status: 201, body: {} } as const],
  ])("says that the change may have happened after %s", async (_case, answer) => {
    const { user, backend } = openAccounts({ role: [answer] });

    await chooseAndConfirm(user, { name: "Mai Nguyen", label: "Make manager" });

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Mai Nguyen may have been made a manager. We could not confirm it. The list is loading again. If the row does not change, it is safe to try again.",
    );
    await waitFor(() => {
      expect(backend.requestsTo(listAdminAccountsRoute)).toHaveLength(2);
    });
  });

  it("says that the change may have happened after a timeout", async () => {
    const { user, backend } = openAccounts({
      status: [{ kind: "no_answer" }],
      settings: { ...testSettings, requestTimeoutMs: 1 },
    });

    await chooseAndConfirm(user, { name: "Mai Nguyen", label: "Deactivate" });

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Mai Nguyen may have been deactivated.",
    );
    await waitFor(() => {
      expect(backend.requestsTo(listAdminAccountsRoute)).toHaveLength(2);
    });
  });

  it.each([
    ["503", exampleAnswer(503, "problems", "not-ready")],
    ["429", { kind: "ingress", status: 429 } as const],
    ["500", exampleAnswer(500, "problems", "internal-error")],
  ])("still says so when the retry after a lost connection gets a %s", async (_case, answer) => {
    const { user, backend } = openAccounts({
      role: [{ kind: "network_error" }, answer],
      settings: { ...testSettings, requestRetryMaxCount: 1 },
    });

    await chooseAndConfirm(user, { name: "Mai Nguyen", label: "Make manager" });

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Mai Nguyen may have been made a manager.",
    );
    await waitFor(() => {
      expect(backend.requestsTo(listAdminAccountsRoute)).toHaveLength(2);
    });
  });

  it("still says so when the admin confirms the same change again and it fails", async () => {
    const { user, backend } = openAccounts({
      role: [{ kind: "network_error" }, exampleAnswer(503, "problems", "not-ready")],
    });

    await chooseAndConfirm(user, { name: "Mai Nguyen", label: "Make manager" });
    await screen.findByRole("alert");
    await chooseAndConfirm(user, { name: "Mai Nguyen", label: "Make manager" });

    await waitFor(() => {
      expect(backend.requestsTo(changeAccountRoleRoute)).toHaveLength(2);
    });
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Mai Nguyen may have been made a manager.",
    );
  });

  it("reuses the key when the same change is confirmed again after a failure", async () => {
    const { user, backend } = openAccounts({
      role: [{ kind: "network_error" }, exampleAnswer(201, "changeAccountRole", "made-manager")],
    });

    await chooseAndConfirm(user, { name: "Mai Nguyen", label: "Make manager" });
    await screen.findByRole("alert");
    await chooseAndConfirm(user, { name: "Mai Nguyen", label: "Make manager" });

    await waitFor(() => {
      expect(backend.requestsTo(changeAccountRoleRoute)).toHaveLength(2);
    });
    const [first, second] = backend
      .requestsTo(changeAccountRoleRoute)
      .map((request) => request.headers.get("Idempotency-Key"));
    expect(second).toBe(first);
  });

  it("uses a new key for another change after a failure", async () => {
    const { user, backend } = openAccounts({
      role: [{ kind: "network_error" }],
    });

    await chooseAndConfirm(user, { name: "Mai Nguyen", label: "Make manager" });
    await screen.findByRole("alert");
    await chooseAndConfirm(user, { name: "Mai Nguyen", label: "Deactivate" });

    await waitFor(() => {
      expect(backend.requestsTo(changeAccountStatusRoute)).toHaveLength(1);
    });
    expect(
      backend.requestsTo(changeAccountStatusRoute)[0]?.headers.get("Idempotency-Key"),
    ).not.toBe(backend.requestsTo(changeAccountRoleRoute)[0]?.headers.get("Idempotency-Key"));
  });
});
