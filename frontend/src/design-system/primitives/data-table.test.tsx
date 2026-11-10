import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { buildRowHeaderId, DataTable } from "@/design-system/primitives/data-table";
import { renderUi } from "@/test/render-app";

describe("DataTable", () => {
  it("marks the cell that names its row as a row header", () => {
    renderUi(
      <DataTable
        caption="Internal accounts"
        columns={[
          { key: "account", label: "Account", isRowHeader: true },
          { key: "role", label: "Role" },
        ]}
        rows={[{ id: "1", cells: { account: "Hoa Pham", role: "Manager" } }]}
      />,
    );

    expect(screen.getByRole("rowheader", { name: "Hoa Pham" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "Manager" })).toBeInTheDocument();
  });

  it("lets a screen move the focus to a row header, outside the tab order (UI-30)", () => {
    renderUi(
      <DataTable
        caption="Internal accounts"
        columns={[{ key: "account", label: "Account", isRowHeader: true }]}
        rows={[{ id: "1", cells: { account: "Hoa Pham" } }]}
      />,
    );

    document.getElementById(buildRowHeaderId("1"))?.focus();

    const header = screen.getByRole("rowheader", { name: "Hoa Pham" });
    expect(header).toHaveFocus();
    expect(header).toHaveAttribute("tabindex", "-1");
  });

  it("names the table and its columns, and puts each cell in its column", () => {
    renderUi(
      <DataTable
        caption="Internal accounts"
        columns={[
          { key: "account", label: "Account" },
          { key: "actions", label: "Actions", align: "end" },
        ]}
        rows={[{ id: "1", cells: { account: "Hoa Pham", actions: "Make staff" } }]}
      />,
    );

    const table = screen.getByRole("table", { name: "Internal accounts" });
    expect(
      within(table)
        .getAllByRole("columnheader")
        .map((header) => header.textContent),
    ).toEqual(["Account", "Actions"]);
    expect(within(table).getByRole("cell", { name: "Hoa Pham" })).toBeInTheDocument();
    expect(within(table).getByRole("cell", { name: "Make staff" })).toBeInTheDocument();
  });

  it("renders the header without rows when the list is empty", () => {
    renderUi(
      <DataTable
        caption="Internal accounts"
        columns={[{ key: "account", label: "Account" }]}
        rows={[]}
      />,
    );

    expect(screen.queryAllByRole("cell")).toHaveLength(0);
    expect(screen.getByRole("columnheader", { name: "Account" })).toBeInTheDocument();
  });
});
