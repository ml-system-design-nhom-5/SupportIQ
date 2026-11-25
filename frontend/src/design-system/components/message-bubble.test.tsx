import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MessageBubble } from "@/design-system/components/message-bubble";
import { renderUi } from "@/test/render-app";

describe("MessageBubble", () => {
  it.each(["customer", "support"] as const)(
    "shows the header and the text of a %s message",
    (author) => {
      renderUi(
        <MessageBubble author={author} header="You · 3 weeks ago" text="Where is my parcel?" />,
      );

      expect(screen.getByText("You · 3 weeks ago")).toBeVisible();
      expect(screen.getByText("Where is my parcel?")).toBeVisible();
    },
  );

  it("renders HTML in a message as text (SEC-22)", () => {
    const html = "<img src=x onerror=alert(1)><b>bold</b>";

    const { container } = renderUi(<MessageBubble author="customer" header="You" text={html} />);

    expect(screen.getByText(html)).toBeVisible();
    expect(container.querySelector("img")).toBeNull();
  });

  it("keeps non-ASCII text and line breaks exactly as written", () => {
    const text = "Xin chào,\ntôi chưa nhận được tiền hoàn 🙏";

    renderUi(<MessageBubble author="customer" header="You" text={text} />);

    expect(screen.getByText(/Xin chào/).textContent).toBe(text);
  });
});
