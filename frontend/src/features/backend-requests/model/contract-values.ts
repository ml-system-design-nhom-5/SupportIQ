/**
 * Mappings of the value types that several `backend` schemas share (CON-09), so each feature's
 * model/ maps them the same way.
 */
import type { Money } from "@/design-system";

/** The shape of the contract's shared `Money` schema (CON-16). */
export type MoneyContract = {
  readonly amount_minor: number;
  readonly currency: string;
};

/**
 * Stop at a `backend` body that lacks a member the contract requires, so that a body of the wrong
 * shape never reads as a success (CODE-32). `requestData` turns the error into a failure.
 *
 * @param body - A body of the contract.
 * @param members - The required members that the mapping reads.
 * @throws TypeError naming the first missing member.
 */
export function requireMembers<Body extends object>(
  body: Body,
  members: readonly (keyof Body)[],
): void {
  for (const member of members) {
    if (body[member] === undefined || body[member] === null) {
      throw new TypeError(`The response has no ${String(member)}.`);
    }
  }
}

/**
 * Map the contract's `Money` to the view model of the shared money formatter.
 *
 * @param money - An amount in minor units with its ISO 4217 code.
 * @returns The same amount in camelCase.
 */
export function toMoney(money: MoneyContract): Money {
  requireMembers(money, ["amount_minor", "currency"]);
  return { amountMinor: money.amount_minor, currency: money.currency };
}
