import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CopyableText } from "@/design-system/components/copyable-text";
import { renderUi } from "@/test/render-app";

const TEXT = "Hello Lan,\n\nyour refund is under review.";

describe("CopyableText", () => {
  it("shows the text as written, in a region of its name", () => {
    renderUi(<CopyableText label="Your unsent text">{TEXT}</CopyableText>);

    expect(screen.getByRole("region", { name: "Your unsent text" })).toHaveTextContent(
      "Hello Lan, your refund is under review.",
    );
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });

  it("copies the text and says so", async () => {
    const { user } = renderUi(<CopyableText label="Your unsent text">{TEXT}</CopyableText>);
    const writeText = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue();

    await user.click(screen.getByRole("button", { name: "Copy text" }));

    expect(writeText).toHaveBeenCalledWith(TEXT);
    expect(screen.getByRole("status")).toHaveTextContent("Text copied.");
  });

  it("tells the person to select the text when the clipboard refuses", async () => {
    const { user } = renderUi(<CopyableText label="Your unsent text">{TEXT}</CopyableText>);
    vi.spyOn(navigator.clipboard, "writeText").mockRejectedValue(
      new DOMException("Denied", "NotAllowedError"),
    );

    await user.click(screen.getByRole("button", { name: "Copy text" }));

    expect(screen.getByRole("status")).toHaveTextContent(
      "The text could not be copied. Select it to copy it.",
    );
  });
});
