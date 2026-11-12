/**
 * What the intent strip shows (console UI design, Workspace regions and States; FR-01, UI-22,
 * UI-42). The intent sits directly under the customer message, so staff check it first.
 */
import type { AnalysisIntent, IntentCandidate } from "@/features/console-tickets/model/analysis";
import type { DraftPart } from "@/features/console-tickets/model/draft";
import type { TicketWorkspace } from "@/features/console-tickets/model/workspace";
import { isLowConfidence } from "@/features/console-tickets/model/workspace-state";

/** How many alternatives the strip shows next to the intent: the next two (FR-01). */
const SHOWN_ALTERNATIVE_COUNT = 2;

/** The intent strip. */
export type IntentAreaState =
  | { readonly kind: "none" }
  | { readonly kind: "loading" }
  | { readonly kind: "unknown" }
  | {
      readonly kind: "intent";
      readonly intent: AnalysisIntent;
      readonly alternatives: readonly IntentCandidate[];
    }
  | {
      readonly kind: "choose";
      readonly intent: Extract<AnalysisIntent, { readonly source: "model" }>;
      readonly alternatives: readonly IntentCandidate[];
    };

/**
 * Choose what the intent strip shows.
 *
 * @param workspace - The ticket.
 * @returns Nothing without an analysis; a skeleton while it is pending; the top three candidates
 *   to choose from after an abstention for low confidence (ESC-01); otherwise the intent with the
 *   next two candidates.
 */
export function getIntentAreaState(workspace: TicketWorkspace): IntentAreaState {
  const suggestion = workspace.suggestion;
  if (workspace.handlingMode === "manual" || suggestion === undefined) {
    return { kind: "none" };
  }
  const analysis = suggestion.analysis;
  if (analysis.status === "pending") {
    return { kind: "loading" };
  }
  if (analysis.status === "unavailable") {
    return { kind: "none" };
  }
  if (analysis.intent === undefined) {
    return { kind: "unknown" };
  }
  const intent = analysis.intent;
  const alternatives = analysis.alternatives.slice(0, SHOWN_ALTERNATIVE_COUNT);
  if (intent.source === "model" && isAbstainedForLowConfidence(suggestion.draft)) {
    return { kind: "choose", intent, alternatives };
  }
  return { kind: "intent", intent, alternatives };
}

/**
 * Tell whether the draft abstained for low confidence, so staff choose an intent (UI-42).
 *
 * @param draft - The draft part of the suggestion.
 * @returns True for an `abstained` draft with `low_confidence`.
 */
function isAbstainedForLowConfidence(draft: DraftPart): boolean {
  return draft.status === "abstained" && isLowConfidence(draft.reasonCodes);
}
