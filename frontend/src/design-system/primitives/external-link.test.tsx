import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ExternalLink } from "@/design-system/primitives/external-link";
import { renderUi } from "@/test/render-app";

/** An address outside the app: a trace in the Grafana of the local stack. */
const GRAFANA_HREF = "http://localhost:3000/explore?trace=4bf92f3577b34da6a3ce929d0e0e4736";

describe("ExternalLink", () => {
  it.each(["default", "strong"] as const)("is a %s link to its address", (emphasis) => {
    renderUi(
      <ExternalLink href={GRAFANA_HREF} emphasis={emphasis}>
        Open in Grafana
      </ExternalLink>,
    );

    expect(
      screen.getByRole("link", { name: "Open in Grafana (opens in a new tab)" }),
    ).toHaveAttribute("href", GRAFANA_HREF);
  });

  it("opens in a new tab without passing the address of the app on", () => {
    renderUi(<ExternalLink href={GRAFANA_HREF}>Open in Grafana</ExternalLink>);

    const link = screen.getByRole("link", { name: "Open in Grafana (opens in a new tab)" });
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noreferrer");
  });
});
