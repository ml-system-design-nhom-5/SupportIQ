import { screen } from "@testing-library/react";
import { Clock, Send, X } from "lucide-react";
import { describe, expect, it, vi } from "vitest";

import { ActionBar, type ActionMenuItem } from "@/design-system/components/action-bar";
import { DraftText } from "@/design-system/components/draft-text";
import { MarkedText } from "@/design-system/components/marked-text";
import { ReplyEditor, type ReplyEditorProps } from "@/design-system/components/reply-editor";
import { ReplyPreview } from "@/design-system/components/reply-preview";
import { ToggleChipGroup } from "@/design-system/components/toggle-chip-group";
import { WarningList } from "@/design-system/components/warning-list";
import { Button } from "@/design-system/primitives/button";
import { renderUi } from "@/test/render-app";

const SOURCES_HINT = "Edited text is not checked against the sources.";

/**
 * Build the Submit for approval item of the More menu.
 *
 * @param overrides - The fields that a test changes.
 * @returns The item, with a mock handler.
 */
function buildSubmitItem(overrides: Partial<ActionMenuItem> = {}): ActionMenuItem {
  return {
    icon: Clock,
    label: "Submit for approval",
    description: "A manager sends the reply",
    onSelect: vi.fn(),
    ...overrides,
  };
}

/**
 * Render an action bar with Escalate ticket and Send reply.
 *
 * @param moreItems - The items of the More menu.
 * @returns The user-event instance.
 */
function renderActionBar(moreItems: readonly ActionMenuItem[]) {
  return renderUi(
    <ActionBar
      reason="Acknowledge 1 warning to send the reply."
      actions={<Button>Escalate ticket</Button>}
      moreItems={moreItems}
      primaryAction={
        <Button variant="primary" leadingIcon={Send} disabled>
          Send reply
        </Button>
      }
    />,
  );
}

/**
 * Render a reply editor with an empty text.
 *
 * @param overrides - The props that a test changes.
 * @returns The change handler and the user-event instance.
 */
function renderEditor(overrides: Partial<ReplyEditorProps> = {}) {
  const onChange = vi.fn();
  const { user } = renderUi(
    <ReplyEditor
      label="Reply to the customer"
      value=""
      onChange={onChange}
      markedParts={[]}
      placeholder="Write the reply to the customer"
      {...overrides}
    />,
  );
  return { onChange, user, editor: screen.getByRole("textbox", { name: "Reply to the customer" }) };
}

describe("ActionBar", () => {
  it("says above the buttons why an action is disabled (UI-16)", () => {
    renderActionBar([buildSubmitItem()]);

    expect(screen.getByText("Acknowledge 1 warning to send the reply.")).toBeVisible();
    expect(screen.getByRole("button", { name: "Send reply" })).toBeDisabled();
  });

  it("runs the More item that staff choose, named by its label and its second line", async () => {
    const item = buildSubmitItem();
    const { user } = renderActionBar([item]);

    await user.click(screen.getByRole("button", { name: "More actions" }));
    await user.click(
      await screen.findByRole("menuitem", {
        name: "Submit for approval A manager sends the reply",
      }),
    );

    expect(item.onSelect).toHaveBeenCalledOnce();
  });

  it("names an item without a second line by its label", async () => {
    const { user } = renderActionBar([{ icon: X, label: "Discard edits", onSelect: vi.fn() }]);

    await user.click(screen.getByRole("button", { name: "More actions" }));

    expect(await screen.findByRole("menuitem", { name: "Discard edits" })).toBeVisible();
  });

  it("never runs a disabled More item", async () => {
    const item = buildSubmitItem({ isDisabled: true });
    const { user } = renderActionBar([
      item,
      { icon: X, label: "Discard edits", onSelect: vi.fn() },
    ]);

    await user.click(screen.getByRole("button", { name: "More actions" }));
    const menuItem = await screen.findByRole("menuitem", { name: /^Submit for approval/ });
    await user.click(menuItem);

    expect(menuItem).toHaveAttribute("aria-disabled", "true");
    expect(item.onSelect).not.toHaveBeenCalled();
  });

  it("disables More when every item is disabled", () => {
    renderActionBar([buildSubmitItem({ isDisabled: true })]);

    expect(screen.getByRole("button", { name: "More actions" })).toBeDisabled();
  });

  it("has no More button without items", () => {
    renderActionBar([]);

    expect(screen.queryByRole("button", { name: "More actions" })).not.toBeInTheDocument();
  });
});

describe("WarningList acknowledgement (UI-18)", () => {
  const warnings = [
    { warningId: "w1", title: "Missing information", description: "Check it." },
    { warningId: "w2", title: "Source review overdue", description: "Check it applies." },
  ];

  it("shows no checkbox without the acknowledgement props", () => {
    renderUi(<WarningList warnings={warnings} />);

    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });

  it("names each checkbox after its warning and checks the acknowledged ones", () => {
    renderUi(
      <WarningList
        warnings={warnings}
        acknowledgedIds={new Set(["w1"])}
        onAcknowledgedChange={vi.fn()}
      />,
    );

    expect(
      screen.getByRole("checkbox", { name: "I have checked this warning: Missing information" }),
    ).toBeChecked();
    expect(
      screen.getByRole("checkbox", { name: "I have checked this warning: Source review overdue" }),
    ).not.toBeChecked();
  });

  it.each([
    { change: "checks", title: "Source review overdue", warningId: "w2", isChecked: true },
    { change: "unchecks", title: "Missing information", warningId: "w1", isChecked: false },
  ])("reports the warning that staff $change", async ({ title, warningId, isChecked }) => {
    const onAcknowledgedChange = vi.fn();
    const { user } = renderUi(
      <WarningList
        warnings={warnings}
        acknowledgedIds={new Set(["w1"])}
        onAcknowledgedChange={onAcknowledgedChange}
      />,
    );

    await user.click(
      screen.getByRole("checkbox", { name: `I have checked this warning: ${title}` }),
    );

    expect(onAcknowledgedChange).toHaveBeenCalledWith(warningId, isChecked);
  });
});

describe("ToggleChipGroup", () => {
  const options = [
    { value: "wrong_intent", label: "Wrong intent" },
    { value: "unsupported_claim", label: "Unsupported claim" },
  ];

  it("is a group named by its label, and each chip says whether it is on", () => {
    renderUi(
      <ToggleChipGroup
        label="Why did you reject it?"
        options={options}
        selected={new Set(["unsupported_claim"])}
        onToggle={vi.fn()}
      />,
    );

    expect(screen.getByRole("group", { name: "Why did you reject it?" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Unsupported claim" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByRole("button", { name: "Wrong intent" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
  });

  it("reports the chip that staff toggle", async () => {
    const onToggle = vi.fn();
    const { user } = renderUi(
      <ToggleChipGroup label="Why?" options={options} selected={new Set()} onToggle={onToggle} />,
    );

    await user.click(screen.getByRole("button", { name: "Wrong intent" }));

    expect(onToggle).toHaveBeenCalledWith("wrong_intent");
  });
});

describe("MarkedText and DraftText", () => {
  it("marks the marked parts and shows every part as plain text (SEC-22)", () => {
    renderUi(
      <p>
        <MarkedText
          parts={[
            { text: "<b>Sent</b> to ", isMarked: false },
            { text: "[EMAIL]", isMarked: true },
          ]}
        />
      </p>,
    );

    expect(screen.getByText("[EMAIL]").tagName).toBe("MARK");
    expect(screen.getByText(/<b>Sent<\/b> to/).tagName).toBe("P");
  });

  it("takes a marked segment in a draft", () => {
    const parts = [{ text: "[NAME]", isMarked: true }];
    renderUi(
      <DraftText
        paragraphs={[
          {
            paragraphId: "p0",
            segments: [{ segmentId: "s1", text: <MarkedText parts={parts} /> }],
          },
        ]}
      />,
    );

    expect(screen.getByText("[NAME]").tagName).toBe("MARK");
  });

  it("fades a rejected or outdated draft", () => {
    renderUi(
      <DraftText
        tone="muted"
        paragraphs={[{ paragraphId: "p0", segments: [{ segmentId: "s1", text: "Old." }] }]}
      />,
    );

    expect(screen.getByText("Old.").parentElement).toHaveClass("text-text-muted");
  });
});

describe("ReplyEditor", () => {
  it("is a text box named by its label that reports each change", async () => {
    const { onChange, user, editor } = renderEditor();

    await user.click(editor);
    await user.paste("Hello");

    expect(onChange).toHaveBeenCalledWith("Hello");
  });

  it("shows its placeholder while it is empty", () => {
    const { editor } = renderEditor();

    expect(editor).toHaveAttribute("placeholder", "Write the reply to the customer");
  });

  it("is described by its hint lines", () => {
    const { editor } = renderEditor({ hints: [SOURCES_HINT] });

    expect(editor).toHaveAccessibleDescription(SOURCES_HINT);
  });

  it("has no description without hint lines", () => {
    const { editor } = renderEditor();

    expect(editor).not.toHaveAttribute("aria-describedby");
  });

  it("marks the marked parts on a backdrop hidden from assistive technology (UI-43)", () => {
    renderEditor({
      value: "Sent to [EMAIL].",
      markedParts: [
        { text: "Sent to ", isMarked: false },
        { text: "[EMAIL]", isMarked: true },
        { text: ".", isMarked: false },
      ],
    });

    const mark = screen.getByText("[EMAIL]");
    expect(mark.tagName).toBe("MARK");
    expect(mark.parentElement).toHaveAttribute("aria-hidden", "true");
  });

  it("takes no more characters than its limit", () => {
    const { editor } = renderEditor({ maxLength: 10 });

    expect(editor).toHaveAttribute("maxlength", "10");
  });
});

describe("ReplyPreview", () => {
  it("shows the reply as plain text (SEC-22)", () => {
    renderUi(<ReplyPreview text="<b>Thank you</b> for waiting." />);

    expect(screen.getByText("<b>Thank you</b> for waiting.")).toBeVisible();
  });
});
