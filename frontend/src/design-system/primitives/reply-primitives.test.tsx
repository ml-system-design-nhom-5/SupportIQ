import { screen } from "@testing-library/react";
import { CircleArrowUp, Send, Sparkles } from "lucide-react";
import { describe, expect, it, vi } from "vitest";

import { ConfirmDialog, type ConfirmDialogText } from "@/design-system/primitives/confirm-dialog";
import { FormDialog, type FormDialogText } from "@/design-system/primitives/form-dialog";
import { Panel } from "@/design-system/primitives/panel";
import { PanelHeader } from "@/design-system/primitives/panel-header";
import { renderUi } from "@/test/render-app";

const DESCRIPTION = "A sent reply cannot be changed.";

/** The ID of the reply heading in these tests. */
const HEADING_ID = "reply-heading";

/** The class of the least height of a `fill` panel. */
const REPLY_PANEL_HEIGHT_CLASS = "min-h-reply-panel";

/**
 * Render an open Send reply confirmation.
 *
 * @param overrides - The texts that a test changes.
 * @returns The cancel handler and the user-event instance.
 */
function renderConfirmDialog(overrides: Partial<ConfirmDialogText> = {}) {
  const onCancel = vi.fn();
  const { user } = renderUi(
    <ConfirmDialog
      isOpen
      text={{
        title: "Send this reply to Linh Tran?",
        description: DESCRIPTION,
        confirmLabel: "Send reply",
        pendingLabel: "Sending…",
        ...overrides,
      }}
      returnFocus={{ opener: document.body, fallbackId: "send-reply" }}
      isPending={false}
      onConfirm={vi.fn()}
      onCancel={onCancel}
    />,
  );
  return { onCancel, user };
}

/** The description of the Escalate ticket form in these tests. */
const FORM_DESCRIPTION = "Choose at least one reason. The ticket becomes read-only for you.";

/**
 * Render an open Escalate ticket form.
 *
 * @param overrides - The texts that a test changes.
 */
function renderFormDialog(overrides: Partial<FormDialogText> = {}) {
  renderUi(
    <FormDialog
      text={{
        title: "Escalate ticket TCK-1042 to a manager?",
        description: FORM_DESCRIPTION,
        submitLabel: "Escalate ticket",
        ...overrides,
      }}
      returnFocus={{ opener: document.body, fallbackId: "escalate-ticket" }}
      isPending={false}
      onSubmit={vi.fn()}
      onCancel={vi.fn()}
    >
      Fields
    </FormDialog>,
  );
}

describe("ConfirmDialog, the cancel label", () => {
  it("names the button that keeps the change from happening, and cancels with it", async () => {
    const { onCancel, user } = renderConfirmDialog({ cancelLabel: "Keep editing" });

    const keepEditing = screen.getByRole("button", { name: "Keep editing" });
    expect(keepEditing).toHaveFocus();
    await user.click(keepEditing);

    expect(onCancel).toHaveBeenCalledOnce();
  });
});

describe("ConfirmDialog, the console texts", () => {
  it("shows the confirm icon on the confirm button, hidden from assistive technology", () => {
    renderConfirmDialog({ confirmIcon: Send });

    expect(screen.getByRole("button", { name: "Send reply" }).querySelector("svg")).toHaveAttribute(
      "aria-hidden",
      "true",
    );
  });

  it("shows no icon on the confirm button without a confirm icon", () => {
    renderConfirmDialog();

    expect(screen.getByRole("button", { name: "Send reply" }).querySelector("svg")).toBeNull();
  });

  it.each([
    { tone: "muted", textClass: "text-text-muted" },
    { tone: "default", textClass: "text-text" },
  ] as const)("gives a $tone description the class $textClass", ({ tone, textClass }) => {
    renderConfirmDialog({ descriptionTone: tone });

    expect(screen.getByText(DESCRIPTION)).toHaveClass(textClass);
  });
});

describe("FormDialog, the console texts", () => {
  it("shows the submit icon on the submit button, hidden from assistive technology", () => {
    renderFormDialog({ submitIcon: CircleArrowUp });

    expect(
      screen.getByRole("button", { name: "Escalate ticket" }).querySelector("svg"),
    ).toHaveAttribute("aria-hidden", "true");
  });

  it("shows no icon on the submit button without a submit icon", () => {
    renderFormDialog();

    expect(screen.getByRole("button", { name: "Escalate ticket" }).querySelector("svg")).toBeNull();
  });

  it.each([
    { tone: "muted", textClass: "text-text-muted" },
    { tone: "default", textClass: "text-text" },
  ] as const)("gives a $tone description the class $textClass", ({ tone, textClass }) => {
    renderFormDialog({ descriptionTone: tone });

    expect(screen.getByText(FORM_DESCRIPTION)).toHaveClass(textClass);
    expect(screen.getByRole("dialog")).toHaveAccessibleDescription(FORM_DESCRIPTION);
  });

  it("gives the description the text role by default", () => {
    renderFormDialog();

    expect(screen.getByText(FORM_DESCRIPTION)).toHaveClass("text-text");
  });
});

describe("PanelHeader, the focus target", () => {
  it("lets a script move the focus to the heading by its ID, but not Tab (UI-30)", () => {
    renderUi(
      <Panel>
        <PanelHeader icon={Sparkles} level={2} title="AI draft" focusTargetId={HEADING_ID} />
      </Panel>,
    );

    const heading = screen.getByRole("heading", { name: "AI draft" });
    document.getElementById(HEADING_ID)?.focus();

    expect(heading).toHaveFocus();
    expect(heading).toHaveAttribute("tabindex", "-1");
  });

  it("keeps a heading without a focus target out of the focus order", () => {
    renderUi(
      <Panel>
        <PanelHeader icon={Sparkles} level={2} title="AI draft" />
      </Panel>,
    );

    expect(screen.getByRole("heading", { name: "AI draft" })).not.toHaveAttribute("tabindex");
  });
});

describe("Panel height", () => {
  it("gives a fill panel the least height of the reply panel", () => {
    renderUi(
      <Panel as="section" label="AI draft" height="fill">
        Draft
      </Panel>,
    );

    expect(screen.getByRole("region", { name: "AI draft" })).toHaveClass(REPLY_PANEL_HEIGHT_CLASS);
  });

  it("fits a panel to its content by default", () => {
    renderUi(
      <Panel as="section" label="AI draft">
        Draft
      </Panel>,
    );

    expect(screen.getByRole("region", { name: "AI draft" })).not.toHaveClass(
      REPLY_PANEL_HEIGHT_CLASS,
    );
  });
});
