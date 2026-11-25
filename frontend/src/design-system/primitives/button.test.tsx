import { screen } from "@testing-library/react";
import { Send } from "lucide-react";
import { describe, expect, it, vi } from "vitest";

import { Button } from "@/design-system/primitives/button";
import { ButtonLink } from "@/design-system/primitives/button-link";
import { renderUi } from "@/test/render-app";

describe("Button", () => {
  it("is a button of type button, so it never submits a form by accident", () => {
    renderUi(<Button>Contact support</Button>);

    expect(screen.getByRole("button", { name: "Contact support" })).toHaveAttribute(
      "type",
      "button",
    );
  });

  it("calls its handler when activated", async () => {
    const onClick = vi.fn();
    const { user } = renderUi(<Button onClick={onClick}>Try again</Button>);

    await user.click(screen.getByRole("button", { name: "Try again" }));

    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("does not call its handler while disabled", async () => {
    const onClick = vi.fn();
    const { user } = renderUi(
      <Button disabled onClick={onClick}>
        Send message
      </Button>,
    );

    await user.click(screen.getByRole("button", { name: "Send message" }));

    expect(onClick).not.toHaveBeenCalled();
  });

  it("reads as disabled and busy while pending, and ignores activation", async () => {
    const onClick = vi.fn();
    const { user } = renderUi(
      <Button isPending onClick={onClick}>
        Sending…
      </Button>,
    );
    const button = screen.getByRole("button", { name: "Sending…" });

    await user.click(button);
    await user.keyboard("{Enter}");

    expect(button).toHaveAttribute("aria-disabled", "true");
    expect(button).toHaveAttribute("aria-busy", "true");
    expect(onClick).not.toHaveBeenCalled();
  });

  it("keeps the keyboard focus while pending (UI-30)", async () => {
    const { user } = renderUi(<Button isPending>Sending…</Button>);

    await user.tab();

    expect(screen.getByRole("button", { name: "Sending…" })).toHaveFocus();
  });

  it("does not send its form while pending", async () => {
    const onSubmit = vi.fn((event: SubmitEvent) => {
      event.preventDefault();
    });
    const { user } = renderUi(
      <form
        onSubmit={(event) => {
          onSubmit(event.nativeEvent);
        }}
      >
        <Button type="submit" isPending>
          Signing in…
        </Button>
      </form>,
    );

    await user.click(screen.getByRole("button", { name: "Signing in…" }));

    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("keeps the label as its accessible name when it has an icon", () => {
    renderUi(
      <Button variant="primary" size="lg" leadingIcon={Send} width="full-on-phone">
        Send message
      </Button>,
    );

    expect(screen.getByRole("button", { name: "Send message" })).toBeVisible();
  });

  it.each(["primary", "secondary", "danger", "ghost"] as const)(
    "renders the %s variant",
    (variant) => {
      renderUi(<Button variant={variant}>Deactivate</Button>);

      expect(screen.getByRole("button", { name: "Deactivate" })).toBeEnabled();
    },
  );

  it("can be a submit button of a form", () => {
    renderUi(<Button type="submit">Sign in</Button>);

    expect(screen.getByRole("button", { name: "Sign in" })).toHaveAttribute("type", "submit");
  });
});

describe("ButtonLink", () => {
  it("is a link to its path, with the button style", () => {
    renderUi(
      <ButtonLink to="/shop/orders" variant="primary" leadingIcon={Send}>
        Back to My orders
      </ButtonLink>,
    );

    expect(screen.getByRole("link", { name: "Back to My orders" })).toHaveAttribute(
      "href",
      "/shop/orders",
    );
  });
});
