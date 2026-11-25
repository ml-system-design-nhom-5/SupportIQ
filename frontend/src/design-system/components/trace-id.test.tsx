import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { TraceId } from "@/design-system/components/trace-id";
import { renderUi } from "@/test/render-app";

const TRACE_ID = "4bf92f3577b34da6a3ce929d0e0e4736";

/** A ready Grafana link of the local stack, as the feature builds it. */
const TRACE_HREF = `http://localhost:3000/explore?trace=${TRACE_ID}`;

describe("TraceId", () => {
  it("shows the trace ID under Details (UI-25)", () => {
    renderUi(<TraceId traceId={TRACE_ID} />);

    expect(screen.getByText(/Details: trace/)).toHaveTextContent(`Details: trace ${TRACE_ID}`);
  });

  it("has no Grafana link without one", () => {
    renderUi(<TraceId traceId={TRACE_ID} />);

    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("links to the trace in Grafana in a new tab and says so (UI-35)", () => {
    renderUi(<TraceId traceId={TRACE_ID} traceHref={TRACE_HREF} />);

    const link = screen.getByRole("link", { name: "Open in Grafana (opens in a new tab)" });
    expect(link).toHaveAttribute("href", TRACE_HREF);
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noreferrer");
  });

  it("copies the trace ID and says so", async () => {
    const { user } = renderUi(<TraceId traceId={TRACE_ID} />);
    const writeText = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue();

    await user.click(screen.getByRole("button", { name: "Copy trace ID" }));

    expect(writeText).toHaveBeenCalledWith(TRACE_ID);
    expect(screen.getByRole("status")).toHaveTextContent("Trace ID copied.");
  });

  it("tells the person to select the ID when the clipboard refuses", async () => {
    const { user } = renderUi(<TraceId traceId={TRACE_ID} />);
    vi.spyOn(navigator.clipboard, "writeText").mockRejectedValue(
      new DOMException("Denied", "NotAllowedError"),
    );

    await user.click(screen.getByRole("button", { name: "Copy trace ID" }));

    expect(screen.getByRole("status")).toHaveTextContent(
      "The trace ID could not be copied. Select it to copy it.",
    );
  });
});
