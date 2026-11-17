/**
 * The intent strip of the workspace (console UI design, Workspace regions and States): nothing
 * without an analysis, a skeleton while it is pending, the intent with the next two candidates,
 * or the top three candidates after an abstention for low confidence (UI-42). When `backend`
 * allows a correction, staff use a candidate or Other intent in one interaction, also while a
 * draft is generating (UI-22). A failed correction shows below the strip, with its trace ID
 * (UI-25).
 */
import { Sparkles } from "lucide-react";

import {
  IntentChoice,
  IntentStrip,
  type IntentUse,
  Panel,
  PanelHeader,
  PanelSection,
  Skeleton,
  Text,
  VisuallyHidden,
} from "@/design-system";
import { assertNever, type RequestFailure } from "@/features/backend-requests";
import { FailureViewBanner } from "@/features/console-tickets/components/failure-view-banner";
import type { IntentCandidate } from "@/features/console-tickets/model/analysis";
import type { Intent } from "@/features/console-tickets/model/intent";
import {
  type ChoosableIntentLabel,
  getChoosableLabel,
  type IntentAreaState,
  listOtherIntents,
} from "@/features/console-tickets/model/intent-area";
import { describeSuggestionFailure } from "@/features/console-tickets/model/suggestion-failure";

/** The ID of Other intent, which takes the focus once a correction started a new draft (UI-30). */
export const OTHER_INTENT_ID = "other-intent-button";

/** Props of {@link IntentSection}. */
type IntentSectionProps = {
  readonly state: IntentAreaState;
  /** True while a correction or a retry is sending, so no second correction starts. */
  readonly isSending: boolean;
  /** The failure of the last correction; undefined when there is none. */
  readonly correctionFailure: RequestFailure | undefined;
  readonly onCorrectIntent: (intentLabel: ChoosableIntentLabel) => void;
};

/**
 * Render the intent strip in its state, and the failure of the last correction.
 *
 * @param props - The state of the strip, whether a request is sending, the failure, and the
 *   handler of a correction.
 * @returns The strip and the failure, or nothing.
 */
export function IntentSection({
  state,
  isSending,
  correctionFailure,
  onCorrectIntent,
}: IntentSectionProps) {
  return (
    <>
      <IntentRegion state={state} use={{ isSending, onUseIntent: onCorrectIntent }} />
      {correctionFailure === undefined ? null : (
        <FailureViewBanner failure={describeSuggestionFailure(correctionFailure, "correction")} />
      )}
    </>
  );
}

/**
 * Render the strip in its state.
 *
 * @param props - The state, and how staff use an intent.
 * @returns The strip, or nothing.
 */
function IntentRegion({
  state,
  use,
}: {
  readonly state: IntentAreaState;
  readonly use: IntentUse<ChoosableIntentLabel>;
}) {
  switch (state.kind) {
    case "none":
      return null;
    case "loading":
      return (
        <Panel density="compact" as="section" label="Intent" tone="ai">
          <PanelSection>
            <p role="status">
              <VisuallyHidden>Analyzing the message…</VisuallyHidden>
            </p>
            <Skeleton width="half" />
          </PanelSection>
        </Panel>
      );
    case "unknown":
      return (
        <Panel density="compact" as="section" label="Intent" tone="ai">
          <PanelHeader icon={Sparkles} level={2} title="Intent" />
          <PanelSection>
            <Text tone="muted">The AI returned an intent that this console does not know.</Text>
          </PanelSection>
        </Panel>
      );
    case "intent":
      return <IntentOfAnalysis state={state} use={use} />;
    case "choose":
      return <IntentCandidates state={state} use={use} />;
    default:
      assertNever(state);
  }
}

/**
 * Render the intent that the pipeline used, with the next two candidates, and the correction when
 * `backend` allows it.
 *
 * @param props - The state, and how staff use an intent.
 * @returns The strip.
 */
function IntentOfAnalysis({
  state,
  use,
}: {
  readonly state: Extract<IntentAreaState, { readonly kind: "intent" }>;
  readonly use: IntentUse<ChoosableIntentLabel>;
}) {
  const { intent } = state;
  return (
    <IntentStrip
      intentName={intent.intent.name}
      {...(intent.source === "model"
        ? { confidence: { band: intent.band, probability: intent.probability } }
        : {})}
      candidates={state.alternatives.map(toCandidate)}
      {...(state.canCorrect
        ? {
            correction: {
              ...use,
              otherIntentId: OTHER_INTENT_ID,
              otherIntents: listOtherIntents(intent.intent).map((other) => ({
                value: other.label,
                name: other.name,
              })),
            },
          }
        : {})}
    />
  );
}

/**
 * Render the top three candidates after an abstention for low confidence, each with "Use this
 * intent" when `backend` allows a correction (UI-42).
 *
 * @param props - The state, and how staff use an intent.
 * @returns The choice.
 */
function IntentCandidates({
  state,
  use,
}: {
  readonly state: Extract<IntentAreaState, { readonly kind: "choose" }>;
  readonly use: IntentUse<ChoosableIntentLabel>;
}) {
  return (
    <IntentChoice
      candidates={[
        {
          name: state.intent.intent.name,
          probability: state.intent.probability,
          band: state.intent.band,
          ...toCandidateValue(state.intent.intent),
        },
        ...state.alternatives.map(toCandidate),
      ]}
      {...(state.canCorrect ? { use } : {})}
    />
  );
}

/**
 * Map a further candidate of the model for the strip or the choice.
 *
 * @param candidate - The candidate.
 * @returns Its name, its probability, and its label when staff can choose it.
 */
function toCandidate(candidate: IntentCandidate) {
  return {
    name: candidate.intent.name,
    probability: candidate.probability,
    ...toCandidateValue(candidate.intent),
  };
}

/**
 * Give a candidate the label that a correction sends.
 *
 * @param intent - The intent of the candidate.
 * @returns The label as a member to spread, or nothing for an intent that staff cannot choose.
 */
function toCandidateValue(intent: Intent): { readonly value?: ChoosableIntentLabel } {
  const label = getChoosableLabel(intent);
  return label === undefined ? {} : { value: label };
}
