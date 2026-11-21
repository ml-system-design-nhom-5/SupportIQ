import { screen } from "@testing-library/react";
import { Inbox, SearchX } from "lucide-react";
import { describe, expect, it } from "vitest";

import { StateMessage } from "@/design-system/components/state-message";
import { ButtonLink } from "@/design-system/primitives/button-link";
import { renderUi } from "@/test/render-app";

describe("StateMessage", () => {
  it("shows the screen heading, the text, the actions, and the trace ID", () => {
    renderUi(
      <StateMessage
        icon={SearchX}
        headingLevel={1}
        title="This order was not found"
        description="It may not exist, or it belongs to another account."
        actions={<ButtonLink to="/shop/orders">Back to My orders</ButtonLink>}
        traceId="c80319c0af7651916cd43dd8448eb211"
      />,
    );

    expect(
      screen.getByRole("heading", { level: 1, name: "This order was not found" }),
    ).toBeVisible();
    expect(screen.getByText("It may not exist, or it belongs to another account.")).toBeVisible();
    expect(screen.getByRole("link", { name: "Back to My orders" })).toBeVisible();
    expect(screen.getByText("c80319c0af7651916cd43dd8448eb211")).toBeVisible();
  });

  it("can be a section state with only a level-2 heading", () => {
    renderUi(<StateMessage icon={Inbox} headingLevel={2} title="You have no orders yet." />);

    expect(
      screen.getByRole("heading", { level: 2, name: "You have no orders yet." }),
    ).toBeVisible();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });
});
