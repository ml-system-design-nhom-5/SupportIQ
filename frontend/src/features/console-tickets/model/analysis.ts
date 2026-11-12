/**
 * The analysis part of a suggestion (ADR-0005; console UI design, Workspace regions), mapped from
 * `AnalysisPart` (TS-09). An analysis status, an intent source, a recommendation, or a validity
 * that this version does not know maps to the safe value of its contract schema (CON-22).
 */
import type { AiReasonCodeName, ConfidenceBandName, DocumentValidityName } from "@/design-system";
import { requireMembers } from "@/features/backend-requests";
import type {
  AnalysisPartContract,
  RankedDocumentContract,
  ReadyAnalysisContract,
} from "@/features/console-tickets/api/contract-types";
import { type Intent, toIntent } from "@/features/console-tickets/model/intent";
import {
  type SuggestionWarning,
  toAiReasonCodes,
  toFirstReasonCode,
  toSuggestionWarning,
} from "@/features/console-tickets/model/reason-codes";
import { toConfidenceBand } from "@/features/console-tickets/model/ticket-status";

const validities: ReadonlySet<string> = new Set(["valid", "expired", "conflicting"]);

/** The intent that the pipeline used: the model's prediction, or the intent that staff chose. */
export type AnalysisIntent =
  | {
      readonly source: "model";
      readonly intent: Intent;
      readonly band: ConfidenceBandName;
      readonly probability: number;
    }
  | { readonly source: "staff"; readonly intent: Intent };

/** A further candidate intent of the model. */
export type IntentCandidate = {
  readonly intent: Intent;
  readonly probability: number;
};

/** A KB document version that retrieval found. */
export type RankedDocument = {
  readonly documentId: string;
  readonly version: string;
  readonly title: string;
  readonly effectiveStartAt: string;
  readonly effectiveEndAt?: string;
  readonly validity: DocumentValidityName;
  readonly rank: number;
  readonly snippet: string;
};

/** What the AI recommends: `RoutingRecommendation`, where an unknown value is `abstain`. */
export type RoutingRecommendation = "draft" | "abstain" | "escalate";

/** An analysis that `ai-service` returned. */
export type ReadyAnalysis = {
  readonly status: "ready";
  /** Absent when the intent source is one that this version does not know: no known intent. */
  readonly intent?: AnalysisIntent;
  readonly alternatives: readonly IntentCandidate[];
  readonly documents: readonly RankedDocument[];
  readonly recommendation: RoutingRecommendation;
  readonly reasonCodes: readonly AiReasonCodeName[];
  readonly warnings: readonly SuggestionWarning[];
};

/** The analysis part, by status. */
export type AnalysisPart =
  | { readonly status: "pending" }
  | ReadyAnalysis
  | { readonly status: "unavailable"; readonly reasonCode: AiReasonCodeName };

/**
 * Map the analysis part of a suggestion.
 *
 * @param analysis - An `AnalysisPart`.
 * @returns The part; an unknown status is `unavailable`, so the ticket is handled manually.
 */
export function toAnalysisPart(analysis: AnalysisPartContract): AnalysisPart {
  requireMembers(analysis, ["analysis_status"]);
  switch (analysis.analysis_status) {
    case "pending":
      return { status: "pending" };
    case "ready":
      return toReadyAnalysis(analysis);
    case "unavailable":
      return { status: "unavailable", reasonCode: toFirstReasonCode(analysis.reason_codes) };
    default:
      return { status: "unavailable", reasonCode: "unknown" };
  }
}

/**
 * Map a ready analysis.
 *
 * @param analysis - A `ReadyAnalysisPart`.
 * @returns The view model.
 */
function toReadyAnalysis(analysis: ReadyAnalysisContract): ReadyAnalysis {
  requireMembers(analysis, ["intent", "alternatives", "documents", "routing", "warnings"]);
  const intent = toAnalysisIntent(analysis.intent);
  return {
    status: "ready",
    ...(intent === undefined ? {} : { intent }),
    alternatives: analysis.alternatives.map((alternative) => ({
      intent: toIntent(alternative.label),
      probability: alternative.probability,
    })),
    documents: analysis.documents.map(toRankedDocument),
    recommendation: toRecommendation(analysis.routing.recommendation),
    reasonCodes: toAiReasonCodes(analysis.routing.reason_codes),
    warnings: analysis.warnings.map(toSuggestionWarning),
  };
}

/**
 * Map the intent of an analysis.
 *
 * @param intent - A `ConsoleIntent`.
 * @returns The intent, or undefined for a source that this version does not know.
 */
function toAnalysisIntent(intent: ReadyAnalysisContract["intent"]): AnalysisIntent | undefined {
  switch (intent.source) {
    case "model":
      return {
        source: "model",
        intent: toIntent(intent.label),
        band: toConfidenceBand(intent.confidence_band),
        probability: intent.probability,
      };
    case "staff":
      return { source: "staff", intent: toIntent(intent.label) };
    default:
      return undefined;
  }
}

/**
 * Map a ranked document.
 *
 * @param document - A `RankedDocument`.
 * @returns The view model; an unknown validity is `expired`, never presented as usable.
 */
function toRankedDocument(document: RankedDocumentContract): RankedDocument {
  requireMembers(document, ["document_id", "version", "title", "effective_start_at", "rank"]);
  return {
    documentId: document.document_id,
    version: document.version,
    title: document.title,
    effectiveStartAt: document.effective_start_at,
    ...(document.effective_end_at === undefined
      ? {}
      : { effectiveEndAt: document.effective_end_at }),
    validity: isValidity(document.validity) ? document.validity : "expired",
    rank: document.rank,
    snippet: document.snippet,
  };
}

/**
 * Map a routing recommendation.
 *
 * @param value - A `RoutingRecommendation`.
 * @returns The recommendation, or `abstain` for a value that this version does not know.
 */
function toRecommendation(value: string): RoutingRecommendation {
  if (value === "draft" || value === "escalate") {
    return value;
  }
  return "abstain";
}

/**
 * Tell whether a value is a validity of the contract.
 *
 * @param value - A `DocumentValidity` from `backend`.
 * @returns True for `valid`, `expired`, and `conflicting`.
 */
function isValidity(value: string): value is DocumentValidityName {
  return validities.has(value);
}
