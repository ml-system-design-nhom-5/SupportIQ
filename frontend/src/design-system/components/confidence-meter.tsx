/**
 * The confidence of a predicted intent (FR-01, UI-14): three bars, the band, and the percentage of
 * the probability that `backend` sent. The UI never computes the band. High and medium use neutral
 * bars and the `warning` role marks low only, so a high band never reads as "correct" (console UI
 * design, placement rule 5).
 */
import { cva } from "class-variance-authority";

import { formatPercent } from "@/design-system/format/number";
import { VisuallyHidden } from "@/design-system/primitives/visually-hidden";

const meterVariants = cva("inline-flex items-center gap-2 text-sm whitespace-nowrap", {
  variants: { band: { high: "text-text-muted", medium: "text-text-muted", low: "text-warning" } },
});

const barVariants = cva("block w-1 rounded-sm", {
  variants: {
    height: { short: "h-1", middle: "h-2", tall: "h-3" },
    fill: { empty: "bg-border", neutral: "bg-text-muted", warning: "bg-warning" },
  },
});

const bars = ["short", "middle", "tall"] as const;

const filledBarCountByBand: Readonly<Record<ConfidenceBandName, number>> = {
  high: 3,
  medium: 2,
  low: 1,
};

const labelByBand: Readonly<Record<ConfidenceBandName, string>> = {
  high: "High",
  medium: "Medium",
  low: "Low",
};

/** A band of `ConfidenceBand`; an unknown value is `low` (CON-22). */
export type ConfidenceBandName = "high" | "medium" | "low";

/** Props of {@link ConfidenceMeter}. */
export type ConfidenceMeterProps = {
  readonly band: ConfidenceBandName;
  /** The calibrated probability, from 0 to 1. */
  readonly probability: number;
};

/**
 * Render the confidence.
 *
 * @param props - The band and the probability.
 * @returns For example "High · 91%" after three bars.
 */
export function ConfidenceMeter({ band, probability }: ConfidenceMeterProps) {
  const filledBarCount = filledBarCountByBand[band];
  const fill = band === "low" ? "warning" : "neutral";
  return (
    <span className={meterVariants({ band })}>
      <span aria-hidden="true" className="inline-flex h-3 items-end gap-1">
        {bars.map((height, index) => (
          <span
            key={height}
            className={barVariants({ height, fill: index < filledBarCount ? fill : "empty" })}
          />
        ))}
      </span>
      <span>
        <VisuallyHidden>Confidence </VisuallyHidden>
        {labelByBand[band]} · {formatPercent(probability)}
      </span>
    </span>
  );
}
