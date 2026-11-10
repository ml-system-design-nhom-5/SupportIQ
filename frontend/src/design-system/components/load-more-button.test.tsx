import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LoadMoreButton } from "@/design-system/components/load-more-button";
import { renderUi } from "@/test/render-app";

describe("LoadMoreButton", () => {
  it("loads the next page when activated", async () => {
    const onLoadMore = vi.fn();
    const { user } = renderUi(
      <LoadMoreButton label="Show more products" isLoading={false} onLoadMore={onLoadMore} />,
    );

    await user.click(screen.getByRole("button", { name: "Show more products" }));

    expect(onLoadMore).toHaveBeenCalledTimes(1);
  });

  it("is disabled and busy while the next page loads, so one click loads one page", async () => {
    const onLoadMore = vi.fn();
    const { user } = renderUi(
      <LoadMoreButton label="Show more products" isLoading size="md" onLoadMore={onLoadMore} />,
    );

    const button = screen.getByRole("button", { name: "Loading…" });
    await user.click(button);

    expect(button).toHaveAttribute("aria-disabled", "true");
    expect(button).toHaveAttribute("aria-busy", "true");
    expect(onLoadMore).not.toHaveBeenCalled();
  });
});
