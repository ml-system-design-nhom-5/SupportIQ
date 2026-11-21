/**
 * The settings that the build reads as well as the app (backend wake-up design, rule 10): one
 * parser for each, so the Content Security Policy of the build and the wake request of the app
 * always name the same origin, and an invalid value stops both with the setting's name
 * (ARCH-34). This module imports nothing, so `vite.config.ts` can import it.
 */

/** The setting of the Render origin of `backend`, for the wake request. */
export const BACKEND_WAKE_ORIGIN_SETTING = "VITE_BACKEND_WAKE_ORIGIN";

/** Thrown when a setting has an invalid value, with the setting's name (ARCH-34). */
export class InvalidSettingError extends Error {
  override readonly name = "InvalidSettingError";
}

/**
 * Read the Render origin of `backend`: an `http` or `https` origin without a path, such as
 * `https://<service>.onrender.com`.
 *
 * @param raw - The value of `VITE_BACKEND_WAKE_ORIGIN`, or undefined when it is not set.
 * @returns The origin, or undefined when the setting is not set, so no wake request is sent and
 *   `connect-src` stays `'self'` (rule 9).
 * @throws InvalidSettingError when the value is not such an origin.
 */
export function parseBackendWakeOrigin(raw: unknown): string | undefined {
  if (raw === undefined || raw === "") {
    return undefined;
  }
  if (typeof raw !== "string" || !isHttpOrigin(raw)) {
    throw new InvalidSettingError(
      `${BACKEND_WAKE_ORIGIN_SETTING} must be an http or https origin without a path, such as ` +
        `https://backend.example.com, got ${JSON.stringify(raw)}.`,
    );
  }
  return raw;
}

/**
 * Tell whether a text is exactly an `http` or `https` origin: no path, query, fragment, or
 * trailing slash.
 *
 * @param text - The text.
 * @returns True for such an origin.
 */
function isHttpOrigin(text: string): boolean {
  if (!URL.canParse(text)) {
    return false;
  }
  const url = new URL(text);
  return (url.protocol === "https:" || url.protocol === "http:") && url.origin === text;
}
