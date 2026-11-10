import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StatusBadge } from "@/design-system/components/status-badge";
import {
  presentationByRefundStatus,
  type StatusTone,
} from "@/design-system/components/status-presentations";
import { renderUi } from "@/test/render-app";

describe("StatusBadge", () => {
  it("shows the label next to an icon hidden from assistive technology (UI-11)", () => {
    const { container } = renderUi(
      <StatusBadge presentation={presentationByRefundStatus.under_review} />,
    );

    expect(screen.getByText("Refund under review")).toBeVisible();
    expect(container.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
  });

  it.each<StatusTone>(["neutral", "info", "success", "warning", "danger", "ai"])(
    "renders the %s tone",
    (tone) => {
      renderUi(
        <StatusBadge
          presentation={{ ...presentationByRefundStatus.requested, tone, label: `Tone ${tone}` }}
        />,
      );

      expect(screen.getByText(`Tone ${tone}`)).toBeVisible();
    },
  );
});
