import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DateText } from "@/design-system/components/date-text";
import { MoneyText } from "@/design-system/components/money-text";
import { ProductImage } from "@/design-system/components/product-image";
import { RelativeTime } from "@/design-system/components/relative-time";
import { RelativeTimeText } from "@/design-system/components/relative-time-text";
import { renderUi } from "@/test/render-app";

describe("MoneyText", () => {
  it("shows the amount with the shared formatter", () => {
    renderUi(<MoneyText money={{ amountMinor: 8900, currency: "USD" }} />);

    expect(screen.getByText("$89.00")).toBeVisible();
  });
});

describe("DateText", () => {
  it("shows the local date in a time element with the machine-readable timestamp", () => {
    renderUi(<DateText timestamp="2026-10-02T19:30:00Z" />);

    expect(screen.getByText("2 Oct 2026")).toHaveAttribute("datetime", "2026-10-02T19:30:00Z");
  });
});

describe("RelativeTime", () => {
  it("shows how long ago, relative to the clock (now is 2026-11-05T09:00:00Z)", () => {
    renderUi(<RelativeTime timestamp="2026-10-13T16:45:10Z" />);

    expect(screen.getByRole("button", { name: "3 weeks ago" })).toBeVisible();
  });

  it("shows the absolute local time on focus (UI-29)", async () => {
    const { user } = renderUi(<RelativeTime timestamp="2026-10-13T16:45:10Z" />);

    await user.tab();

    expect(await screen.findByRole("tooltip")).toHaveTextContent("13 Oct 2026, 16:45");
  });
});

describe("RelativeTimeText", () => {
  it("shows how long ago as text, with the absolute local time on hover (UI-29)", () => {
    renderUi(<RelativeTimeText timestamp="2026-10-13T16:45:10Z" />);

    const time = screen.getByText("3 weeks ago");
    expect(time).toHaveAttribute("title", "13 Oct 2026, 16:45");
    expect(time).toHaveAttribute("datetime", "2026-10-13T16:45:10Z");
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});

describe("ProductImage", () => {
  it.each(["card", "detail", "thumbnail"] as const)(
    "renders the neutral %s image, hidden from assistive technology",
    (size) => {
      const { container } = renderUi(<ProductImage size={size} />);

      expect(container.firstElementChild).toHaveAttribute("aria-hidden", "true");
    },
  );
});
