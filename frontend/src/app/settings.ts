/**
 * The typed settings of frontend (ARCH-33), parsed once by the composition root and validated at
 * startup (ARCH-34). Every setting has a safe default, so a fresh clone runs without a `.env`
 * file. `.env.example` lists each one.
 */

/** The backend contract, section Timeouts: frontend stops waiting after 10 000 ms. */
const DEFAULT_REQUEST_TIMEOUT_MS = 10_000;

/** ERR-13: bounded retries. Two retries keep a read within three timeouts. */
const DEFAULT_REQUEST_RETRY_MAX_COUNT = 2;

/** ERR-13: exponential backoff that starts at half a second. */
const DEFAULT_REQUEST_RETRY_BASE_DELAY_MS = 500;

/** The settings that the composition root wires into the client and the query client. */
export type FrontendSettings = {
  /** How long frontend waits for each `backend` response (ERR-09). */
  readonly requestTimeoutMs: number;
  /** How many times a retryable request is sent again (ERR-12, ERR-13). */
  readonly requestRetryMaxCount: number;
  /** The first retry delay, doubled for each later attempt, with jitter (ERR-13). */
  readonly requestRetryBaseDelayMs: number;
};

/** The variables that Vite exposes to the page. Only `VITE_` variables reach it. */
export type FrontendEnvironment = Readonly<Record<string, string | boolean | undefined>>;

/** Thrown when a setting has an invalid value, with the setting's name (ARCH-34). */
export class InvalidSettingError extends Error {
  override readonly name = "InvalidSettingError";
}

/**
 * Parse and validate the settings.
 *
 * @param environment - `import.meta.env` in the app, or a plain object in tests.
 * @returns The validated settings.
 * @throws InvalidSettingError naming the first invalid setting.
 */
export function parseFrontendSettings(environment: FrontendEnvironment): FrontendSettings {
  return {
    requestTimeoutMs: parseIntegerSetting(environment, "VITE_REQUEST_TIMEOUT_MS", {
      fallback: DEFAULT_REQUEST_TIMEOUT_MS,
      minimum: 1,
    }),
    requestRetryMaxCount: parseIntegerSetting(environment, "VITE_REQUEST_RETRY_MAX_COUNT", {
      fallback: DEFAULT_REQUEST_RETRY_MAX_COUNT,
      minimum: 0,
    }),
    requestRetryBaseDelayMs: parseIntegerSetting(environment, "VITE_REQUEST_RETRY_BASE_DELAY_MS", {
      fallback: DEFAULT_REQUEST_RETRY_BASE_DELAY_MS,
      minimum: 1,
    }),
  };
}

/**
 * Read one integer setting.
 *
 * @param environment - The Vite environment.
 * @param name - The variable name, which the error message repeats.
 * @param bounds - The default, and the smallest allowed value.
 * @returns The parsed value, or the default when the variable is not set.
 * @throws InvalidSettingError when the value is not an integer of at least `bounds.minimum`.
 */
function parseIntegerSetting(
  environment: FrontendEnvironment,
  name: string,
  bounds: { readonly fallback: number; readonly minimum: number },
): number {
  const raw = environment[name];
  if (raw === undefined || raw === "") {
    return bounds.fallback;
  }
  const value = typeof raw === "string" ? Number(raw) : Number.NaN;
  if (!Number.isInteger(value) || value < bounds.minimum) {
    throw new InvalidSettingError(
      `${name} must be an integer of at least ${String(bounds.minimum)}, got "${String(raw)}".`,
    );
  }
  return value;
}
