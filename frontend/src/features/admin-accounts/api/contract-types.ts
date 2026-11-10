/**
 * The contract types of the admin account operations, for the mappings in model/ (TS-09).
 */
import type { components } from "@/api/generated/backend";

/** `AdminAccountView`: an internal account as the admin area shows it. */
export type AdminAccountContract = components["schemas"]["AdminAccountView"];

/** `AdminAccountPage`: one page of `listAdminAccounts`. */
export type AdminAccountPageContract = components["schemas"]["AdminAccountPage"];
