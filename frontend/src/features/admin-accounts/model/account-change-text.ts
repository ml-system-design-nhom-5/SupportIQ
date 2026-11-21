/**
 * The texts of an account change: the button, the confirmation dialog, and the banner of a change
 * that did not happen (admin UI design, Accounts). Every confirmation names the account and the
 * change (UI-45).
 */
import type { AccountChange, AccountChangeKind } from "@/features/admin-accounts/model/account";

/** The labels of each change. The button and the confirm button use the same verb. */
const labelsByChangeKind: Readonly<
  Record<AccountChangeKind, { readonly label: string; readonly pendingLabel: string }>
> = {
  make_manager: { label: "Make manager", pendingLabel: "Making manager…" },
  make_staff: { label: "Make staff", pendingLabel: "Making staff…" },
  deactivate: { label: "Deactivate", pendingLabel: "Deactivating…" },
  reactivate: { label: "Reactivate", pendingLabel: "Reactivating…" },
};

/** The title, the description, and the tone of each confirmation. */
const confirmationByChangeKind: Readonly<
  Record<
    AccountChangeKind,
    (name: string) => Pick<AccountChangeConfirmation, "title" | "description" | "tone">
  >
> = {
  make_manager: (name) => ({
    title: `Make ${name} a manager?`,
    description: `${name} will be able to send replies on tickets that require authority and to view reports. ${name} will be signed out of every session.`,
    tone: "default",
  }),
  make_staff: (name) => ({
    title: `Make ${name} staff?`,
    description: `${name} will no longer send replies on tickets that require authority or view reports. ${name} will be signed out of every session.`,
    tone: "default",
  }),
  deactivate: (name) => ({
    title: `Deactivate ${name}?`,
    description: `${name} will be signed out of every session and cannot sign in until an admin reactivates the account.`,
    tone: "danger",
  }),
  reactivate: (name) => ({
    title: `Reactivate ${name}?`,
    description: `${name} will be able to sign in again with the current role.`,
    tone: "default",
  }),
};

/** What each change does to its account, as the banners of a failed change say it. */
const resultByChangeKind: Readonly<Record<AccountChangeKind, string>> = {
  make_manager: "made a manager",
  make_staff: "made staff",
  deactivate: "deactivated",
  reactivate: "reactivated",
};

/** The confirmation dialog of a change. */
export type AccountChangeConfirmation = {
  readonly title: string;
  readonly description: string;
  readonly confirmLabel: string;
  readonly pendingLabel: string;
  readonly tone: "default" | "danger";
};

/**
 * Name the button of a change.
 *
 * @param kind - The change.
 * @returns For example "Make manager".
 */
export function getChangeLabel(kind: AccountChangeKind): string {
  return labelsByChangeKind[kind].label;
}

/**
 * Write the confirmation dialog of a change, with the texts of the admin UI design.
 *
 * @param change - The change and its account.
 * @returns The title, the description, the labels, and the tone.
 */
export function buildChangeConfirmation(change: AccountChange): AccountChangeConfirmation {
  const { label, pendingLabel } = labelsByChangeKind[change.kind];
  return {
    ...confirmationByChangeKind[change.kind](change.account.displayName),
    confirmLabel: label,
    pendingLabel,
  };
}

/**
 * Write the first sentence of the banner of a change that did not happen.
 *
 * @param change - The change and its account.
 * @returns For example "Hoa Pham was not deactivated."
 */
export function buildChangeFailureLead(change: AccountChange): string {
  return `${change.account.displayName} was not ${resultByChangeKind[change.kind]}.`;
}

/**
 * Write the first sentence of the banner of a change that may have happened.
 *
 * @param change - The change and its account.
 * @returns For example "Hoa Pham may have been deactivated."
 */
export function buildChangeOutcomeUnknownLead(change: AccountChange): string {
  return `${change.account.displayName} may have been ${resultByChangeKind[change.kind]}.`;
}
