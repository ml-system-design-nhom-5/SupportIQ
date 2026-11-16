import { describe, expect, it } from "vitest";

import type { Account } from "@/features/admin-accounts/model/account";
import {
  buildChangeConfirmation,
  buildChangeFailureLead,
  buildChangeOutcomeUnknownLead,
  getChangeLabel,
} from "@/features/admin-accounts/model/account-change-text";

const mai: Account = {
  accountId: "1",
  loginName: "staff-1",
  displayName: "Mai Nguyen",
  role: "staff",
  rawRole: "staff",
  isActive: true,
};

describe("buildChangeConfirmation of role changes (admin UI design, Accounts)", () => {
  it("writes the confirmation of Make manager", () => {
    expect(buildChangeConfirmation({ kind: "make_manager", account: mai })).toEqual({
      title: "Make Mai Nguyen a manager?",
      description:
        "Mai Nguyen will be able to send replies on tickets that require authority and to view reports. Mai Nguyen will be signed out of every session.",
      confirmLabel: "Make manager",
      pendingLabel: "Making manager…",
      tone: "default",
    });
  });

  it("writes the confirmation of Make staff", () => {
    expect(buildChangeConfirmation({ kind: "make_staff", account: mai })).toEqual({
      title: "Make Mai Nguyen staff?",
      description:
        "Mai Nguyen will no longer send replies on tickets that require authority or view reports. Mai Nguyen will be signed out of every session.",
      confirmLabel: "Make staff",
      pendingLabel: "Making staff…",
      tone: "default",
    });
  });
});

describe("buildChangeConfirmation of status changes (admin UI design, Accounts)", () => {
  it("writes the confirmation of Deactivate in the danger role", () => {
    expect(buildChangeConfirmation({ kind: "deactivate", account: mai })).toEqual({
      title: "Deactivate Mai Nguyen?",
      description:
        "Mai Nguyen will be signed out of every session and cannot sign in until an admin reactivates the account.",
      confirmLabel: "Deactivate",
      pendingLabel: "Deactivating…",
      tone: "danger",
    });
  });

  it("writes the confirmation of Reactivate", () => {
    expect(buildChangeConfirmation({ kind: "reactivate", account: mai })).toEqual({
      title: "Reactivate Mai Nguyen?",
      description: "Mai Nguyen will be able to sign in again with the current role.",
      confirmLabel: "Reactivate",
      pendingLabel: "Reactivating…",
      tone: "default",
    });
  });
});

describe("buildChangeFailureLead", () => {
  it.each([
    ["make_manager", "Mai Nguyen was not made a manager."],
    ["make_staff", "Mai Nguyen was not made staff."],
    ["deactivate", "Mai Nguyen was not deactivated."],
    ["reactivate", "Mai Nguyen was not reactivated."],
  ] as const)("names the account and the change of %s", (kind, lead) => {
    expect(buildChangeFailureLead({ kind, account: mai })).toBe(lead);
  });
});

describe("buildChangeOutcomeUnknownLead", () => {
  it.each([
    ["make_manager", "Mai Nguyen may have been made a manager."],
    ["make_staff", "Mai Nguyen may have been made staff."],
    ["deactivate", "Mai Nguyen may have been deactivated."],
    ["reactivate", "Mai Nguyen may have been reactivated."],
  ] as const)("names the account and the change of %s", (kind, lead) => {
    expect(buildChangeOutcomeUnknownLead({ kind, account: mai })).toBe(lead);
  });
});

describe("getChangeLabel", () => {
  it.each([
    ["make_manager", "Make manager"],
    ["make_staff", "Make staff"],
    ["deactivate", "Deactivate"],
    ["reactivate", "Reactivate"],
  ] as const)("names the button of %s", (kind, label) => {
    expect(getChangeLabel(kind)).toBe(label);
  });
});
