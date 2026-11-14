/**
 * The developer details of a suggestion (console UI design, Workspace regions; UI-35): the trace
 * ID, and for each part its raw status and reason codes, the release and asset versions, and the
 * time that `ai-service` spent. Values stay as `backend` sent them, also a status or a code that
 * this version does not know, because developers compare them with the logs. All of it is
 * Internal data.
 */
import { formatCount } from "@/design-system";
import type {
  AnalysisPartContract,
  DraftPartContract,
  SuggestionContract,
} from "@/features/console-tickets/api/contract-types";

/** The terms of the versions of a part, in the order of `AssetVersions`. */
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

/** What a part of a suggestion holds for developers. */
export type PartDetails = {
  readonly part: "analysis" | "draft";
  /** `analysis_status` or `draft_status`, as sent. */
  readonly status: string;
  /** The reason codes of the routing or of the part, as sent; empty when there are none. */
  readonly reasonCodes: readonly string[];
  /** The reason codes of the warnings of a ready analysis, as sent; empty otherwise. */
  readonly warningCodes: readonly string[];
  /** Absent while the part is pending or when `backend` could not get it. */
  readonly versions?: PartVersions;
  /** Absent while the part is pending or when `backend` could not get it. */
  readonly latencies?: PartLatencies;
};

/** The developer details of one suggestion. */
export type DeveloperDetails = {
  /** The W3C trace ID of the job that ran the suggestion. */
  readonly traceId: string;
  readonly suggestionId: string;
  /** Why `backend` started the suggestion, as sent. */
  readonly trigger: string;
  readonly analysis: PartDetails;
  readonly draft: PartDetails;
};

/** One line of the developer details: a term and its value as text. */
export type DetailLine = {
  readonly term: string;
  readonly value: string;
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
    analysis: {
      part: "analysis",
      status: analysis.analysis_status,
      reasonCodes: readAnalysisReasonCodes(analysis),
      warningCodes: "warnings" in analysis ? analysis.warnings.map((item) => item.reason_code) : [],
      ...readMeasurements(analysis),
    },
    draft: {
      part: "draft",
      status: draft.draft_status,
      reasonCodes: "reason_codes" in draft ? draft.reason_codes : [],
      warningCodes: [],
      ...readMeasurements(draft),
    },
  };
}

/**
 * Describe a part as lines. A part without a completed call (pending, or one that `backend` could
 * not get) has only its status and reason codes: no empty versions and no zero latencies.
 *
 * @param part - The details of the part.
 * @returns The status, the reason codes, the warnings of a ready analysis, the versions, and the
 *   latencies in milliseconds.
 */
export function describePartDetails(part: PartDetails): readonly DetailLine[] {
  const { versions, latencies } = part;
  return [
    { term: "Status", value: part.status },
    { term: "Reason codes", value: joinCodes(part.reasonCodes) },
    ...(part.part === "analysis" && versions !== undefined
      ? [{ term: "Warnings", value: joinCodes(part.warningCodes) }]
      : []),
    ...(versions === undefined
      ? []
      : versionTerms.map(([key, term]) => ({ term, value: versions[key] }))),
    ...(latencies === undefined ? [] : describeLatencies(latencies)),
  ];
}

/**
 * Describe the time that `ai-service` spent on a call.
 *
 * @param latencies - The latencies of the call.
 * @returns The total, the analysis, and the LLM time, or that there was no LLM call.
 */
function describeLatencies(latencies: PartLatencies): readonly DetailLine[] {
  return [
    { term: "Total time", value: formatMilliseconds(latencies.totalMs) },
    { term: "Analysis time", value: formatMilliseconds(latencies.analysisMs) },
    {
      term: "LLM time",
      value: latencies.llmMs === undefined ? NO_LLM_CALL_TEXT : formatMilliseconds(latencies.llmMs),
    },
  ];
}

/**
 * Format a duration as `backend` sent it.
 *
 * @param milliseconds - The duration in milliseconds.
 * @returns For example `3,420 ms`.
 */
function formatMilliseconds(milliseconds: number): string {
  return `${formatCount(milliseconds)} ms`;
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

/**
 * Read the reason codes of an analysis: those of its routing when it is ready, its own when it is
 * unavailable.
 *
 * @param analysis - The analysis part.
 * @returns The codes as sent, or none while it is pending.
 */
function readAnalysisReasonCodes(analysis: AnalysisPartContract): readonly string[] {
  if ("routing" in analysis) {
    return analysis.routing.reason_codes;
  }
  return "reason_codes" in analysis ? analysis.reason_codes : [];
}

/**
 * Read the versions and the latencies of a part, which only a completed call has.
 *
 * @param part - The analysis or the draft part.
 * @returns Both, or nothing.
 */
function readMeasurements(
  part: AnalysisPartContract | DraftPartContract,
): Pick<PartDetails, "versions" | "latencies"> {
  if (!("versions" in part) || !("step_latencies" in part)) {
    return {};
  }
  const { versions, step_latencies: latencies } = part;
  return {
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
