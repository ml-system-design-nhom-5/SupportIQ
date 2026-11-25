import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { FailureBanner } from "@/features/backend-requests/components/failure-banner";
import { FailureState } from "@/features/backend-requests/components/failure-state";
import { renderUi } from "@/test/render-app";

describe("FailureState", () => {
  it("says what could not load, why, and offers Try again with the trace ID", async () => {
    const onRetry = vi.fn();
    const { user } = renderUi(
      <FailureState
        title="Your orders could not be loaded"
        headingLevel={1}
        isRetrying={false}
        onRetry={onRetry}
        failure={{
          kind: "problem",
          status: 503,
          problemType: "not_ready",
          traceId: "1c80319c0af7651916cd43dd8448eb21",
        }}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Try again" }));

    expect(
      screen.getByRole("heading", { level: 1, name: "Your orders could not be loaded" }),
    ).toBeVisible();
    expect(
      screen.getByText("The service is not available right now. Try again in a moment."),
    ).toBeVisible();
    expect(screen.getByText("1c80319c0af7651916cd43dd8448eb21")).toBeVisible();
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("disables Try again while it loads again", () => {
    renderUi(
      <FailureState
        title="Tickets could not be loaded"
        headingLevel={2}
        isRetrying
        onRetry={vi.fn()}
        failure={{ kind: "network" }}
      />,
    );

    expect(screen.getByRole("button", { name: "Trying again…" })).toHaveAttribute(
      "aria-disabled",
      "true",
    );
    expect(screen.queryByText(/Details: trace/)).not.toBeInTheDocument();
  });
});

describe("FailureBanner", () => {
  it("announces what did not happen and why, without a status code", () => {
    renderUi(
      <FailureBanner
        lead="Your message was not sent."
        failure={{ kind: "ingress", status: 413 }}
      />,
    );

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Your message was not sent. The request is too large. Shorten your text and try again.",
    );
    expect(screen.getByRole("alert")).not.toHaveTextContent("413");
  });
});
