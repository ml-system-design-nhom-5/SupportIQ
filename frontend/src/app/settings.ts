/**
 * The typed settings of frontend (ARCH-33), parsed once by the composition root and validated at
 * startup (ARCH-34). Every setting has a safe default, so a fresh clone runs without a `.env`
 * file. `.env.example` lists each one. Every setting is read through one reader, which also lists
 * it with the value in use for the developer details (admin UI design), so the list never misses
 * a setting.
 */
import {
  BACKEND_WAKE_ORIGIN_SETTING,
  InvalidSettingError,
  parseBackendWakeOrigin,
} from "@/app/build-settings";
import { type ShownSetting, TRACE_ID_SLOT } from "@/features/session";

/** The backend contract, section Timeouts: frontend stops waiting after 10 000 ms. */
const DEFAULT_REQUEST_TIMEOUT_MS = 10_000;

/** Backend wake-up design: Render's start time of about one minute plus 30 s. */
const DEFAULT_BACKEND_WAKE_TIMEOUT_MS = 90_000;

/** ERR-13: bounded retries. Two retries keep a read within three timeouts. */
const DEFAULT_REQUEST_RETRY_MAX_COUNT = 2;

/** ERR-13: exponential backoff that starts at half a second. */
const DEFAULT_REQUEST_RETRY_BASE_DELAY_MS = 500;

/** The value of the dev mode setting that makes dev mode available (UI-35). */
const DEV_MODE_ON = "on";

/** The value of the dev mode setting that keeps dev mode unavailable (UI-35). */
const DEV_MODE_OFF = "off";

/**
 * The build version on the dev server: the value that backend/.env.example gives
 * `BACKEND_BUILD_VERSION` (admin UI design, Developer details in the admin area).
 */
const LOCAL_BUILD_VERSION = "local";

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
  /** The build version of frontend; absent in a production build that was given none. */
  readonly frontendBuildVersion?: string;
  /** The link to the Grafana dashboard System overview (LOG-27); absent when none is set up. */
  readonly grafanaSystemOverviewUrl?: string;
  /** The link to the Grafana dashboard AI pipeline (LOG-27); absent when none is set up. */
  readonly grafanaAiPipelineUrl?: string;
  /** The Render origin of the wake request; absent when no wake request is sent. */
  readonly backendWakeOrigin?: string;
  /** How long a wake request may wait (ERR-09). */
  readonly backendWakeTimeoutMs: number;
  /** Every `VITE_` setting with the value in use, for the developer details (UI-35). */
  readonly viteSettings: readonly ShownSetting[];
};

/** The variables that Vite exposes to the page. Only `VITE_` variables reach it. */
export type FrontendEnvironment = Readonly<Record<string, string | boolean | undefined>>;

/** The value of one variable, or undefined when it is not set. */
type RawSetting = FrontendEnvironment[string];

/** Parses the value of one variable; the name goes into the error message. */
type ParseSetting<Value> = (raw: RawSetting, name: string) => Value;

/** Reads one variable and lists it with the value in use. */
type ReadSetting = <Value extends string | number | boolean | undefined>(
  name: string,
  parse: ParseSetting<Value>,
) => Value;

/**
 * Parse and validate the settings.
 *
 * @param environment - `import.meta.env` in the app, or a plain object in tests.
 * @returns The validated settings.
 * @throws InvalidSettingError naming the first invalid setting.
 */
export function parseFrontendSettings(environment: FrontendEnvironment): FrontendSettings {
  const shown: ShownSetting[] = [];
  const read: ReadSetting = (name, parse) => {
    const value = parse(environment[name], name);
    shown.push(value === undefined ? { name } : { name, value: String(value) });
    return value;
  };
  return {
    ...readRequestSettings(read),
    ...readDevModeSettings(read, environment["DEV"] === true),
    ...readWakeSettings(read),
    viteSettings: shown,
  };
}

/**
 * Read the settings of the requests to `backend`.
 *
 * @param read - The reader of the settings.
 * @returns The timeout and the retries.
 */
function readRequestSettings(
  read: ReadSetting,
): Pick<FrontendSettings, "requestTimeoutMs" | "requestRetryMaxCount" | "requestRetryBaseDelayMs"> {
  return {
    requestTimeoutMs: read(
      "VITE_REQUEST_TIMEOUT_MS",
      integerSetting(DEFAULT_REQUEST_TIMEOUT_MS, 1),
    ),
    requestRetryMaxCount: read(
      "VITE_REQUEST_RETRY_MAX_COUNT",
      integerSetting(DEFAULT_REQUEST_RETRY_MAX_COUNT, 0),
    ),
    requestRetryBaseDelayMs: read(
      "VITE_REQUEST_RETRY_BASE_DELAY_MS",
      integerSetting(DEFAULT_REQUEST_RETRY_BASE_DELAY_MS, 1),
    ),
  };
}

/**
 * Read the settings of dev mode (UI-35).
 *
 * @param read - The reader of the settings.
 * @param isDevServer - True on the dev server, where Vite sets `DEV`.
 * @returns Whether dev mode is available, the build version, and the Grafana links.
 */
function readDevModeSettings(read: ReadSetting, isDevServer: boolean) {
  const isDevModeAvailable = read("VITE_DEV_MODE", (raw, name) =>
    parseDevModeSetting(raw, name, isDevServer),
  );
  const grafanaTraceUrl = read("VITE_GRAFANA_TRACE_URL", grafanaUrlSetting(true));
  const frontendBuildVersion = read("VITE_FRONTEND_BUILD_VERSION", (raw, name) =>
    parseBuildVersionSetting(raw, name, isDevServer),
  );
  const systemOverviewUrl = read("VITE_GRAFANA_SYSTEM_OVERVIEW_URL", grafanaUrlSetting(false));
  const aiPipelineUrl = read("VITE_GRAFANA_AI_PIPELINE_URL", grafanaUrlSetting(false));
  return {
    isDevModeAvailable,
    ...(grafanaTraceUrl === undefined ? {} : { grafanaTraceUrl }),
    ...(frontendBuildVersion === undefined ? {} : { frontendBuildVersion }),
    ...(systemOverviewUrl === undefined ? {} : { grafanaSystemOverviewUrl: systemOverviewUrl }),
    ...(aiPipelineUrl === undefined ? {} : { grafanaAiPipelineUrl: aiPipelineUrl }),
  };
}

/**
 * Read the settings of the wake request (backend wake-up design).
 *
 * @param read - The reader of the settings.
 * @returns The Render origin and the wake timeout.
 */
function readWakeSettings(read: ReadSetting) {
  const backendWakeOrigin = read(BACKEND_WAKE_ORIGIN_SETTING, parseBackendWakeOrigin);
  return {
    ...(backendWakeOrigin === undefined ? {} : { backendWakeOrigin }),
    backendWakeTimeoutMs: read(
      "VITE_BACKEND_WAKE_TIMEOUT_MS",
      integerSetting(DEFAULT_BACKEND_WAKE_TIMEOUT_MS, 1),
    ),
  };
}

/**
 * Create the parser of one integer setting.
 *
 * @param fallback - The default, when the variable is not set.
 * @param minimum - The smallest allowed value.
 * @returns The parser.
 */
function integerSetting(fallback: number, minimum: number): ParseSetting<number> {
  return (raw, name) => {
    if (raw === undefined || raw === "") {
      return fallback;
    }
    const value = typeof raw === "string" ? Number(raw) : Number.NaN;
    if (!Number.isInteger(value) || value < minimum) {
      throw new InvalidSettingError(
        `${name} must be an integer of at least ${String(minimum)}, got "${String(raw)}".`,
      );
    }
    return value;
  };
}

/**
 * Read the dev mode setting. When it is not set, dev mode follows the Vite build: available on the
 * dev server and not in a production build, so local development has it and the demo deployment
 * does not, without a `.env` file (UI-35).
 *
 * @param raw - The value of the variable.
 * @param name - The variable name, which the error message repeats.
 * @param isDevServer - True on the dev server.
 * @returns Whether dev mode is available.
 * @throws InvalidSettingError when the value is neither `on` nor `off`.
 */
function parseDevModeSetting(raw: RawSetting, name: string, isDevServer: boolean): boolean {
  if (raw === undefined || raw === "") {
    return isDevServer;
  }
  // Compared with each value, never looked up in an object: a lookup would also find inherited
  // keys such as `constructor` and switch dev mode on for a wrong value (ARCH-34).
  if (raw !== DEV_MODE_ON && raw !== DEV_MODE_OFF) {
    throw new InvalidSettingError(`${name} must be "on" or "off", got "${String(raw)}".`);
  }
  return raw === DEV_MODE_ON;
}

/**
 * Read the build version. When it is not set, it is `local` on the dev server, and absent in a
 * production build, so a build never shows a wrong version (admin UI design).
 *
 * @param raw - The value of the variable.
 * @param name - The variable name, which the error message repeats.
 * @param isDevServer - True on the dev server.
 * @returns The build version, or undefined.
 * @throws InvalidSettingError when the value is not text.
 */
function parseBuildVersionSetting(
  raw: RawSetting,
  name: string,
  isDevServer: boolean,
): string | undefined {
  if (raw === undefined || raw === "") {
    return isDevServer ? LOCAL_BUILD_VERSION : undefined;
  }
  if (typeof raw !== "string") {
    throw new InvalidSettingError(`${name} must be text, got "${String(raw)}".`);
  }
  return raw;
}

/**
 * Create the parser of a Grafana link: the trace link, with one `{trace_id}`, or the link to a
 * dashboard, which has none (admin UI design).
 *
 * @param hasTraceIdSlot - True for the trace link.
 * @returns The parser, which returns undefined when the variable is not set.
 * @throws InvalidSettingError when the value is not an absolute https URL, or http on the
 *   developer's machine, with exactly as many slots as the link needs.
 */
function grafanaUrlSetting(hasTraceIdSlot: boolean): ParseSetting<string | undefined> {
  const slotCount = hasTraceIdSlot ? 1 : 0;
  return (raw, name) => {
    if (raw === undefined || raw === "") {
      return undefined;
    }
    if (
      typeof raw !== "string" ||
      raw.split(TRACE_ID_SLOT).length !== slotCount + 1 ||
      !isAllowedGrafanaUrl(raw)
    ) {
      throw new InvalidSettingError(
        `${name} must be an https URL, or http on localhost, 127.0.0.1, or [::1], ` +
          `${hasTraceIdSlot ? "with one" : "without"} ${TRACE_ID_SLOT}, ` +
          `got "${String(raw)}".`,
      );
    }
    return raw;
  };
}

/**
 * Tell whether a text is an absolute URL that a Grafana link may use: https, or http on a loopback
 * host.
 *
 * @param text - The text.
 * @returns True for an https URL, or an http URL of the developer's machine.
 */
function isAllowedGrafanaUrl(text: string): boolean {
  if (!URL.canParse(text)) {
    return false;
  }
  const { protocol, hostname } = new URL(text);
  return protocol === "https:" || (protocol === "http:" && loopbackHosts.has(hostname));
}
