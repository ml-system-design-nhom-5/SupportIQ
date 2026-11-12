/**
 * Clipboard answers for stories: the browser of the story tests grants no clipboard permission, so
 * a story chooses what the clipboard does and restores it afterwards.
 */
import { spyOn } from "storybook/test";

/**
 * Make the clipboard accept every write, until the returned function restores it.
 *
 * @returns The cleanup of the story.
 */
export function acceptClipboardWrites(): () => void {
  const writeText = spyOn(navigator.clipboard, "writeText").mockResolvedValue();
  return () => {
    writeText.mockRestore();
  };
}

/**
 * Make the clipboard refuse every write, as a browser without permission does, until the returned
 * function restores it.
 *
 * @returns The cleanup of the story.
 */
export function refuseClipboardWrites(): () => void {
  const writeText = spyOn(navigator.clipboard, "writeText").mockRejectedValue(
    new DOMException("Denied", "NotAllowedError"),
  );
  return () => {
    writeText.mockRestore();
  };
}
