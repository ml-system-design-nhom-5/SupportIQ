import { screen } from "@testing-library/react";
import { Code } from "lucide-react";
import { describe, expect, it } from "vitest";

import {
  DisclosurePanel,
  type DisclosurePanelProps,
} from "@/design-system/components/disclosure-panel";
import { renderUi } from "@/test/render-app";

/** The text of the content in these tests. */
const CONTENT_TEXT = "Release rel-2026-11-01";

/** The props that a test can set; the others are fixed. */
type PanelOptions = Partial<Pick<DisclosurePanelProps, "level" | "isDefaultOpen">>;

/**
 * Render a panel titled "Developer details" with one line of content.
 *
 * @param options - The heading level and whether the panel starts open; absent, the defaults.
 * @returns What {@link renderUi} returns.
 */
function renderPanel(options: PanelOptions = {}) {
  return renderUi(
    <DisclosurePanel title="Developer details" icon={Code} {...options}>
      {CONTENT_TEXT}
    </DisclosurePanel>,
  );
}

/**
 * Find the button of the panel.
 *
 * @returns The button named "Developer details".
 */
function getPanelButton(): HTMLElement {
  return screen.getByRole("button", { name: "Developer details" });
}

describe("DisclosurePanel", () => {
  it("is closed by default, and the content is not rendered at all", () => {
    renderPanel();

    const button = getPanelButton();
    expect(button).toHaveAttribute("aria-expanded", "false");
    expect(button).not.toHaveAttribute("aria-controls");
    expect(screen.queryByText(CONTENT_TEXT)).not.toBeInTheDocument();
  });

  it("holds its button in a level 2 heading by default (UI-30)", () => {
    renderPanel();

    expect(screen.getByRole("heading", { level: 2, name: "Developer details" })).toContainElement(
      getPanelButton(),
    );
  });

  it("holds its button in a level 3 heading when asked (UI-30)", () => {
    renderPanel({ level: 3 });

    expect(screen.getByRole("heading", { level: 3, name: "Developer details" })).toContainElement(
      getPanelButton(),
    );
  });

  it("opens on a click and shows the content", async () => {
    const { user } = renderPanel();

    await user.click(getPanelButton());

    expect(getPanelButton()).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText(CONTENT_TEXT)).toBeVisible();
  });

  it("names the content it controls while it is open", () => {
    renderPanel({ isDefaultOpen: true });

    const contentId = getPanelButton().getAttribute("aria-controls") ?? "";
    expect(document.getElementById(contentId)).toContainElement(screen.getByText(CONTENT_TEXT));
  });

  it("closes on a click, removes the content, and stops naming it", async () => {
    const { user } = renderPanel({ isDefaultOpen: true });

    await user.click(getPanelButton());

    expect(getPanelButton()).toHaveAttribute("aria-expanded", "false");
    expect(getPanelButton()).not.toHaveAttribute("aria-controls");
    expect(screen.queryByText(CONTENT_TEXT)).not.toBeInTheDocument();
  });

  it("opens with Enter (UI-30)", async () => {
    const { user } = renderPanel();
    getPanelButton().focus();

    await user.keyboard("{Enter}");

    expect(screen.getByText(CONTENT_TEXT)).toBeVisible();
  });

  it("closes with Space and keeps the focus on its button (UI-30)", async () => {
    const { user } = renderPanel({ isDefaultOpen: true });
    getPanelButton().focus();

    await user.keyboard(" ");

    expect(screen.queryByText(CONTENT_TEXT)).not.toBeInTheDocument();
    expect(getPanelButton()).toHaveFocus();
  });

  it("starts open when asked", () => {
    renderPanel({ isDefaultOpen: true });

    expect(getPanelButton()).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText(CONTENT_TEXT)).toBeVisible();
  });
});
