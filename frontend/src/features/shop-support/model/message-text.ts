/**
 * The rule of `MessageText` in the contract: from 1 to 2 000 characters, counted in Unicode code
 * points as JSON Schema counts string length. frontend checks it before sending as a convenience;
 * `backend` enforces it with `422` (shop UI design, Components and responsibilities).
 */

/** The `maxLength` of `MessageText` (contracts/schemas/MessageText.yaml). */
export const MESSAGE_MAX_LENGTH = 2000;

/**
 * Count the characters of a message as the contract counts them.
 *
 * @param text - The message, exactly as typed.
 * @returns The number of Unicode code points, so an emoji counts once.
 */
export function countMessageCharacters(text: string): number {
  return Array.from(text).length;
}
