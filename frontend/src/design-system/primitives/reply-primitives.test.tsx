import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ConfirmDialog } from "@/design-system/primitives/confirm-dialog";
import { renderUi } from "@/test/render-app";

describe("ConfirmDialog, the cancel label", () => {
  it("names the button that keeps the change from happening, and cancels with it", async () => {
    const onCancel = vi.fn();
    const { user } = renderUi(
      <ConfirmDialog
        isOpen
        text={{
          title: "Send this reply to Linh Tran?",
          description: "A sent reply cannot be changed.",
          confirmLabel: "Send reply",
          pendingLabel: "Sending…",
          cancelLabel: "Keep editing",
        }}
        returnFocus={{ opener: document.body, fallbackId: "send-reply" }}
        isPending={false}
        onConfirm={vi.fn()}
        onCancel={onCancel}
      />,
    );

    const keepEditing = screen.getByRole("button", { name: "Keep editing" });
    expect(keepEditing).toHaveFocus();
    await user.click(keepEditing);

    expect(onCancel).toHaveBeenCalledOnce();
  });
});
