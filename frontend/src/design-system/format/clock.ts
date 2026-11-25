/**
 * The clock of the UI (CODE-18, ARCH-31): components read the current time from it, so tests and
 * stories can fix it.
 */
import { createContext, use } from "react";

/** The real clock. */
export const systemClock: Clock = () => new Date();

/** Holds the clock; the real clock unless a provider fixes another one. */
export const ClockContext = createContext<Clock>(systemClock);

/** Returns the current time. */
export type Clock = () => Date;

/**
 * Read the current time from the nearest {@link ClockContext}.
 *
 * @returns The current time.
 */
export function useNow(): Date {
  return use(ClockContext)();
}
