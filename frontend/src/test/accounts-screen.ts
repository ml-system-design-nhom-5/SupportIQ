/**
 * The Accounts screen in tests: open it with fake answers, find a row, confirm a change, and open
 * the create and reset dialogs.
 */
import { screen, within } from "@testing-library/react";

import {
  changeAccountRoleRoute,
  changeAccountStatusRoute,
  createAdminAccountRoute,
  getCurrentSessionRoute,
  listAdminAccountsRoute,
  resetAccountPasswordRoute,
} from "@/test/backend-routes";
import {
  createFakeBackend,
  exampleAnswer,
  type FakeAnswer,
  type FakeRoute,
} from "@/test/fake-backend";
import { renderApp, testSettings } from "@/test/render-app";

/** The answers of the Accounts screen of a test. */
export type AccountAnswers = {
  readonly list?: readonly FakeAnswer[];
  readonly role?: readonly FakeAnswer[];
  readonly status?: readonly FakeAnswer[];
  readonly create?: readonly FakeAnswer[];
  readonly reset?: readonly FakeAnswer[];
  readonly settings?: typeof testSettings;
  readonly path?: string;
};

/** The operations of the Accounts screen that a test answers. */
const accountOperations = ["list", "role", "status", "create", "reset"] as const;

/** An operation of the Accounts screen. */
type AccountOperation = (typeof accountOperations)[number];

const routeByOperation: Readonly<Record<AccountOperation, FakeRoute>> = {
  list: listAdminAccountsRoute,
  role: changeAccountRoleRoute,
  status: changeAccountStatusRoute,
  create: createAdminAccountRoute,
  reset: resetAccountPasswordRoute,
};

/** The answers of an operation that a test does not choose. */
const defaultAnswersByOperation: Readonly<Record<AccountOperation, readonly FakeAnswer[]>> = {
  list: [exampleAnswer(200, "listAdminAccounts", "first-page")],
  role: [exampleAnswer(201, "changeAccountRole", "made-manager")],
  status: [exampleAnswer(201, "changeAccountStatus", "deactivated")],
  create: [exampleAnswer(201, "createAdminAccount", "created")],
  reset: [exampleAnswer(201, "resetAccountPassword", "reset")],
};

/**
 * Open Accounts as the admin of the examples.
 *
 * @param answers - The answers of the list and of the writes.
 * @returns The rendered app.
 */
export function openAccounts(answers: AccountAnswers = {}) {
  const backend = createFakeBackend();
  backend.answer(getCurrentSessionRoute, exampleAnswer(200, "getCurrentSession", "admin"));
  for (const operation of accountOperations) {
    backend.answer(
      routeByOperation[operation],
      ...(answers[operation] ?? defaultAnswersByOperation[operation]),
    );
  }
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

/**
 * Open the create dialog and type a display name.
 *
 * @param user - The user-event instance.
 * @param displayName - The display name to type.
 * @returns The dialog.
 */
export async function openCreateDialog(
  user: ReturnType<typeof renderApp>["user"],
  displayName: string,
): Promise<HTMLElement> {
  await user.click(await screen.findByRole("button", { name: "Create account" }));
  const dialog = await screen.findByRole("dialog", { name: "Create an account" });
  await user.type(within(dialog).getByRole("textbox", { name: "Display name" }), displayName);
  return dialog;
}

/**
 * Open the reset dialog of an account.
 *
 * @param user - The user-event instance.
 * @param name - The display name of the account.
 * @returns The dialog.
 */
export async function openResetDialog(
  user: ReturnType<typeof renderApp>["user"],
  name: string,
): Promise<HTMLElement> {
  const row = await findRow(name);
  await user.click(within(row).getByRole("button", { name: /Reset password/ }));
  return screen.findByRole("dialog", { name: `Reset the password of ${name}?` });
}
