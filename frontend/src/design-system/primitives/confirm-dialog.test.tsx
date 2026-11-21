import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ConfirmDialog, type ConfirmDialogProps } from "@/design-system/primitives/confirm-dialog";
import { renderUi } from "@/test/render-app";

/**
 * Render the dialog with the texts of the admin design.
 *
 * @param overrides - The props that a test changes.
 * @returns The handlers, the user-event instance, and the function that closes the dialog.
 */
function renderDialog(overrides: Partial<ConfirmDialogProps> = {}) {
  const onConfirm = vi.fn();
  const onCancel = vi.fn();
  const { user, unmount } = renderUi(
    <ConfirmDialog
      isOpen
      text={{
        title: "Deactivate Minh Le?",
        description: "Minh Le will be signed out of every session.",
        confirmLabel: "Deactivate",
        pendingLabel: "Deactivating…",
      }}
      returnFocus={{ opener: document.body, fallbackId: "row" }}
      tone="danger"
      isPending={false}
      onConfirm={onConfirm}
      onCancel={onCancel}
      {...overrides}
    />,
  );
  return { onConfirm, onCancel, user, unmount };
}

/**
 * Render a row of a list: a stable element and the button that opens the dialog.
 *
 * @returns The two elements.
 */
function renderRow() {
  renderUi(
    <>
      <p id="row" tabIndex={-1}>
        Mai Nguyen
      </p>
      <button type="button">Make manager</button>
    </>,
  );
  return {
    row: screen.getByText("Mai Nguyen"),
    opener: screen.getByRole("button", { name: "Make manager" }),
  };
}

describe("ConfirmDialog, the focus when it closes (UI-30)", () => {
  it("returns the focus to the element that opened it", async () => {
    const { opener } = renderRow();
    const { unmount } = renderDialog({ returnFocus: { opener, fallbackId: "row" } });

    unmount();

    await waitFor(() => {
      expect(opener).toHaveFocus();
    });
  });

  it("moves the focus to the fallback when the change removed that element", async () => {
    const { row } = renderRow();
    const removedOpener = document.createElement("button");
    const { unmount } = renderDialog({
      returnFocus: { opener: removedOpener, fallbackId: "row" },
    });

    unmount();

    await waitFor(() => {
      expect(row).toHaveFocus();
    });
  });

  it("leaves the focus where the outcome of the dialog moved it", async () => {
    const { row, opener } = renderRow();
    const { unmount } = renderDialog({ returnFocus: { opener, fallbackId: "row" } });

    unmount();
    row.focus();
    // Radix returns the focus in a timer that the unmount started; this one runs after it.
    await new Promise((resolve) => {
      setTimeout(resolve, 0);
    });

    expect(row).toHaveFocus();
  });

  it("moves the focus to the fallback when the change disabled that element", async () => {
    const { row, opener } = renderRow();
    const { unmount } = renderDialog({ returnFocus: { opener, fallbackId: "row" } });
    opener.setAttribute("disabled", "");

    unmount();

    await waitFor(() => {
      expect(row).toHaveFocus();
    });
  });
});

describe("ConfirmDialog", () => {
  it("is a modal alert dialog named by its title and described by its text", () => {
    renderDialog();

    const dialog = screen.getByRole("alertdialog", { name: "Deactivate Minh Le?" });
    expect(dialog).toHaveAccessibleDescription("Minh Le will be signed out of every session.");
  });

  it("moves the focus into the dialog, on the least destructive action (UI-30)", () => {
    renderDialog();

    expect(screen.getByRole("button", { name: "Cancel" })).toHaveFocus();
  });

  it("confirms with the button that names the result", async () => {
    const { onConfirm, user } = renderDialog();

    await user.click(screen.getByRole("button", { name: "Deactivate" }));

    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("cancels with Cancel", async () => {
    const { onCancel, onConfirm, user } = renderDialog();

    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("cancels with Escape", async () => {
    const { onCancel, user } = renderDialog();

    await user.keyboard("{Escape}");

    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("ignores both buttons and says what it does while the change is sent", async () => {
    const { onCancel, onConfirm, user } = renderDialog({ isPending: true });

    await user.keyboard("{Escape}");
    await user.click(screen.getByRole("button", { name: "Deactivating…" }));

    expect(screen.getByRole("button", { name: "Deactivating…" })).toHaveAttribute(
      "aria-disabled",
      "true",
    );
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
    expect(onCancel).not.toHaveBeenCalled();
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("renders nothing while closed", () => {
    renderDialog({ isOpen: false });

    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  });

  it("uses the primary style for a change that is not dangerous", () => {
    renderDialog({
      tone: "default",
      text: {
        title: "Make Mai Nguyen a manager?",
        description: "Mai Nguyen will be signed out of every session.",
        confirmLabel: "Make manager",
        pendingLabel: "Making manager…",
      },
    });

    expect(screen.getByRole("button", { name: "Make manager" })).toBeEnabled();
  });
});
