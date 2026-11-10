import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { TraceId } from "@/design-system/components/trace-id";
import { renderUi } from "@/test/render-app";

const TRACE_ID = "4bf92f3577b34da6a3ce929d0e0e4736";

describe("TraceId", () => {
  it("shows the trace ID under Details (UI-25)", () => {
    renderUi(<TraceId traceId={TRACE_ID} />);

    expect(screen.getByText(/Details: trace/)).toHaveTextContent(`Details: trace ${TRACE_ID}`);
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
