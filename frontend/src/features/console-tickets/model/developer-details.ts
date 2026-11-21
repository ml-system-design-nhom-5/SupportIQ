/**
 * The developer details of a suggestion (console UI design, Workspace regions; UI-35): the trace
 * ID, and for each part its raw status and reason codes, the release and asset versions, and the
 * time that `ai-service` spent. Values stay as `backend` sent them, also a status or a code that
 * this version does not know, because developers compare them with the logs. All of it is
 * Internal data.
 */
import { formatMilliseconds } from "@/design-system";
import type {
  AnalysisPartContract,
  DraftPartContract,
  SuggestionContract,
} from "@/features/console-tickets/api/contract-types";

/** The terms of the versions of a call, in the order of `AssetVersions`. */
const versionTerms: readonly (readonly [keyof PartVersions, string])[] = [
  ["releaseId", "Release"],
  ["modelVersion", "Model"],
  ["kbVersion", "KB"],
  ["mappingVersion", "Mapping"],
  ["promptVersion", "Prompts"],
  ["routingVersion", "Routing"],
  ["indexVersion", "Index"],
];

/** The value of a list of codes that is empty. */
const NO_CODES_TEXT = "None";

/** The value of the LLM time of a call that made no LLM request (`llm_ms` absent). */
const NO_LLM_CALL_TEXT = "No LLM call";

/** The release and asset versions that produced a part (`AssetVersions`, ARCH-39). */
export type PartVersions = {
  readonly releaseId: string;
  readonly modelVersion: string;
  readonly kbVersion: string;
  readonly mappingVersion: string;
  readonly promptVersion: string;
  readonly routingVersion: string;
  readonly indexVersion: string;
};

/** The time that `ai-service` spent on one call, in milliseconds (`StepLatencies`). */
export type PartLatencies = {
  readonly totalMs: number;
  readonly analysisMs: number;
  /** Absent when the call made no LLM request. */
  readonly llmMs?: number;
};

/**
 * What a part of a suggestion holds for developers, by what `backend` sent for it. The status is
 * `analysis_status` or `draft_status`, and the reason codes are those of the routing or of the
 * part, all as sent.
 * `pending`: the part is still running, so it has only its status.
 * `not_called`: `backend` could not get the part, so it has its reason codes and no call.
 * `called`: `ai-service` answered, so the part also has the versions and the latencies of the
 * call.
 */
export type PartDetails =
  | { readonly kind: "pending"; readonly status: string }
  | {
      readonly kind: "not_called";
      readonly status: string;
      readonly reasonCodes: readonly string[];
    }
  | {
      readonly kind: "called";
      readonly status: string;
      readonly reasonCodes: readonly string[];
      readonly versions: PartVersions;
      readonly latencies: PartLatencies;
    };

/** The developer details of one suggestion. */
export type DeveloperDetails = {
  /** The W3C trace ID of the job that ran the suggestion. */
  readonly traceId: string;
  readonly suggestionId: string;
  /** Why `backend` started the suggestion, as sent. */
  readonly trigger: string;
  readonly analysis: PartDetails;
  /** The reason codes of the warnings of a ready analysis, as sent; empty otherwise. */
  readonly analysisWarningCodes: readonly string[];
  readonly draft: PartDetails;
};

/** One line of the developer details: a term and its value as text. */
export type DetailLine = {
  readonly term: string;
  readonly value: string;
  /** True for a version or another identifier, which the screen shows in monospace (UI-08). */
  readonly isIdentifier: boolean;
};

/**
 * Map the developer details of a suggestion.
 *
 * @param suggestion - A `SuggestionView`.
 * @returns The trace ID, the suggestion, its trigger, and the details of both parts.
 */
export function toDeveloperDetails(suggestion: SuggestionContract): DeveloperDetails {
  const { analysis, draft } = suggestion;
  return {
    traceId: suggestion.trace_id,
    suggestionId: suggestion.suggestion_id,
    trigger: suggestion.trigger,
    analysis: toPartDetails(analysis, analysis.analysis_status),
    analysisWarningCodes:
      "warnings" in analysis ? analysis.warnings.map((warning) => warning.reason_code) : [],
    draft: toPartDetails(draft, draft.draft_status),
  };
}

/**
 * Build the lines of a part: a pending part has only its status, a part without a call adds its
 * reason codes, and a called part adds the warnings it was given, the versions, and the latencies.
 * No line is empty, and no latency shows as 0.
 *
 * @param part - The details of the part.
 * @param warningCodes - The warning codes of a ready analysis; absent for the draft.
 * @returns The lines, in the order of the panel.
 */
export function buildDetailLines(
  part: PartDetails,
  warningCodes?: readonly string[],
): readonly DetailLine[] {
  const statusLine = buildTextLine("Status", part.status);
  if (part.kind === "pending") {
    return [statusLine];
  }
  const reasonLine = buildTextLine("Reason codes", joinCodes(part.reasonCodes));
  if (part.kind === "not_called") {
    return [statusLine, reasonLine];
  }
  return [
    statusLine,
    reasonLine,
    ...(warningCodes === undefined ? [] : [buildTextLine("Warnings", joinCodes(warningCodes))]),
    ...versionTerms.map(([key, term]) => ({ term, value: part.versions[key], isIdentifier: true })),
    ...buildLatencyLines(part.latencies),
  ];
}

/**
 * Convert a part from `backend` by what it holds.
 *
 * @param part - The analysis or the draft part.
 * @param status - Its `analysis_status` or `draft_status`.
 * @returns The part: pending, without a call, or with its call.
 */
function toPartDetails(
  part: AnalysisPartContract | DraftPartContract,
  status: string,
): PartDetails {
  const reasonCodes = getReasonCodes(part);
  if (reasonCodes === undefined) {
    return { kind: "pending", status };
  }
  if (!("versions" in part) || !("step_latencies" in part)) {
    return { kind: "not_called", status, reasonCodes };
  }
  const { versions, step_latencies: latencies } = part;
  return {
    kind: "called",
    status,
    reasonCodes,
    versions: {
      releaseId: versions.release_id,
      modelVersion: versions.model_version,
      kbVersion: versions.kb_version,
      mappingVersion: versions.mapping_version,
      promptVersion: versions.prompt_version,
      routingVersion: versions.routing_version,
      indexVersion: versions.index_version,
    },
    latencies: {
      totalMs: latencies.total_ms,
      analysisMs: latencies.analysis_ms,
      ...(latencies.llm_ms === undefined ? {} : { llmMs: latencies.llm_ms }),
    },
  };
}

/**
 * Get the reason codes of a part: those of the routing of a ready analysis, otherwise its own.
 *
 * @param part - The analysis or the draft part.
 * @returns The codes as sent, or undefined for a pending part, which has none.
 */
function getReasonCodes(
  part: AnalysisPartContract | DraftPartContract,
): readonly string[] | undefined {
  if ("routing" in part) {
    return part.routing.reason_codes;
  }
  return "reason_codes" in part ? part.reason_codes : undefined;
}

/**
 * Build the lines of the time that `ai-service` spent on a call.
 *
 * @param latencies - The latencies of the call.
 * @returns The total, the analysis, and the LLM time, or that there was no LLM call.
 */
function buildLatencyLines(latencies: PartLatencies): readonly DetailLine[] {
  return [
    buildTextLine("Total time", formatMilliseconds(latencies.totalMs)),
    buildTextLine("Analysis time", formatMilliseconds(latencies.analysisMs)),
    buildTextLine(
      "LLM time",
      latencies.llmMs === undefined ? NO_LLM_CALL_TEXT : formatMilliseconds(latencies.llmMs),
    ),
  ];
}

/**
 * Build a line whose value is text, not an identifier.
 *
 * @param term - The term.
 * @param value - The value.
 * @returns The line.
 */
function buildTextLine(term: string, value: string): DetailLine {
  return { term, value, isIdentifier: false };
}

/**
 * Join codes as sent.
 *
 * @param codes - The codes.
 * @returns For example `kb_gap, other`, or `None`.
 */
function joinCodes(codes: readonly string[]): string {
  return codes.length === 0 ? NO_CODES_TEXT : codes.join(", ");
}
