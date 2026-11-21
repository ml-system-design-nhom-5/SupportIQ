/**
 * AI reason codes and warnings as the console shows them (console UI design, Workspace regions;
 * UI-18). A reason code that this version does not know is an unspecified reason (CON-22). The
 * warning texts say what to check in plain language (UI-25, UI-28).
 */
import type { AiReasonCodeName } from "@/design-system";

const knownReasonCodes: ReadonlySet<string> = new Set([
  "low_confidence",
  "signal_disagreement",
  "out_of_scope_intent",
  "human_agent_requested",
  "requires_authority",
  "no_valid_document",
  "only_expired_documents",
  "conflicting_sources",
  "missing_information",
  "source_review_overdue",
  "grounding_failed",
  "llm_unavailable",
  "llm_invalid_output",
  "budget_exceeded",
  "ai_service_unavailable",
  "pseudonymization_failed",
]);

/** What staff check for each warning that the contract names (`Warning`, ESC-04). */
const warningTextByReasonCode: Readonly<Partial<Record<AiReasonCodeName, string>>> = {
  signal_disagreement:
    "The intent and the sources point to different topics. Check the intent and the sources.",
  source_review_overdue:
    "A source that the AI found is past its review date. Check that it still applies.",
  conflicting_sources: "Two sources in effect disagree. Check which one applies.",
  missing_information:
    "The request needs information that is in neither the message nor the order. See the note for staff.",
  requires_authority: "A manager decides this ticket. Check the reply with a manager in mind.",
};

/** The text of a warning that has no text of its own. */
const GENERAL_WARNING_TEXT = "Check the draft and its sources before you send it.";

/** A warning of a suggestion: a condition that staff acknowledge before sending (UI-18). */
export type SuggestionWarning = {
  readonly warningId: string;
  readonly reasonCode: AiReasonCodeName;
  /** What staff check, in plain language. */
  readonly text: string;
};

/**
 * Map an AI reason code from `backend`.
 *
 * @param value - An `AiReasonCode`.
 * @returns The code, or `unknown` for a code that this version does not know.
 */
export function toAiReasonCode(value: string): AiReasonCodeName {
  return isKnownReasonCode(value) ? value : "unknown";
}

/**
 * Map the reason codes of a part, without repeats, in the order of `backend`.
 *
 * @param values - `AiReasonCode` values.
 * @returns The codes; codes that this version does not know become one `unknown`.
 */
export function toAiReasonCodes(values: readonly string[]): readonly AiReasonCodeName[] {
  return [...new Set(values.map(toAiReasonCode))];
}

/**
 * Read the one reason code of an unavailable part.
 *
 * @param reasonCodes - The `reason_codes` of the part: exactly one.
 * @returns The code, or `unknown` when the list is empty.
 */
export function toFirstReasonCode(reasonCodes: readonly string[]): AiReasonCodeName {
  const [first] = reasonCodes;
  return first === undefined ? "unknown" : toAiReasonCode(first);
}

/**
 * Map a warning from `backend`.
 *
 * @param warning - A `Warning`, with its identifier and its reason code.
 * @returns The warning with the text that staff read.
 */
export function toSuggestionWarning(warning: {
  readonly warning_id: string;
  readonly reason_code: string;
}): SuggestionWarning {
  const reasonCode = toAiReasonCode(warning.reason_code);
  return {
    warningId: warning.warning_id,
    reasonCode,
    text: warningTextByReasonCode[reasonCode] ?? GENERAL_WARNING_TEXT,
  };
}

/**
 * Tell whether a value is a reason code of the contract.
 *
 * @param value - An `AiReasonCode` from `backend`.
 * @returns True for one of the 16 codes.
 */
function isKnownReasonCode(value: string): value is Exclude<AiReasonCodeName, "unknown"> {
  return knownReasonCodes.has(value);
}
