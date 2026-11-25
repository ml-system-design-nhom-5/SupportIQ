import { screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { IntentChoice } from "@/design-system/components/intent-choice";
import { IntentStrip } from "@/design-system/components/intent-strip";
import type { IntentCorrection } from "@/design-system/components/other-intent-menu";
import { renderUi } from "@/test/render-app";

/** The intents of Other intent in these tests. */
const otherIntents = [
  { value: "cancel_order", name: "Cancel order" },
  { value: "track_order", name: "Track order" },
];

/** A candidate that staff can choose, and one whose intent this version does not know. */
const candidates = [
  { name: "Request refund", probability: 0.05, value: "request_refund" },
  { name: "Unspecified intent", probability: 0.02 },
];

/** The candidates of a low-confidence abstention; the last one cannot be chosen. */
const choiceCandidates = [
  { name: "Cancel order", probability: 0.41, band: "low", value: "cancel_order" },
  { name: "Change order", probability: 0.33, value: "change_order" },
  { name: "Unspecified intent", probability: 0.11 },
] as const;

/** The ID of Other intent in these tests. */
const OTHER_INTENT_ID = "other-intent";

/**
 * Render a strip that staff can correct, with no correction sending.
 *
 * @param overrides - The fields of the correction that a test changes.
 * @returns The handler of the corrections and the user-event instance.
 */
function renderCorrectableStrip(overrides: Partial<IntentCorrection> = {}) {
  const handleUseIntent = vi.fn();
  const { user } = renderUi(
    <IntentStrip
      intentName="Refund status"
      confidence={{ band: "high", probability: 0.91 }}
      candidates={candidates}
      correction={{ otherIntents, isSending: false, onUseIntent: handleUseIntent, ...overrides }}
    />,
  );
  return { handleUseIntent, user };
}

/**
 * Render the choice of an intent with "Use this intent" and Other intent.
 *
 * @param isSending - Whether a correction is sending.
 * @returns The handler of the choices and the user-event instance.
 */
function renderChoiceWithUse(isSending: boolean) {
  const handleUseIntent = vi.fn();
  const { user } = renderUi(
    <IntentChoice
      candidates={choiceCandidates}
      correction={{ otherIntents, isSending, onUseIntent: handleUseIntent }}
    />,
  );
  return { handleUseIntent, user };
}

describe("IntentStrip with a correction", () => {
  it("uses a next candidate in one interaction (UI-22)", async () => {
    const { handleUseIntent, user } = renderCorrectableStrip();

    await user.click(screen.getByRole("button", { name: "Use Request refund 5%" }));

    expect(handleUseIntent).toHaveBeenCalledWith("request_refund");
  });

  it("says Not right? Use: and keeps a candidate that staff cannot choose as plain text", () => {
    renderCorrectableStrip();

    const strip = screen.getByRole("region", { name: "Intent" });
    expect(strip).toHaveTextContent("Not right? Use:Use Request refund 5%Unspecified intent 2%");
    expect(within(strip).queryByRole("button", { name: /Unspecified intent/ })).toBeNull();
  });

  it("uses an intent from Other intent", async () => {
    const { handleUseIntent, user } = renderCorrectableStrip();

    await user.click(screen.getByRole("button", { name: "Other intent" }));
    await user.click(await screen.findByRole("menuitem", { name: "Track order" }));

    expect(handleUseIntent).toHaveBeenCalledWith("track_order");
  });

  it("disables the candidates and the intents of Other intent while a correction is sending", async () => {
    const { handleUseIntent, user } = renderCorrectableStrip({ isSending: true });

    const candidate = screen.getByRole("button", { name: "Use Request refund 5%" });
    await user.click(candidate);
    await user.click(screen.getByRole("button", { name: "Other intent" }));

    expect(candidate).toHaveAttribute("aria-disabled", "true");
    expect(await screen.findByRole("menuitem", { name: "Track order" })).toHaveAttribute(
      "aria-disabled",
      "true",
    );
    expect(handleUseIntent).not.toHaveBeenCalled();
  });

  it("lets a script move the focus to Other intent by its ID (UI-30)", () => {
    renderCorrectableStrip({ otherIntentId: OTHER_INTENT_ID });

    document.getElementById(OTHER_INTENT_ID)?.focus();

    expect(screen.getByRole("button", { name: "Other intent" })).toHaveFocus();
  });

  it("keeps the menu named Other intent when the button has an ID", async () => {
    const { user } = renderCorrectableStrip({ otherIntentId: OTHER_INTENT_ID });

    await user.click(screen.getByRole("button", { name: "Other intent" }));

    expect(await screen.findByRole("menu", { name: "Other intent" })).toBeVisible();
  });

  it("offers Other intent next to an intent that staff chose", () => {
    renderUi(
      <IntentStrip
        intentName="Request refund"
        candidates={[]}
        correction={{ otherIntents, isSending: false, onUseIntent: vi.fn() }}
      />,
    );

    const strip = screen.getByRole("region", { name: "Intent" });
    expect(strip).toHaveTextContent("Request refundChosen by staffNot right? Use:Other intent");
    expect(
      within(strip)
        .getAllByRole("button")
        .map((button) => button.textContent),
    ).toEqual(["Other intent"]);
  });
});

describe("IntentChoice with Use this intent", () => {
  it("names each button after its intent and uses it (UI-42)", async () => {
    const { handleUseIntent, user } = renderChoiceWithUse(false);

    await user.click(screen.getByRole("button", { name: "Use this intent: Change order" }));

    expect(handleUseIntent).toHaveBeenCalledWith("change_order");
  });

  it("offers no button for a candidate that staff cannot choose", () => {
    renderChoiceWithUse(false);

    expect(screen.getAllByRole("button")).toHaveLength(3);
    expect(screen.getByRole("button", { name: "Use this intent: Cancel order" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Use this intent: Change order" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Other intent" })).toBeVisible();
  });

  it("ignores Use this intent while a correction is sending", async () => {
    const { handleUseIntent, user } = renderChoiceWithUse(true);

    const button = screen.getByRole("button", { name: "Use this intent: Cancel order" });
    await user.click(button);

    expect(button).toHaveAttribute("aria-disabled", "true");
    expect(handleUseIntent).not.toHaveBeenCalled();
  });
});

describe("IntentChoice with Other intent", () => {
  it("uses an intent that is not among the candidates (ESC-01)", async () => {
    const { handleUseIntent, user } = renderChoiceWithUse(false);

    await user.click(screen.getByRole("button", { name: "Other intent" }));
    await user.click(await screen.findByRole("menuitem", { name: "Track order" }));

    expect(handleUseIntent).toHaveBeenCalledExactlyOnceWith("track_order");
  });

  it("is one row below the list, which holds only the candidates", () => {
    renderChoiceWithUse(false);

    const choice = screen.getByRole("region", { name: "Choose an intent" });
    expect(within(choice).getAllByRole("listitem")).toHaveLength(choiceCandidates.length);
    expect(
      within(within(choice).getByRole("list")).queryByRole("button", { name: "Other intent" }),
    ).toBeNull();
    expect(choice).toHaveTextContent(/Unspecified intent11%None of these\? Use:Other intent$/);
  });

  it("opens with the keyboard, chooses by typing, and gives the focus back (UI-30)", async () => {
    const { handleUseIntent, user } = renderChoiceWithUse(false);
    const button = screen.getByRole("button", { name: "Other intent" });

    button.focus();
    await user.keyboard("{Enter}");
    await screen.findByRole("menu", { name: "Other intent" });
    await user.keyboard("{Escape}");
    expect(button).toHaveFocus();

    await user.keyboard("{Enter}");
    await screen.findByRole("menu", { name: "Other intent" });
    await user.keyboard("track{Enter}");

    expect(handleUseIntent).toHaveBeenCalledExactlyOnceWith("track_order");
  });

  it("disables its intents while a correction is sending", async () => {
    const { handleUseIntent, user } = renderChoiceWithUse(true);

    await user.click(screen.getByRole("button", { name: "Other intent" }));
    const intent = await screen.findByRole("menuitem", { name: "Track order" });
    await user.click(intent);

    expect(intent).toHaveAttribute("aria-disabled", "true");
    expect(handleUseIntent).not.toHaveBeenCalled();
  });

  it("is absent when staff may not choose an intent (UI-40)", () => {
    renderUi(<IntentChoice candidates={choiceCandidates} />);

    const choice = screen.getByRole("region", { name: "Choose an intent" });
    expect(within(choice).queryAllByRole("button")).toEqual([]);
    expect(choice).not.toHaveTextContent("None of these?");
  });
});
