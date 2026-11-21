import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { MessageBox, type MessageBoxProps } from "@/design-system/components/message-box";
import { renderUi } from "@/test/render-app";

/**
 * Render the box with the given text length.
 *
 * @param overrides - The props that a test changes.
 * @returns The handlers and the user-event instance.
 */
function renderBox(overrides: Partial<MessageBoxProps> = {}) {
  const onSend = vi.fn();
  const onChange = vi.fn();
  const rendered = renderUi(
    <MessageBox
      inputId="order-message"
      label="Write to support about this order"
      text={{ value: "Hello", onChange }}
      limit={{ count: 5, max: 2000 }}
      isSending={false}
      onSend={onSend}
      {...overrides}
    />,
  );
  return { ...rendered, onSend, onChange };
}

describe("MessageBox", () => {
  it("labels the box and describes it with the counter and the help line", () => {
    renderBox();

    const box = screen.getByRole("textbox", { name: "Write to support about this order" });
    expect(box).toHaveAccessibleDescription(
      "5 / 2,000 characters Each message gets one reply from a person on our support team.",
    );
  });

  it("leaves the focus alone when it opens", () => {
    renderBox();

    expect(
      screen.getByRole("textbox", { name: "Write to support about this order" }),
    ).not.toHaveFocus();
  });

  it("passes each change to its container", async () => {
    const { user, onChange } = renderBox();

    await user.type(screen.getByRole("textbox"), "!");

    expect(onChange).toHaveBeenCalledWith("Hello!");
  });

  it("sends with Send message", async () => {
    const { user, onSend } = renderBox();

    await user.click(screen.getByRole("button", { name: "Send message" }));

    expect(onSend).toHaveBeenCalledTimes(1);
  });

  it.each([
    ["empty", { count: 0, max: 2000 }],
    ["over the limit", { count: 2001, max: 2000 }],
  ])("disables Send message while the box is %s", (_case, limit) => {
    renderBox({ limit });

    expect(screen.getByRole("button", { name: "Send message" })).toBeDisabled();
  });

  it("allows exactly the limit", () => {
    renderBox({ limit: { count: 2000, max: 2000 } });

    expect(screen.getByRole("button", { name: "Send message" })).toBeEnabled();
  });

  it("marks a text over the limit and says how to fix it", () => {
    renderBox({ limit: { count: 2001, max: 2000 } });

    expect(screen.getByRole("textbox")).toBeInvalid();
    expect(screen.getByText(/2,001 \/ 2,000 characters/)).toHaveTextContent(
      "Shorten your message to send it.",
    );
  });

  it("shows progress and does not send again while sending", async () => {
    const { user, onSend } = renderBox({ isSending: true });

    const button = screen.getByRole("button", { name: "Sending…" });
    await user.click(button);

    expect(button).toHaveAttribute("aria-disabled", "true");
    expect(onSend).not.toHaveBeenCalled();
  });

  it("shows the feedback it is given above the box", () => {
    renderBox({ children: <p role="alert">Your message was not sent.</p> });

    expect(screen.getByRole("alert")).toHaveTextContent("Your message was not sent.");
  });
});
