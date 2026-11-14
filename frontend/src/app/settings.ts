/**
 * The typed settings of frontend (ARCH-33), parsed once by the composition root and validated at
 * startup (ARCH-34). Every setting has a safe default, so a fresh clone runs without a `.env`
 * file. `.env.example` lists each one.
 */
import { TRACE_ID_SLOT } from "@/features/session";

/** The backend contract, section Timeouts: frontend stops waiting after 10 000 ms. */
const DEFAULT_REQUEST_TIMEOUT_MS = 10_000;

/** ERR-13: bounded retries. Two retries keep a read within three timeouts. */
const DEFAULT_REQUEST_RETRY_MAX_COUNT = 2;

/** ERR-13: exponential backoff that starts at half a second. */
const DEFAULT_REQUEST_RETRY_BASE_DELAY_MS = 500;

/** The value of the dev mode setting that makes dev mode available (UI-35). */
const DEV_MODE_ON = "on";

/** The value of the dev mode setting that keeps dev mode unavailable (UI-35). */
const DEV_MODE_OFF = "off";

/**
 * The hosts whose Grafana may use plain http, compared exactly with the parsed `hostname`, never
 * as a prefix of the text. SEC-28 requires TLS only for connections that leave the machine, and
 * the local Grafana of ADR-0007 (`grafana/otel-lgtm`) runs on the developer's machine without TLS.
 * Every other host needs https.
 */
const loopbackHosts: ReadonlySet<string> = new Set(["localhost", "127.0.0.1", "[::1]"]);

/** The settings that the composition root wires into the client and the query client. */
export type FrontendSettings = {
  /** How long frontend waits for each `backend` response (ERR-09). */
  readonly requestTimeoutMs: number;
  /** How many times a retryable request is sent again (ERR-12, ERR-13). */
  readonly requestRetryMaxCount: number;
  /** The first retry delay, doubled for each later attempt, with jitter (ERR-13). */
  readonly requestRetryBaseDelayMs: number;
  /**
   * Whether dev mode is available, so that each user of the console can switch it on for
   * themselves (UI-35): on in local development, off in the demo deployment.
   */
  readonly isDevModeAvailable: boolean;
  /**
   * The link to a trace in Grafana, with `{trace_id}` where the trace ID goes (UI-35). Absent when
   * no Grafana is set up: the developer details then show the trace ID without a link.
   */
  readonly grafanaTraceUrl?: string;
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
  const grafanaTraceUrl = parseTraceUrlSetting(environment, "VITE_GRAFANA_TRACE_URL");
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
    isDevModeAvailable: parseDevModeSetting(environment, "VITE_DEV_MODE"),
    ...(grafanaTraceUrl === undefined ? {} : { grafanaTraceUrl }),
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

/**
 * Read the dev mode setting. When it is not set, dev mode follows the Vite build: available on the
 * dev server (`DEV` is true) and not in a production build, so local development has it and the
 * demo deployment does not, without a `.env` file (UI-35).
 *
 * @param environment - The Vite environment.
 * @param name - The variable name, which the error message repeats.
 * @returns Whether dev mode is available.
 * @throws InvalidSettingError when the value is neither `on` nor `off`.
 */
function parseDevModeSetting(environment: FrontendEnvironment, name: string): boolean {
  const raw = environment[name];
  if (raw === undefined || raw === "") {
    return environment["DEV"] === true;
  }
  // Compared with each value, never looked up in an object: a lookup would also find inherited
  // keys such as `constructor` and switch dev mode on for a wrong value (ARCH-34).
  if (raw !== DEV_MODE_ON && raw !== DEV_MODE_OFF) {
    throw new InvalidSettingError(`${name} must be "on" or "off", got "${String(raw)}".`);
  }
  return raw === DEV_MODE_ON;
}

/**
 * Read the setting of the Grafana trace link.
 *
 * @param environment - The Vite environment.
 * @param name - The variable name, which the error message repeats.
 * @returns The link with its `{trace_id}` slot, or undefined when the variable is not set.
 * @throws InvalidSettingError when the value is not an absolute https URL, or http on the
 *   developer's machine, with exactly one slot.
 */
function parseTraceUrlSetting(environment: FrontendEnvironment, name: string): string | undefined {
  const raw = environment[name];
  if (raw === undefined || raw === "") {
    return undefined;
  }
  if (typeof raw !== "string" || raw.split(TRACE_ID_SLOT).length !== 2 || !isAllowedTraceUrl(raw)) {
    throw new InvalidSettingError(
      `${name} must be an https URL, or http on localhost, 127.0.0.1, or [::1], ` +
        `with one ${TRACE_ID_SLOT}, ` +
        `got "${String(raw)}".`,
    );
  }
  return raw;
}

/**
 * Tell whether a text is an absolute URL that a trace link may use: https, or http on a loopback
 * host.
 *
 * @param text - The text.
 * @returns True for an https URL, or an http URL of the developer's machine.
 */
function isAllowedTraceUrl(text: string): boolean {
  if (!URL.canParse(text)) {
    return false;
  }
  const { protocol, hostname } = new URL(text);
  return protocol === "https:" || (protocol === "http:" && loopbackHosts.has(hostname));
}
