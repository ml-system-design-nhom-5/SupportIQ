import { screen } from "@testing-library/react";
import { CircleCheck, LifeBuoy } from "lucide-react";
import { describe, expect, it } from "vitest";

import { Grid } from "@/design-system/primitives/grid";
import { Heading } from "@/design-system/primitives/heading";
import { Icon } from "@/design-system/primitives/icon";
import { Identifier } from "@/design-system/primitives/identifier";
import { PageColumn } from "@/design-system/primitives/page-column";
import { Panel } from "@/design-system/primitives/panel";
import { PanelHeader } from "@/design-system/primitives/panel-header";
import { PanelSection } from "@/design-system/primitives/panel-section";
import { Skeleton } from "@/design-system/primitives/skeleton";
import { Stack } from "@/design-system/primitives/stack";
import { Text } from "@/design-system/primitives/text";
import { VisuallyHidden } from "@/design-system/primitives/visually-hidden";
import { renderUi } from "@/test/render-app";

describe("Stack", () => {
  it("renders the element it is given, so lists keep their semantics", () => {
    renderUi(
      <Stack as="ul" direction="row" gap="2" align="center" justify="between">
        <li>Order</li>
        <li>Shipment</li>
      </Stack>,
    );

    expect(screen.getAllByRole("listitem")).toHaveLength(2);
  });

  it("names a section landmark", () => {
    renderUi(
      <Stack as="section" label="Order statuses">
        <Text>Delivered</Text>
      </Stack>,
    );

    expect(screen.getByRole("region", { name: "Order statuses" })).toBeInTheDocument();
  });
});

describe("Panel", () => {
  it("holds a header with a heading of the given level and sections", () => {
    renderUi(
      <Panel as="section" label="Support for this order">
        <PanelHeader icon={LifeBuoy} level={2} title="Support for this order" trailing="2" />
        <PanelSection>
          <Text>Tickets</Text>
        </PanelSection>
        <PanelSection layout="centered">
          <Text>Message box</Text>
        </PanelSection>
      </Panel>,
    );

    expect(screen.getByRole("region", { name: "Support for this order" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Support for this order" })).toBeVisible();
  });

  it("can use a level-3 heading inside a section", () => {
    renderUi(
      <Panel>
        <PanelHeader icon={LifeBuoy} level={3} title="Lines" />
      </Panel>,
    );

    expect(screen.getByRole("heading", { level: 3, name: "Lines" })).toBeVisible();
  });
});

describe("PageColumn", () => {
  it.each(["shop", "admin"] as const)("is the main landmark of the %s area", (area) => {
    renderUi(
      <PageColumn area={area}>
        <Text>Content</Text>
      </PageColumn>,
    );

    expect(screen.getByRole("main")).toHaveTextContent("Content");
  });
});

describe("Grid", () => {
  it("is a named list when it holds list items", () => {
    renderUi(
      <Grid as="ul" label="Products">
        <li>Desk lamp</li>
      </Grid>,
    );

    expect(screen.getByRole("list", { name: "Products" })).toBeInTheDocument();
  });
});

describe("Heading", () => {
  it.each([
    [1, "page"],
    [2, "section"],
    [3, "item"],
  ] as const)("renders level %i with the %s size", (level, size) => {
    renderUi(
      <Heading level={level} size={size}>
        Title
      </Heading>,
    );

    expect(screen.getByRole("heading", { level, name: "Title" })).toBeVisible();
  });
});

describe("Text", () => {
  it("renders customer text as text, never as HTML (SEC-22)", () => {
    renderUi(<Text overflow="preserve">{"<b>bold</b>"}</Text>);

    expect(screen.getByText("<b>bold</b>")).toBeVisible();
  });

  it("renders the tone and the size it is given", () => {
    renderUi(
      <Text tone="danger" size="base">
        Not sent
      </Text>,
    );

    expect(screen.getByText("Not sent")).toHaveClass("text-danger", "text-base");
  });
});

describe("Identifier", () => {
  it("keeps the identifier in the text of its heading", () => {
    renderUi(
      <Heading level={1}>
        Order <Identifier>ORD-20931</Identifier>
      </Heading>,
    );

    expect(screen.getByRole("heading", { level: 1, name: "Order ORD-20931" })).toBeVisible();
  });
});

describe("Icon, Skeleton, and VisuallyHidden", () => {
  it("hide decoration from assistive technology and keep hidden text readable", () => {
    const { container } = renderUi(
      <>
        <Icon icon={CircleCheck} size="lg" tone="success" />
        <Skeleton width="half" height="block" />
        <VisuallyHidden>Order status</VisuallyHidden>
      </>,
    );

    expect(container.querySelectorAll("[aria-hidden='true']")).toHaveLength(2);
    expect(screen.getByText("Order status")).toBeInTheDocument();
  });
});
