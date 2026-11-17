/**
 * Move the focus after a staff action replaced the element that had it (UI-30, WCAG 2.4.3): Send
 * reply leaves the reply sent, Try AI again leaves the draft generating, and an intent correction
 * leaves the strip with the new intent. The element that should take the focus often renders only
 * after the answer of `backend`, so a request waits until an element with its ID is in the page.
 * Nothing moves the focus without a request, so opening a ticket keeps the focus where it was.
 */
import { useEffect, useRef } from "react";

/**
 * Keep one request to move the focus.
 *
 * @returns The function that asks for the focus on the element with an ID; a later request
 *   replaces an earlier one.
 */
export function useFocusRequest(): (targetId: string) => void {
  const targetIdRef = useRef<string | undefined>(undefined);
  // Runs after every render, because the target can appear in any of them.
  useEffect(() => {
    const targetId = targetIdRef.current;
    const target = targetId === undefined ? null : document.getElementById(targetId);
    if (target !== null) {
      targetIdRef.current = undefined;
      target.focus();
    }
  });
  return (targetId) => {
    targetIdRef.current = targetId;
  };
}
