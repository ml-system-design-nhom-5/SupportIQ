/**
 * The query keys of the admin accounts feature (TS-19).
 */

/** The one key factory of the admin accounts feature. */
export const accountQueryKeys = {
  all: ["admin-accounts"] as const,
  accounts: () => [...accountQueryKeys.all, "accounts"] as const,
};
