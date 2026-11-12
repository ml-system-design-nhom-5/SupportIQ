/**
 * The choice of an intent after an abstention for low confidence (ESC-01, UI-42; console UI
 * design, state-choose-intent.png): the top three candidates with their confidence, and no draft
 * until staff choose. The list is AI output, so it carries the `ai` marker (UI-13).
 */
import { Sparkles } from "lucide-react";

import { presentationByAiReasonCode } from "@/design-system/components/ai-presentations";
import {
  type ConfidenceBandName,
  ConfidenceMeter,
} from "@/design-system/components/confidence-meter";
import { StatusBadge } from "@/design-system/components/status-badge";
import { formatPercent } from "@/design-system/format/number";
import { Panel } from "@/design-system/primitives/panel";
import { PanelHeader } from "@/design-system/primitives/panel-header";

/** One candidate intent. */
export type IntentChoiceCandidate = {
  readonly name: string;
  readonly probability: number;
  /** The band of the predicted intent; absent for the further candidates. */
  readonly band?: ConfidenceBandName;
};

/** Props of {@link IntentChoice}. */
export type IntentChoiceProps = {
  /** The predicted intent first, then the next two candidates. */
  readonly candidates: readonly IntentChoiceCandidate[];
};

/**
 * Render the candidates.
 *
 * @param props - The candidates.
 * @returns The panel with the list.
 */
export function IntentChoice({ candidates }: IntentChoiceProps) {
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
          </li>
        ))}
      </ul>
    </Panel>
  );
}
