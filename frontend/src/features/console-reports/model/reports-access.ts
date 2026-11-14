/**
 * Who reads the report (ADR-0012, UI-44): managers only, as the permission table of
 * `getConsoleReport` says. The console uses this rule only to leave out the Reports link and the
 * request for other roles; `backend` stays the check, and a `403` still shows the
 * permission-denied state (UI-40, SEC-20).
 */
import type { AccountRole } from "@/features/session";

/**
 * Tell whether a role reads the report.
 *
 * @param role - The role of the signed-in account.
 * @returns True only for `manager`.
 */
export function canReadReports(role: AccountRole): boolean {
  return role === "manager";
}
