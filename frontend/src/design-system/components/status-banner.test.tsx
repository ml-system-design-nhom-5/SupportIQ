import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StatusBanner } from "@/design-system/components/status-banner";
import { Button } from "@/design-system/primitives/button";
import { renderUi } from "@/test/render-app";

describe("StatusBanner", () => {
  it("announces a danger banner as an alert, with its lead, text, trace ID, and action", () => {
    renderUi(
      <StatusBanner
        tone="danger"
        lead="Hoa Pham was not deactivated."
        traceId="eb211c80319c0af7651916cd43dd8448"
        action={<Button>Reload list</Button>}
      >
        This change would leave no active manager.
      </StatusBanner>,
    );

    const banner = screen.getByRole("alert");
    expect(banner).toHaveTextContent(
      "Hoa Pham was not deactivated. This change would leave no active manager.",
    );
    expect(screen.getByText("eb211c80319c0af7651916cd43dd8448")).toBeVisible();
    expect(screen.getByRole("button", { name: "Reload list" })).toBeVisible();
  });

  it.each(["success", "info", "warning"] as const)("announces a %s banner as a status", (tone) => {
    renderUi(<StatusBanner tone={tone} lead="Message sent." />);

    expect(screen.getByRole("status")).toHaveTextContent("Message sent.");
  });

  it("takes the focus from a script with a focus target ID, but is not in the tab order", () => {
    renderUi(
      <StatusBanner tone="success" lead="Your password was changed." focusTargetId="done" />,
    );

    const banner = screen.getByRole("status");
    document.getElementById("done")?.focus();

    expect(banner).toHaveFocus();
    expect(banner).toHaveAttribute("tabindex", "-1");
  });
});
