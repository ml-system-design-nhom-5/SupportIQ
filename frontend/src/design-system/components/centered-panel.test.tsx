import { screen } from "@testing-library/react";
import { CircleCheck, TriangleAlert } from "lucide-react";
import { describe, expect, it } from "vitest";

import { CenteredPanel } from "@/design-system/components/centered-panel";
import { InlineMessage } from "@/design-system/components/inline-message";
import { renderUi } from "@/test/render-app";

describe("CenteredPanel", () => {
  it("is the main landmark of the page", () => {
    renderUi(<CenteredPanel>Sign in</CenteredPanel>);

    expect(screen.getByRole("main")).toHaveTextContent("Sign in");
  });
});

describe("InlineMessage", () => {
  it("announces an error as an alert with its text", () => {
    renderUi(
      <InlineMessage tone="danger" icon={TriangleAlert} role="alert" id="sign-in-error">
        The login name or the password is not correct.
      </InlineMessage>,
    );

    expect(screen.getByRole("alert")).toHaveTextContent(
      "The login name or the password is not correct.",
    );
    expect(screen.getByRole("alert")).toHaveAttribute("id", "sign-in-error");
  });

  it.each(["muted", "success"] as const)("shows a %s message without a role", (tone) => {
    renderUi(
      <InlineMessage tone={tone} icon={CircleCheck}>
        Hint
      </InlineMessage>,
    );

    expect(screen.getByText("Hint")).toBeVisible();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
