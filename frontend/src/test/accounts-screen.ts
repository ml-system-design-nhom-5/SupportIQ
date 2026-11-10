/**
 * The Accounts screen in tests: open it with fake answers, find a row, and confirm a change.
 */
import { screen, within } from "@testing-library/react";

import {
  changeAccountRoleRoute,
  changeAccountStatusRoute,
  getCurrentSessionRoute,
  listAdminAccountsRoute,
} from "@/test/backend-routes";
import { createFakeBackend, exampleAnswer, type FakeAnswer } from "@/test/fake-backend";
import { renderApp, testSettings } from "@/test/render-app";

/** The answers of the Accounts screen of a test. */
export type AccountAnswers = {
  readonly list?: readonly FakeAnswer[];
  readonly role?: readonly FakeAnswer[];
  readonly status?: readonly FakeAnswer[];
  readonly settings?: typeof testSettings;
  readonly path?: string;
};

/**
 * Open Accounts as the admin of the examples.
 *
 * @param answers - The answers of the list and of the changes.
 * @returns The rendered app.
 */
export function openAccounts(answers: AccountAnswers = {}) {
  const backend = createFakeBackend();
  backend.answer(getCurrentSessionRoute, exampleAnswer(200, "getCurrentSession", "admin"));
  backend.answer(
    listAdminAccountsRoute,
    ...(answers.list ?? [exampleAnswer(200, "listAdminAccounts", "first-page")]),
  );
  backend.answer(
    changeAccountRoleRoute,
    ...(answers.role ?? [exampleAnswer(201, "changeAccountRole", "made-manager")]),
  );
  backend.answer(
    changeAccountStatusRoute,
    ...(answers.status ?? [exampleAnswer(201, "changeAccountStatus", "deactivated")]),
  );
  return renderApp({
    path: answers.path ?? "/admin/accounts",
    backend,
    settings: answers.settings ?? testSettings,
  });
}

/**
 * Find the row of an account.
 *
 * @param name - The display name.
 * @returns The table row.
 */
export async function findRow(name: string): Promise<HTMLElement> {
  const header = await screen.findByRole("rowheader", { name: new RegExp(name) });
  const row = header.closest("tr");
  if (row === null) {
    throw new Error(`${name} has no table row.`);
  }
  return row;
}

/**
 * Choose an action of a row and confirm it.
 *
 * @param user - The user-event instance.
 * @param change - The account name and the label of the action.
 */
export async function chooseAndConfirm(
  user: ReturnType<typeof renderApp>["user"],
  change: { readonly name: string; readonly label: string },
) {
  const row = await findRow(change.name);
  await user.click(within(row).getByRole("button", { name: new RegExp(change.label) }));
  const dialog = await screen.findByRole("alertdialog");
  await user.click(within(dialog).getByRole("button", { name: change.label }));
}
