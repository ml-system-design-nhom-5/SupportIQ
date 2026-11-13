/**
 * The actions of a draft on the left of the action bar (console UI design, Actions): Edit draft or
 * Discard edits, and Reject draft. They need no request. A rejected draft has none. While no draft
 * is ready, the AI still works or staff choose an intent first, and both stay disabled.
 */
import { Pencil, X } from "lucide-react";

import { Button } from "@/design-system";
import type { ComposerMode } from "@/features/console-tickets/model/reply-request";

/** What the actions do. */
export type DraftModeHandlers = {
  readonly onEdit: () => void;
  readonly onDiscard: () => void;
  readonly onReject: () => void;
};

/** Props of {@link DraftModeActions}. */
type DraftModeActionsProps = {
  /** What staff do with the draft. */
  readonly mode: ComposerMode;
  /** True when the draft is ready and `backend` allows a reply or a proposal. */
  readonly canChange: boolean;
  /** Absent while no draft is ready. */
  readonly handlers?: DraftModeHandlers;
};

/**
 * Render the actions of the draft.
 *
 * @param props - The mode, whether the draft can change, and the handlers.
 * @returns The buttons, or nothing after a rejection.
 */
export function DraftModeActions({ mode, canChange, handlers }: DraftModeActionsProps) {
  if (mode === "rejecting") {
    return null;
  }
  const isEnabled = canChange && handlers !== undefined;
  return (
    <>
      {mode === "editing" ? (
        <Button leadingIcon={Pencil} onClick={handlers?.onDiscard}>
          Discard edits
        </Button>
      ) : (
        <Button leadingIcon={Pencil} disabled={!isEnabled} onClick={handlers?.onEdit}>
          Edit draft
        </Button>
      )}
      <Button leadingIcon={X} disabled={!isEnabled} onClick={handlers?.onReject}>
        Reject draft
      </Button>
    </>
  );
}
