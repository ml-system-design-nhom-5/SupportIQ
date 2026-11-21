/**
 * The keyboard focus style of every interactive element (UI-30): a 2 px outline in the
 * `focus-ring` role, outside the element.
 */
import { cn } from "@/design-system/primitives/class-names";

/** The focus classes, defined once for every interactive primitive (CODE-48). */
export const FOCUS_RING_CLASSES = cn(
  "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus-ring",
);
