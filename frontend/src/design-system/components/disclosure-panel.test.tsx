import { screen } from "@testing-library/react";
import { Code } from "lucide-react";
import { describe, expect, it } from "vitest";

import { DisclosurePanel } from "@/design-system/components/disclosure-panel";
import { renderUi } from "@/test/render-app";

/** The text of the content in these tests. */
const CONTENT_TEXT = "Release rel-2026-11-01";

/**
 * Render a panel titled "Developer details" with one line of content.
 *
 * @param isDefaultOpen - Whether the panel starts open; absent, it starts closed.
 * @returns What {@link renderUi} returns.
 */
function renderPanel(isDefaultOpen?: boolean) {
  return renderUi(
    <DisclosurePanel
      title="Developer details"
      icon={Code}
      {...(isDefaultOpen === undefined ? {} : { isDefaultOpen })}
    >
      {CONTENT_TEXT}
    </DisclosurePanel>,
  );
}

describe("DisclosurePanel", () => {
  it("is closed by default, and the content is not rendered at all", () => {
    renderPanel();

    const button = screen.getByRole("button", { name: "Developer details" });
    expect(button).toHaveAttribute("aria-expanded", "false");
    expect(button).not.toHaveAttribute("aria-controls");
    expect(screen.queryByText(CONTENT_TEXT)).not.toBeInTheDocument();
  });

  it.each([
    [undefined, 2],
    [3, 3],
  ] as const)("holds its button in a heading, level %s by default 2 (UI-30)", (level, shown) => {
    renderUi(
      <DisclosurePanel
        title="Developer details"
        icon={Code}
        {...(level === undefined ? {} : { level })}
      >
        {CONTENT_TEXT}
      </DisclosurePanel>,
    );

    expect(
      screen.getByRole("heading", { level: shown, name: "Developer details" }),
    ).toContainElement(screen.getByRole("button", { name: "Developer details" }));
  });

  it("opens, names the content it controls, and closes again", async () => {
    const { user } = renderPanel();
    const button = screen.getByRole("button", { name: "Developer details" });

    await user.click(button);

    expect(button).toHaveAttribute("aria-expanded", "true");
    const content = screen.getByText(CONTENT_TEXT);
    expect(content).toBeVisible();
    const contentId = button.getAttribute("aria-controls") ?? "";
    expect(document.getElementById(contentId)).toContainElement(content);

    await user.click(button);

    expect(button).toHaveAttribute("aria-expanded", "false");
    expect(button).not.toHaveAttribute("aria-controls");
    expect(screen.queryByText(CONTENT_TEXT)).not.toBeInTheDocument();
  });

  it("opens with the keyboard (UI-30)", async () => {
    const { user } = renderPanel();
    const button = screen.getByRole("button", { name: "Developer details" });
    button.focus();

    await user.keyboard("{Enter}");
    expect(screen.getByText(CONTENT_TEXT)).toBeVisible();
    await user.keyboard(" ");

    expect(screen.queryByText(CONTENT_TEXT)).not.toBeInTheDocument();
    expect(button).toHaveFocus();
  });

  it("starts open when asked", () => {
    renderPanel(true);

    expect(screen.getByRole("button", { name: "Developer details" })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
    expect(screen.getByText(CONTENT_TEXT)).toBeVisible();
  });
});
