/**
 * The intent strip (FR-01, UI-22; console UI design, Workspace regions and placement rule 7): the
 * intent that the pipeline used, directly under the customer message, with its confidence and
 * "Predicted", or "Chosen by staff" after a correction, and the next two candidates of the model.
 * When staff may correct the intent, "Not right? Use:" turns the candidates into buttons and adds
 * Other intent, a menu of the other intents on Radix DropdownMenu (UI-31), so a correction takes
 * one interaction from where the intent is shown. The strip is AI output, so it carries the `ai`
 * marker (UI-13).
 */
import * as DropdownMenuPrimitive from "@radix-ui/react-dropdown-menu";
import { ChevronRight, Sparkles } from "lucide-react";

import {
  type ConfidenceBandName,
  ConfidenceMeter,
} from "@/design-system/components/confidence-meter";
import type { IntentUse } from "@/design-system/components/intent-choice";
import { Tag } from "@/design-system/components/tag";
import { formatPercent } from "@/design-system/format/number";
import { Button } from "@/design-system/primitives/button";
import { Icon } from "@/design-system/primitives/icon";
import { MENU_ITEM_CLASSES } from "@/design-system/primitives/menu-item";
import { Panel } from "@/design-system/primitives/panel";
import { VisuallyHidden } from "@/design-system/primitives/visually-hidden";

/** A further candidate of the model. */
export type IntentStripCandidate<Value extends string = string> = {
  readonly name: string;
  readonly probability: number;
  /** What {@link IntentUse.onUseIntent} receives; absent for an intent that staff cannot choose. */
  readonly value?: Value;
};

/** The confidence of a predicted intent. */
export type IntentConfidence = {
  readonly band: ConfidenceBandName;
  readonly probability: number;
};

/** An intent of the Other intent menu. */
export type IntentOption<Value extends string = string> = {
  readonly value: Value;
  readonly name: string;
};

/** How staff correct the intent from the strip (UI-22). */
export type IntentCorrection<Value extends string = string> = IntentUse<Value> & {
  /** The intents that Other intent lists, in the order of the menu. */
  readonly otherIntents: readonly IntentOption<Value>[];
};

/** Props of {@link IntentStrip}. */
export type IntentStripProps<Value extends string = string> = {
  /** The name of the intent, for example "Refund status". */
  readonly intentName: string;
  /** The confidence of a predicted intent; absent for an intent that staff chose. */
  readonly confidence?: IntentConfidence;
  /** The next candidates of the model; empty after a correction. */
  readonly candidates: readonly IntentStripCandidate<Value>[];
  /** Turns the candidates into buttons and adds Other intent; absent for a read-only strip. */
  readonly correction?: IntentCorrection<Value>;
};

/**
 * Render the intent strip.
 *
 * @param props - The intent, its confidence, the next candidates, and the correction when staff
 *   may correct the intent.
 * @returns The strip in an `ai` panel.
 */
export function IntentStrip<Value extends string = string>({
  intentName,
  confidence,
  candidates,
  correction,
}: IntentStripProps<Value>) {
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
        {correction === undefined ? (
          <NextCandidates candidates={candidates} />
        ) : (
          <IntentCorrectionControls candidates={candidates} correction={correction} />
        )}
      </div>
    </Panel>
  );
}

/**
 * Render the next candidates of a read-only strip.
 *
 * @param props - The candidates.
 * @returns "Next candidates:" with each candidate, or nothing without candidates.
 */
function NextCandidates({ candidates }: { readonly candidates: readonly IntentStripCandidate[] }) {
  if (candidates.length === 0) {
    return null;
  }
  return (
    <p className="flex flex-wrap items-center gap-2 text-text-muted">
      Next candidates:
      {candidates.map((candidate) => (
        <CandidateChip key={candidate.name} candidate={candidate} />
      ))}
    </p>
  );
}

/** Props of {@link IntentCorrectionControls}. */
type IntentCorrectionControlsProps<Value extends string> = {
  readonly candidates: readonly IntentStripCandidate<Value>[];
  readonly correction: IntentCorrection<Value>;
};

/**
 * Render "Not right? Use:" with a button for each candidate that staff can choose, and Other
 * intent (console UI design, workspace-staff.png).
 *
 * @param props - The candidates and the correction.
 * @returns The controls.
 */
function IntentCorrectionControls<Value extends string>({
  candidates,
  correction,
}: IntentCorrectionControlsProps<Value>) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-text-muted">Not right? Use:</span>
      {candidates.map((candidate) =>
        candidate.value === undefined ? (
          <CandidateChip key={candidate.name} candidate={candidate} />
        ) : (
          <CandidateButton
            key={candidate.name}
            candidate={candidate}
            value={candidate.value}
            use={correction}
          />
        ),
      )}
      <OtherIntentMenu correction={correction} />
    </div>
  );
}

/**
 * Render a candidate that staff cannot choose, or any candidate of a read-only strip.
 *
 * @param props - The candidate.
 * @returns The name and the percentage in an outlined chip.
 */
function CandidateChip({ candidate }: { readonly candidate: IntentStripCandidate }) {
  return (
    <span className="rounded-md border border-border px-2 py-1 text-text">
      {candidate.name}{" "}
      <span className="text-text-muted">{formatPercent(candidate.probability)}</span>
    </span>
  );
}

/** Props of {@link CandidateButton}. */
type CandidateButtonProps<Value extends string> = {
  readonly candidate: IntentStripCandidate<Value>;
  readonly value: Value;
  readonly use: IntentUse<Value>;
};

/**
 * Render a candidate as the button that uses it. The accessible name starts with "Use", such as
 * "Use Request refund 7%", so it differs from the item of the same intent in Other intent.
 *
 * @param props - The candidate, its value, and how staff use it.
 * @returns The button.
 */
function CandidateButton<Value extends string>({
  candidate,
  value,
  use,
}: CandidateButtonProps<Value>) {
  return (
    <Button
      size="sm"
      isPending={use.isSending}
      onClick={() => {
        use.onUseIntent(value);
      }}
    >
      <span>
        <VisuallyHidden>Use</VisuallyHidden> {candidate.name}{" "}
        <span className="text-text-muted">{formatPercent(candidate.probability)}</span>
      </span>
    </Button>
  );
}

/**
 * Render Other intent: a button that opens the menu of the other intents. Enter, Space, or the
 * down arrow opens it, the arrow keys and typing move between the intents, Escape closes it, and
 * the focus returns to the button. The menu opens beside the button and stays within the height
 * of the window, where its list scrolls. Its items are disabled while a correction is sending.
 *
 * @param props - The correction.
 * @returns The button; the menu opens in a portal.
 */
function OtherIntentMenu<Value extends string>({
  correction,
}: {
  readonly correction: IntentCorrection<Value>;
}) {
  return (
    // Not modal, as in the WAI-ARIA menu button pattern (axe aria-hidden-focus, UI-32).
    <DropdownMenuPrimitive.Root modal={false}>
      <DropdownMenuPrimitive.Trigger asChild>
        <Button size="sm" variant="ghost">
          Other intent
          <Icon icon={ChevronRight} />
        </Button>
      </DropdownMenuPrimitive.Trigger>
      <DropdownMenuPrimitive.Portal>
        <DropdownMenuPrimitive.Content
          side="right"
          align="start"
          sideOffset={4}
          className="z-20 flex max-h-screen min-w-menu flex-col overflow-y-auto rounded-md border border-border bg-surface-raised p-1 text-sm shadow-md"
        >
          {correction.otherIntents.map((option) => (
            <DropdownMenuPrimitive.Item
              key={option.value}
              className={MENU_ITEM_CLASSES}
              disabled={correction.isSending}
              onSelect={() => {
                correction.onUseIntent(option.value);
              }}
            >
              {option.name}
            </DropdownMenuPrimitive.Item>
          ))}
        </DropdownMenuPrimitive.Content>
      </DropdownMenuPrimitive.Portal>
    </DropdownMenuPrimitive.Root>
  );
}
