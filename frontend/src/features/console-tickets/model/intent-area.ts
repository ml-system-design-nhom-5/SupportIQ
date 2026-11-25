/**
 * What the intent strip shows (console UI design, Workspace regions and States; FR-01, UI-22,
 * UI-42). The intent sits directly under the customer message, so staff check it first. Staff can
 * correct it whenever `backend` allows it (`correct_intent`), also while a draft is generating; the
 * UI never decides that itself (UI-40).
 */
import type { AnalysisIntent, IntentCandidate } from "@/features/console-tickets/model/analysis";
import type { DraftPart } from "@/features/console-tickets/model/draft";
import {
  type Intent,
  type IntentLabel,
  intentLabels,
  toIntent,
} from "@/features/console-tickets/model/intent";
import type { TicketWorkspace } from "@/features/console-tickets/model/workspace";
import { isLowConfidence } from "@/features/console-tickets/model/workspace-state";

/** How many alternatives the strip shows next to the intent: the next two (FR-01). */
const SHOWN_ALTERNATIVE_COUNT = 2;

/** An intent label that staff can choose: one of the 46 labels of the contract. */
export type ChoosableIntentLabel = Exclude<IntentLabel, "unknown">;

/** An intent that staff can choose, with its name. */
export type ChoosableIntent = {
  readonly label: ChoosableIntentLabel;
  readonly name: string;
};

/** The intent strip. */
export type IntentAreaState =
  | { readonly kind: "none" }
  | { readonly kind: "loading" }
  | { readonly kind: "unknown" }
  | {
      readonly kind: "intent";
      readonly intent: AnalysisIntent;
      readonly alternatives: readonly IntentCandidate[];
      /** True when `backend` allows a correction (`correct_intent`). */
      readonly canCorrect: boolean;
    }
  | {
      readonly kind: "choose";
      readonly intent: Extract<AnalysisIntent, { readonly source: "model" }>;
      readonly alternatives: readonly IntentCandidate[];
      /** True when `backend` allows a correction (`correct_intent`). */
      readonly canCorrect: boolean;
    };

/** Every intent that staff can choose, in the order of the contract, which is also by name. */
const choosableIntents: readonly ChoosableIntent[] = intentLabels.map((label) => ({
  label,
  name: toIntent(label).name,
}));

/**
 * Choose what the intent strip shows.
 *
 * @param workspace - The ticket.
 * @returns Nothing without an analysis; a skeleton while it is pending; the top three candidates
 *   to choose from after an abstention for low confidence (ESC-01); otherwise the intent with the
 *   next two candidates. The last two say whether staff can correct the intent.
 */
export function getIntentAreaState(workspace: TicketWorkspace): IntentAreaState {
  const suggestion = workspace.suggestion;
  if (workspace.handlingMode === "manual" || suggestion === undefined) {
    return { kind: "none" };
  }
  const analysis = suggestion.analysis;
  const canCorrect = workspace.allowedActions.has("correct_intent");
  if (analysis.status === "pending") {
    return getPendingAnalysisState(suggestion.intentOverride, canCorrect);
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
    return { kind: "choose", intent, alternatives, canCorrect };
  }
  return { kind: "intent", intent, alternatives, canCorrect };
}

/**
 * List the intents that Other intent offers: every intent but the one on the strip.
 *
 * @param intent - The intent on the strip.
 * @returns The other intents, in the order of the contract.
 */
export function listOtherIntents(intent: Intent): readonly ChoosableIntent[] {
  return choosableIntents.filter((choosable) => choosable.label !== intent.label);
}

/**
 * Read the label that staff would choose for an intent.
 *
 * @param intent - An intent of the analysis.
 * @returns The label, or undefined for an intent that this version does not know, which staff can
 *   never choose (CON-22).
 */
export function getChoosableLabel(intent: Intent): ChoosableIntentLabel | undefined {
  return intent.label === "unknown" ? undefined : intent.label;
}

/**
 * Choose the strip while the analysis is pending: the intent that staff chose stays on the strip
 * after a correction, and they can change it again (UI-22; console UI design, Flow step 4).
 *
 * @param intentOverride - The intent that staff chose for the suggestion, when they chose one.
 * @param canCorrect - True when `backend` allows a correction.
 * @returns The chosen intent, or the skeleton without one.
 */
function getPendingAnalysisState(
  intentOverride: Intent | undefined,
  canCorrect: boolean,
): IntentAreaState {
  if (intentOverride === undefined) {
    return { kind: "loading" };
  }
  return {
    kind: "intent",
    intent: { source: "staff", intent: intentOverride },
    alternatives: [],
    canCorrect,
  };
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
