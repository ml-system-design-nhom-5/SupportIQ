import { screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { EscalateDialog } from "@/features/console-tickets/components/escalate-dialog";
import type { EscalationErrors } from "@/features/console-tickets/model/escalation-form";
import type { FailureView } from "@/features/console-tickets/model/failure-view";
import { staffReasonCodeLabels } from "@/features/console-tickets/model/staff-reason-codes";
import { renderUi } from "@/test/render-app";

const TITLE = "Escalate ticket TCK-1042 to a manager?";

const GROUP_LABEL = "Why do you escalate this ticket?";

const NOTE_LABEL = "Note (required with Other)";

const REASONS_ERROR = "Choose at least one reason.";

const NOTE_ERROR = "Write a note for the reason Other.";

/** The state of the dialog that a test changes. */
type DialogState = {
  readonly errors?: EscalationErrors;
  readonly isPending?: boolean;
  readonly failure?: FailureView;
};

/**
 * Render the dialog with Missing case info chosen and an empty note.
 *
 * @param state - The errors, the pending state, and the failure of the test.
 * @returns The handlers and the user-event instance.
 */
function renderDialog({ errors, isPending = false, failure }: DialogState = {}) {
  const handlers = {
    onToggle: vi.fn(),
    onNoteChange: vi.fn(),
    onSubmit: vi.fn(),
    onCancel: vi.fn(),
  };
  const { user } = renderUi(
    <EscalateDialog
      ticketId="TCK-1042"
      returnFocus={{ opener: document.body, fallbackId: "escalate-ticket" }}
      form={{
        reasonCodes: new Set(["missing_case_info"]),
        note: "",
        ...(errors === undefined ? {} : { errors }),
        onToggle: handlers.onToggle,
        onNoteChange: handlers.onNoteChange,
      }}
      submission={{
        isPending,
        ...(failure === undefined ? {} : { failure }),
        onSubmit: handlers.onSubmit,
        onCancel: handlers.onCancel,
      }}
    />,
  );
  return { ...handlers, user };
}

describe("EscalateDialog (console UI design, Dialogs)", () => {
  it("is a dialog named by the ticket and described by what escalation does", () => {
    renderDialog();

    expect(screen.getByRole("dialog", { name: TITLE })).toHaveAccessibleDescription(
      "Choose at least one reason. The ticket becomes read-only for you.",
    );
  });

  it("shows the staff reason codes as toggle chips in the contract order (ADR-0006)", () => {
    renderDialog();

    const chips = within(screen.getByRole("group", { name: GROUP_LABEL })).getAllByRole("button");
    expect(chips.map((chip) => chip.textContent)).toEqual(Object.values(staffReasonCodeLabels));
    expect(screen.getByRole("button", { name: "Missing case info" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByRole("button", { name: "Other" })).toHaveAttribute("aria-pressed", "false");
  });

  it("passes the code of a chip that staff select", async () => {
    const { onToggle, user } = renderDialog();

    await user.click(screen.getByRole("button", { name: "Other" }));

    expect(onToggle).toHaveBeenCalledExactlyOnceWith("other");
  });

  it("labels the note and passes what staff type", async () => {
    const { onNoteChange, user } = renderDialog();

    await user.type(screen.getByRole("textbox", { name: NOTE_LABEL }), "N");

    expect(onNoteChange).toHaveBeenCalledExactlyOnceWith("N");
  });

  it("shows no error before a check", () => {
    renderDialog();

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: NOTE_LABEL })).not.toBeInvalid();
  });

  it("ties the error of the reasons to the group of chips", () => {
    renderDialog({ errors: { reasons: REASONS_ERROR } });

    const group = screen.getByRole("group", { name: GROUP_LABEL });
    expect(screen.getByRole("alert")).toHaveTextContent(REASONS_ERROR);
    expect(group).toHaveAccessibleDescription(REASONS_ERROR);
    expect(within(group).getByRole("alert")).toBeVisible();
  });

  it("ties the error of the note to the note field", () => {
    renderDialog({ errors: { note: NOTE_ERROR } });

    const note = screen.getByRole("textbox", { name: NOTE_LABEL });
    expect(note).toBeInvalid();
    expect(note).toHaveAccessibleDescription(NOTE_ERROR);
    expect(screen.getByRole("alert")).toHaveTextContent(NOTE_ERROR);
  });

  it("asks to escalate with Escalate ticket", async () => {
    const { onSubmit, onCancel, user } = renderDialog();

    await user.click(screen.getByRole("button", { name: "Escalate ticket" }));

    expect(onSubmit).toHaveBeenCalledOnce();
    expect(onCancel).not.toHaveBeenCalled();
  });

  it("cancels with Cancel", async () => {
    const { onSubmit, onCancel, user } = renderDialog();

    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(onCancel).toHaveBeenCalledOnce();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("ignores Escalate ticket, Cancel, and Escape while the escalation is sent", async () => {
    const { onSubmit, onCancel, user } = renderDialog({ isPending: true });

    await user.click(screen.getByRole("button", { name: "Escalate ticket" }));
    await user.keyboard("{Escape}");

    expect(screen.getByRole("button", { name: "Escalate ticket" })).toHaveAttribute(
      "aria-disabled",
      "true",
    );
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
    expect(onSubmit).not.toHaveBeenCalled();
    expect(onCancel).not.toHaveBeenCalled();
  });

  it("shows a failed escalation in the dialog, with its trace ID (UI-25)", () => {
    renderDialog({
      failure: {
        lead: "The ticket was not escalated.",
        message: "Something went wrong. Try again in a moment.",
        traceId: "319c0af7651916cd43dd8448eb211c80",
      },
    });

    const banner = within(screen.getByRole("dialog", { name: TITLE })).getByRole("alert");
    expect(banner).toHaveTextContent("The ticket was not escalated.");
    expect(banner).toHaveTextContent("Something went wrong. Try again in a moment.");
    expect(banner).toHaveTextContent("319c0af7651916cd43dd8448eb211c80");
  });
});
