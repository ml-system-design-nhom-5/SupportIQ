import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AppErrorBoundary } from "@/app/app-error-boundary";

/**
 * Fail while rendering, as a provider that cannot start would.
 *
 * @returns Never.
 * @throws Error always.
 */
function FailingProvider(): never {
  throw new Error("The provider could not start.");
}

describe("AppErrorBoundary", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders its children when nothing fails", () => {
    render(
      <AppErrorBoundary>
        <p>The app</p>
      </AppErrorBoundary>,
    );

    expect(screen.getByText("The app")).toBeVisible();
  });

  it("says what to do, without the error text, when the app cannot render (UI-25)", () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);

    render(
      <AppErrorBoundary>
        <FailingProvider />
      </AppErrorBoundary>,
    );

    expect(
      screen.getByRole("heading", { level: 1, name: "SupportIQ could not start" }),
    ).toBeVisible();
    expect(screen.getByText(/Reload the page/)).toBeVisible();
    expect(screen.queryByText(/provider could not start/)).not.toBeInTheDocument();
  });
});
