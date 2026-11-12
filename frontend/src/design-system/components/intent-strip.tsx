/**
 * The intent strip (FR-01, UI-22; console UI design, Workspace regions and placement rule 7): the
 * intent that the pipeline used, directly under the customer message, with its confidence and
 * "Predicted", or "Chosen by staff" after a correction, and the next two candidates of the model.
 * The strip is AI output, so it carries the `ai` marker (UI-13).
 */
import { Sparkles } from "lucide-react";

import {
  type ConfidenceBandName,
  ConfidenceMeter,
} from "@/design-system/components/confidence-meter";
import { Tag } from "@/design-system/components/tag";
import { formatPercent } from "@/design-system/format/number";
import { Icon } from "@/design-system/primitives/icon";
import { Panel } from "@/design-system/primitives/panel";

/** A further candidate of the model. */
export type IntentStripCandidate = {
  readonly name: string;
  readonly probability: number;
};

/** The confidence of a predicted intent. */
export type IntentConfidence = {
  readonly band: ConfidenceBandName;
  readonly probability: number;
};

/** Props of {@link IntentStrip}. */
export type IntentStripProps = {
  /** The name of the intent, for example "Refund status". */
  readonly intentName: string;
  /** The confidence of a predicted intent; absent for an intent that staff chose. */
  readonly confidence?: IntentConfidence;
  /** The next candidates of the model; empty after a correction. */
  readonly candidates: readonly IntentStripCandidate[];
};

/**
 * Render the intent strip.
 *
 * @param props - The intent, its confidence, and the next candidates.
 * @returns The strip in an `ai` panel.
 */
export function IntentStrip({ intentName, confidence, candidates }: IntentStripProps) {
  return (
    <Panel as="section" label="Intent" tone="ai" density="compact">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3 text-sm">
        <h2 className="flex items-center gap-2 font-semibold text-text">
          <Icon icon={Sparkles} tone="ai" />
          Intent
        </h2>
        <p className="flex flex-wrap items-center gap-2">
          <span className="text-base font-semibold text-text">{intentName}</span>
          {confidence === undefined ? null : (
            <ConfidenceMeter band={confidence.band} probability={confidence.probability} />
          )}
          {confidence === undefined ? (
            <Tag tone="neutral">Chosen by staff</Tag>
          ) : (
            <Tag tone="ai">Predicted</Tag>
          )}
        </p>
        {candidates.length === 0 ? null : (
          <p className="flex flex-wrap items-center gap-2 text-text-muted">
            Next candidates:
            {candidates.map((candidate) => (
              <span
                key={candidate.name}
                className="rounded-md border border-border px-2 py-1 text-text"
              >
                {candidate.name}{" "}
                <span className="text-text-muted">{formatPercent(candidate.probability)}</span>
              </span>
            ))}
          </p>
        )}
      </div>
    </Panel>
  );
}
