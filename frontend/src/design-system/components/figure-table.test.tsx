import { screen, within } from "@testing-library/react";
import { Gauge } from "lucide-react";
import { describe, expect, it } from "vitest";

import { FigureTable } from "@/design-system/components/figure-table";
import { renderUi } from "@/test/render-app";

const latencyRow = {
  id: "latency-p50",
  label: "End-to-end latency p50",
  value: "3.6 s",
  target: "At most 4 s",
};

describe("FigureTable", () => {
  it("shows each figure as a named row with its value and its target", () => {
    renderUi(
      <FigureTable icon={Gauge} title="Speed" rows={[latencyRow]} emptyText="No figures." />,
    );

    expect(screen.getByRole("heading", { level: 2, name: "Speed" })).toBeVisible();
    const table = screen.getByRole("table", { name: "Speed" });
    expect(
      within(table)
        .getAllByRole("columnheader")
        .map((header) => header.textContent),
    ).toEqual(["Figure", "Value", "Target"]);
    const row = within(table).getByRole("row", { name: /End-to-end latency p50/ });
    expect(within(row).getByRole("rowheader")).toHaveTextContent("End-to-end latency p50");
    expect(
      within(row)
        .getAllByRole("cell")
        .map((cell) => cell.textContent),
    ).toEqual(["3.6 s", "At most 4 s"]);
  });

  it("says that there are no figures instead of showing an empty table", () => {
    renderUi(
      <FigureTable
        icon={Gauge}
        title="AI outcomes"
        rows={[]}
        emptyText="No suggestions were completed in this period."
      />,
    );

    expect(screen.getByRole("heading", { level: 2, name: "AI outcomes" })).toBeVisible();
    expect(screen.getByText("No suggestions were completed in this period.")).toBeVisible();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});
