/**
 * Read JSON text that comes from outside the code, such as a stored preference or the data of a
 * stream event, as untrusted: text that is not JSON, or a value without the expected field, gives
 * undefined, never an error.
 */

/**
 * Parse text that should be JSON.
 *
 * @param text - The text.
 * @returns The value, or undefined when the text is not JSON.
 * @throws Any error other than the SyntaxError of text that is not JSON.
 */
export function parseJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch (error) {
    if (error instanceof SyntaxError) {
      return undefined;
    }
    throw error;
  }
}

/**
 * Read a field of a value that should be an object.
 *
 * @param value - The value.
 * @param name - The name of the field.
 * @returns The field, or undefined when the value is not an object or has no such field.
 */
export function readField(value: unknown, name: string): unknown {
  return typeof value === "object" && value !== null ? Reflect.get(value, name) : undefined;
}
