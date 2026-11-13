/**
 * The actions of a draft on the left of the action bar (console UI design, Actions): Edit draft or
 * Discard edits, and Reject draft. They need no request. A rejected draft has none. While no draft
 * is ready, the AI still works, staff choose an intent first, or the ticket is closed, and both stay
 * disabled.
 */
import { Pencil, X } from "lucide-react";

import { Button } from "@/design-system";
import type { DraftMode } from "@/features/console-tickets/model/reply-composer";

/** What the actions do. */
type DraftModeHandlers = {
  readonly onEdit: () => void;
  readonly onDiscard: () => void;
  readonly onReject: () => void;
};

/** Props of {@link DraftModeActions}. */
type DraftModeActionsProps = {
  /** What staff do with the draft. */
  readonly mode: DraftMode;
  /** True when the draft is ready and `backend` allows a reply or a proposal. */
  readonly canChange: boolean;
  /** Absent while no draft is ready. */
  readonly handlers?: DraftModeHandlers;
};

/** The first action of each mode with actions: Edit draft, or Discard edits for text in the editor. */
const firstActionByMode: Readonly<Record<Exclude<DraftMode, "rejecting">, "edit" | "discard">> = {
  viewing: "edit",
  editing: "discard",
  keeping: "discard",
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
      {firstActionByMode[mode] === "edit" ? (
        <Button leadingIcon={Pencil} disabled={!isEnabled} onClick={handlers?.onEdit}>
          Edit draft
        </Button>
      ) : (
        <Button leadingIcon={Pencil} onClick={handlers?.onDiscard}>
          Discard edits
        </Button>
      )}
      <Button leadingIcon={X} disabled={!isEnabled} onClick={handlers?.onReject}>
        Reject draft
      </Button>
    </>
  );
}
