/**
 * The intent strip of the workspace (console UI design, Workspace regions and States): nothing
 * without an analysis, a skeleton while it is pending, the intent with the next two candidates,
 * or the top three candidates after an abstention for low confidence (UI-42).
 */
import { Sparkles } from "lucide-react";

import {
  IntentChoice,
  IntentStrip,
  Panel,
  PanelHeader,
  PanelSection,
  Skeleton,
  Text,
  VisuallyHidden,
} from "@/design-system";
import { assertNever } from "@/features/backend-requests";
import type { IntentAreaState } from "@/features/console-tickets/model/intent-area";

/** Props of {@link IntentSection}. */
type IntentSectionProps = {
  readonly state: IntentAreaState;
};

/**
 * Render the intent strip in its state.
 *
 * @param props - The state of the strip.
 * @returns The strip, or nothing.
 */
export function IntentSection({ state }: IntentSectionProps) {
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
      return (
        <IntentStrip
          intentName={state.intent.intent.name}
          {...(state.intent.source === "model"
            ? {
                confidence: {
                  band: state.intent.band,
                  probability: state.intent.probability,
                },
              }
            : {})}
          candidates={state.alternatives.map((alternative) => ({
            name: alternative.intent.name,
            probability: alternative.probability,
          }))}
        />
      );
    case "choose":
      return (
        <IntentChoice
          candidates={[
            {
              name: state.intent.intent.name,
              probability: state.intent.probability,
              band: state.intent.band,
            },
            ...state.alternatives.map((alternative) => ({
              name: alternative.intent.name,
              probability: alternative.probability,
            })),
          ]}
        />
      );
    default:
      assertNever(state);
  }
}
