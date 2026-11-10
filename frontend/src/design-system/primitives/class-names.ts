/**
 * Join the class names of a design-system component, letting later classes win (shadcn/ui
 * convention). Only design-system components use it; feature code never passes classes.
 */
import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Join class names and drop the ones that a later class overrides.
 *
 * @param inputs - Class names, conditional class objects, or arrays of them.
 * @returns One class string.
 */
export function cn(...inputs: readonly ClassValue[]): string {
  return twMerge(clsx(inputs));
}
