/**
 * Mappings of the value types that several `backend` schemas share (CON-09), so each feature's
 * model/ maps them the same way.
 */
import type { Money } from "@/design-system";

/**
 * The `maxLength` of `MessageText` (contracts/schemas/MessageText.yaml). The rule of `MessageText`
 * in the contract: from 1 to 2 000 characters, counted in Unicode code points as JSON Schema counts
 * string length ({@link countContractCharacters}). frontend checks it before sending as a
 * convenience; `backend` enforces it with `422` (shop UI design, Components and responsibilities;
 * console UI design, Actions).
 */
export const MESSAGE_MAX_LENGTH = 2000;

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
 * Count the characters of a text as the contract counts them: JSON Schema counts the length of a
 * string in Unicode code points, so an emoji counts once and a password of 128 emoji is allowed.
 *
 * @param text - The text, exactly as typed.
 * @returns The number of Unicode code points.
 */
export function countContractCharacters(text: string): number {
  return Array.from(text).length;
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
