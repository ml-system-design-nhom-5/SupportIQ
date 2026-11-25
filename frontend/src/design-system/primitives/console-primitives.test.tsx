import { screen, waitFor } from "@testing-library/react";
import { FileText, LifeBuoy } from "lucide-react";
import { describe, expect, it, vi } from "vitest";

import { DescriptionList } from "@/design-system/primitives/description-list";
import { MenuSelect } from "@/design-system/primitives/menu-select";
import { Panel } from "@/design-system/primitives/panel";
import { PanelHeader } from "@/design-system/primitives/panel-header";
import { Sheet } from "@/design-system/primitives/sheet";
import { renderUi } from "@/test/render-app";

const statusOptions = [
  { value: "open", label: "Open" },
  { value: "closed", label: "Closed" },
] as const;

describe("MenuSelect", () => {
  it("names the choice and changes it from the list", async () => {
    const handleChange = vi.fn();
    const { user } = renderUi(
      <MenuSelect
        label="Ticket status"
        options={statusOptions}
        value="open"
        onChange={handleChange}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Ticket status: Open" }));
    expect(await screen.findByRole("menuitemradio", { name: "Open" })).toBeChecked();
    await user.click(screen.getByRole("menuitemradio", { name: "Closed" }));

    expect(handleChange).toHaveBeenCalledWith("closed");
  });

  it("shows a value that is not an option as it is", () => {
    renderUi(
      <MenuSelect
        label="Ticket status"
        options={statusOptions}
        value="archived"
        onChange={vi.fn()}
      />,
    );

    expect(screen.getByRole("button", { name: "Ticket status: archived" })).toBeVisible();
  });
});

describe("Sheet", () => {
  it("names the sheet by its title and closes it with Close", async () => {
    const handleClose = vi.fn();
    const { user } = renderUi(
      <>
        <button type="button" id="opener">
          Opener
        </button>
        <Sheet
          icon={FileText}
          title="Refund policy"
          returnFocus={{ opener: document.body, fallbackId: "opener" }}
          onClose={handleClose}
        >
          <p>Full text.</p>
        </Sheet>
      </>,
    );

    expect(screen.getByRole("dialog", { name: "Refund policy" })).toHaveTextContent("Full text.");
    await user.click(screen.getByRole("button", { name: "Close" }));

    await waitFor(() => {
      expect(handleClose).toHaveBeenCalledOnce();
    });
  });
});

describe("DescriptionList", () => {
  it("pairs each term with its value", () => {
    renderUi(<DescriptionList items={[{ term: "Owner", description: "Policy team" }]} />);

    expect(screen.getByRole("term")).toHaveTextContent("Owner");
    expect(screen.getByRole("definition")).toHaveTextContent("Policy team");
  });
});

describe("Panel density", () => {
  it.each([
    ["comfortable", "text-base"],
    ["compact", "text-sm"],
  ] as const)("gives a %s panel headings of its size", (density, sizeClass) => {
    renderUi(
      <Panel density={density}>
        <PanelHeader icon={LifeBuoy} level={2} title="Sources" />
      </Panel>,
    );

    expect(screen.getByRole("heading", { name: "Sources" })).toHaveClass(sizeClass);
  });
});
