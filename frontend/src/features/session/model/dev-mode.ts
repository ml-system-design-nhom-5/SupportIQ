/**
 * The rules of dev mode (UI-35): an environment setting makes it available, and each user switches
 * it on or off for themselves. It only adds developer details to the screens of a role, never
 * changes permissions, and customers never get it.
 *
 * `staff`, `manager`, and `admin` can switch it on, as UI-35 says. In this version only the ticket
 * workspace has developer details, so the switch changes nothing yet on the screens of `admin`.
 */
import type { AccountRole } from "@/features/session/model/session";

/** The roles that can switch dev mode on (UI-35). */
const devModeRoles: ReadonlySet<AccountRole> = new Set(["staff", "manager", "admin"]);

/**
 * The part of the Grafana trace link that the trace ID replaces (UI-35). The settings check that
 * the link holds it once, so this is its only definition.
 */
export const TRACE_ID_SLOT = "{trace_id}";

/** The prefix of the key under which the browser keeps the dev mode switch of an account. */
const PREFERENCE_KEY_PREFIX = "supportiq.dev-mode.";

/**
 * Tell whether a role can switch dev mode on, where dev mode is available.
 *
 * @param role - The role of the signed-in account.
 * @returns True for `staff`, `manager`, and `admin`; never for `customer`.
 */
export function canUseDevMode(role: AccountRole): boolean {
  return devModeRoles.has(role);
}

/**
 * Build the key of the dev mode switch of one account, so that two people who share a browser
 * keep their own choice.
 *
 * @param accountId - The `account_id` of the signed-in account.
 * @returns For example `supportiq.dev-mode.9a7d3e21-…`.
 */
export function buildDevModePreferenceKey(accountId: string): string {
  return `${PREFERENCE_KEY_PREFIX}${accountId}`;
}

/**
 * Build the link to a trace in Grafana.
 *
 * @param traceUrl - The setting, with one `{trace_id}` where the trace ID goes.
 * @param traceId - The W3C trace ID of the contract: 32 lowercase hexadecimal characters.
 * @returns The link to the trace.
 */
export function buildTraceUrl(traceUrl: string, traceId: string): string {
  return traceUrl.replace(TRACE_ID_SLOT, encodeURIComponent(traceId));
}
