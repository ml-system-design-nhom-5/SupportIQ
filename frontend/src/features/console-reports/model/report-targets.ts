/**
 * The targets of the report figures, in one place (UI-44): the text that the requirements give
 * for a figure, or "No target". The UI shows a target next to its figure and never compares the
 * figure with it.
 */

/** NFR-08: end-to-end latency p50 of at most 4 s (a team target). */
export const LATENCY_P50_TARGET_TEXT = "At most 4 s";

/** NFR-08: end-to-end latency p95 of at most 12 s. */
export const LATENCY_P95_TARGET_TEXT = "At most 12 s";

/**
 * NFR-11: a handling time at least 20% shorter than the manual process (a team target). The
 * requirements measure it by comparing both processes on the same requests, not from these two
 * medians, so the page only states the target.
 */
export const ASSISTED_HANDLING_TIME_TARGET_TEXT = "At least 20% shorter than manual";

/** Every figure for which the requirements give no target. */
export const NO_TARGET_TEXT = "No target";
