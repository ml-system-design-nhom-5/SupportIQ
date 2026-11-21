/**
 * The choice of an intent after an abstention for low confidence (ESC-01, UI-42; console UI
 * design, state-choose-intent.png): the top three candidates with their confidence, each with
 * "Use this intent" when staff may choose one, and no draft until staff choose. The list is AI
 * output, so it carries the `ai` marker (UI-13).
 */
import { Sparkles } from "lucide-react";

import { presentationByAiReasonCode } from "@/design-system/components/ai-presentations";
import {
  type ConfidenceBandName,
  ConfidenceMeter,
} from "@/design-system/components/confidence-meter";
import { StatusBadge } from "@/design-system/components/status-badge";
import { formatPercent } from "@/design-system/format/number";
import { Button } from "@/design-system/primitives/button";
import { Panel } from "@/design-system/primitives/panel";
import { PanelHeader } from "@/design-system/primitives/panel-header";

/** One candidate intent. */
export type IntentChoiceCandidate<Value extends string = string> = {
  readonly name: string;
  readonly probability: number;
  /** The band of the predicted intent; absent for the further candidates. */
  readonly band?: ConfidenceBandName;
  /** What {@link IntentUse.onUseIntent} receives; absent for an intent that staff cannot choose. */
  readonly value?: Value;
};

/** How staff use an intent that the intent strip or the choice offers (UI-22, UI-42). */
export type IntentUse<Value extends string = string> = {
  /**
   * True while a correction is sending. The buttons then read as disabled and ignore activation,
   * so one correction is sent at a time, and they keep the focus (UI-30).
   */
  readonly isSending: boolean;
  readonly onUseIntent: (value: Value) => void;
};

/** Props of {@link IntentChoice}. */
export type IntentChoiceProps<Value extends string = string> = {
  /** The predicted intent first, then the next two candidates. */
  readonly candidates: readonly IntentChoiceCandidate<Value>[];
  /** Adds "Use this intent" to each candidate; absent when staff may not choose an intent. */
  readonly use?: IntentUse<Value>;
};

/**
 * Render the candidates.
 *
 * @param props - The candidates, and how staff use one when they may.
 * @returns The panel with the list.
 */
export function IntentChoice<Value extends string = string>({
  candidates,
  use,
}: IntentChoiceProps<Value>) {
  return (
    <Panel as="section" label="Choose an intent" tone="ai" density="compact">
      <PanelHeader
        icon={Sparkles}
        level={2}
        title="Choose an intent"
        trailing={<StatusBadge presentation={presentationByAiReasonCode.low_confidence} />}
      />
      <ul className="flex flex-col px-4 py-2 text-sm">
        {candidates.map((candidate) => (
          <li
            key={candidate.name}
            className="flex items-center gap-2 border-t border-border py-2 first:border-t-0"
          >
            <span className="flex-1 font-medium text-text">{candidate.name}</span>
            {candidate.band === undefined ? (
              <span className="text-text-muted">{formatPercent(candidate.probability)}</span>
            ) : (
              <ConfidenceMeter band={candidate.band} probability={candidate.probability} />
            )}
            {use === undefined || candidate.value === undefined ? null : (
              <UseIntentButton name={candidate.name} value={candidate.value} use={use} />
            )}
          </li>
        ))}
      </ul>
    </Panel>
  );
}

/** Props of {@link UseIntentButton}. */
type UseIntentButtonProps<Value extends string> = {
  readonly name: string;
  readonly value: Value;
  readonly use: IntentUse<Value>;
};

/**
 * Render "Use this intent" for one candidate. The accessible name adds the intent, so each button
 * has its own name, such as "Use this intent: Request refund". It starts with the visible text
 * (WCAG 2.5.3), and an `aria-label` gives every browser the same name.
 *
 * @param props - The name and the value of the intent, and how staff use it.
 * @returns The button.
 */
function UseIntentButton<Value extends string>({ name, value, use }: UseIntentButtonProps<Value>) {
  return (
    <Button
      size="sm"
      aria-label={`Use this intent: ${name}`}
      isPending={use.isSending}
      onClick={() => {
        use.onUseIntent(value);
      }}
    >
      Use this intent
    </Button>
  );
}
