import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Tooltip } from "@/design-system/primitives/tooltip";
import { renderUi } from "@/test/render-app";

describe("Tooltip", () => {
  it("shows nothing until it is asked for", () => {
    renderUi(<Tooltip content="2 Oct 2026, 19:30">3 weeks ago</Tooltip>);

    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
  });

  it("shows the hint when its trigger gets keyboard focus", async () => {
    const { user } = renderUi(<Tooltip content="2 Oct 2026, 19:30">3 weeks ago</Tooltip>);

    await user.tab();

    expect(await screen.findByRole("tooltip")).toHaveTextContent("2 Oct 2026, 19:30");
  });

  it("shows the hint when its trigger is tapped or clicked (shop UI design, States)", async () => {
    const { user } = renderUi(<Tooltip content="2 Oct 2026, 19:30">3 weeks ago</Tooltip>);

    await user.click(screen.getByRole("button", { name: "3 weeks ago" }));

    expect(await screen.findByRole("tooltip")).toHaveTextContent("2 Oct 2026, 19:30");
  });
});
