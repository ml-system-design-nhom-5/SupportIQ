import { screen, waitFor, within } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { CitationMarker } from "@/design-system/components/citation-marker";
import { CustomerOrders } from "@/design-system/components/customer-orders";
import { OrderChip } from "@/design-system/components/order-chip";
import { OrderCitationMarker } from "@/design-system/components/order-citation-marker";
import { OrderRecord } from "@/design-system/components/order-record";
import { SourceList } from "@/design-system/components/source-list";
import { presentationByDocumentValidity } from "@/design-system/components/status-presentations";
import { renderUi } from "@/test/render-app";

/**
 * Render the order chip with its open state held in the test.
 *
 * @param props - The count of other orders.
 * @returns The chip.
 */
function ChipWithState({ otherOrderCount }: { readonly otherOrderCount: number }) {
  const [isOpen, setIsOpen] = useState(false);
  return (
    <OrderChip
      orderId="ORD-20931"
      summary="Delivered · Refund under review"
      otherOrderCount={otherOrderCount}
      isOpen={isOpen}
      onOpenChange={setIsOpen}
    >
      <OrderRecord orderId="ORD-20931" facts={[{ term: "Order", value: "Delivered" }]} />
    </OrderChip>
  );
}

/**
 * Render the order chip with a button that opens it, as an order citation marker does.
 *
 * @returns The chip and the button.
 */
function ChipOpenedFromAnotherControl() {
  const [popover, setPopover] = useState<{ isOpen: boolean; opener?: HTMLElement }>({
    isOpen: false,
  });
  return (
    <>
      <button
        type="button"
        onClick={(event) => {
          setPopover({ isOpen: true, opener: event.currentTarget });
        }}
      >
        Open the order
      </button>
      <OrderChip
        orderId="ORD-20931"
        summary="Delivered · Refund under review"
        otherOrderCount={0}
        isOpen={popover.isOpen}
        onOpenChange={(isOpen) => {
          setPopover((current) => ({ ...current, isOpen }));
        }}
        {...(popover.opener === undefined
          ? {}
          : { returnFocus: { opener: popover.opener, fallbackId: "heading" } })}
      >
        <OrderRecord orderId="ORD-20931" facts={[{ term: "Order", value: "Delivered" }]} />
      </OrderChip>
    </>
  );
}

describe("OrderChip", () => {
  it("shows the order and its statuses, and opens the order from order records", async () => {
    const { user } = renderUi(<ChipWithState otherOrderCount={0} />);

    await user.click(
      screen.getByRole("button", {
        name: /ORD-20931 Delivered · Refund under review/,
      }),
    );

    const popover = await screen.findByRole("dialog", { name: "Order ORD-20931" });
    expect(within(popover).getByText("From order records, not AI")).toBeVisible();
    expect(within(popover).getByRole("definition")).toHaveTextContent("Delivered");
  });

  it.each([
    [1, "+1 order"],
    [2, "+2 orders"],
  ])("counts %i other orders", (count, text) => {
    renderUi(<ChipWithState otherOrderCount={count} />);

    expect(screen.getByRole("button", { name: new RegExp(`\\${text}$`) })).toBeVisible();
  });

  it("closes on Escape and returns the focus to the chip", async () => {
    const { user } = renderUi(<ChipWithState otherOrderCount={0} />);
    const chip = screen.getByRole("button", { name: /ORD-20931/ });
    await user.click(chip);
    await screen.findByRole("dialog", { name: "Order ORD-20931" });

    await user.keyboard("{Escape}");

    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
    expect(chip).toHaveFocus();
  });

  it("returns the focus to the control that opened it (UI-30)", async () => {
    const { user } = renderUi(<ChipOpenedFromAnotherControl />);
    const opener = screen.getByRole("button", { name: "Open the order" });
    await user.click(opener);
    await screen.findByRole("dialog", { name: "Order ORD-20931" });

    await user.keyboard("{Escape}");

    await waitFor(() => {
      expect(opener).toHaveFocus();
    });
  });
});

describe("CustomerOrders", () => {
  it("marks the ticket's order and the selected one, and selects another", async () => {
    const handleSelect = vi.fn();
    const { user } = renderUi(
      <CustomerOrders
        orders={[
          {
            orderId: "ORD-1",
            summary: "Delivered",
            isTicketOrder: true,
          },
          {
            orderId: "ORD-2",
            summary: "Shipped · In transit",
            isTicketOrder: false,
          },
        ]}
        selectedOrderId="ORD-1"
        onSelect={handleSelect}
        preview={<p>Preview</p>}
      />,
    );

    expect(screen.getByRole("button", { name: /ORD-1 This ticket/ })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await user.click(screen.getByRole("button", { name: /ORD-2/ }));

    expect(handleSelect).toHaveBeenCalledWith("ORD-2");
    expect(screen.getByText("Orders of this customer (2)")).toBeVisible();
  });
});

describe("CitationMarker", () => {
  it("shows the source on focus and opens it on activation (UI-20)", async () => {
    const handleActivate = vi.fn();
    const { user } = renderUi(
      <CitationMarker
        number={1}
        source={{
          title: "Refund policy",
          documentId: "refund-policy",
          version: "v3",
          validity: presentationByDocumentValidity.valid,
          period: "Since 1 Sept 2026",
        }}
        snippet="A refund request is reviewed."
        onActivate={handleActivate}
      />,
    );
    const marker = screen.getByRole("button", { name: "Source 1: Refund policy" });

    await user.tab();
    const hint = await screen.findByRole("tooltip");
    expect(hint).toHaveTextContent("refund-policy · v3In effectSince 1 Sept 2026");
    expect(hint).toHaveTextContent("“A refund request is reviewed.”");
    await user.click(marker);

    expect(handleActivate).toHaveBeenCalledWith(marker);
  });

  it("leaves out the validity of a version that the analysis did not return", async () => {
    const { user } = renderUi(
      <CitationMarker
        number={2}
        source={{ title: "DOC-9", documentId: "DOC-9", version: "1" }}
        snippet="A passage."
        onActivate={vi.fn()}
      />,
    );

    await user.tab();

    expect(await screen.findByRole("tooltip")).not.toHaveTextContent("In effect");
  });
});

describe("OrderCitationMarker", () => {
  it("lists the cited facts from order records, not AI, and opens the order", async () => {
    const handleActivate = vi.fn();
    const { user } = renderUi(
      <OrderCitationMarker
        orderId="ORD-20931"
        facts={[{ term: "Refund status", value: "Refund under review" }]}
        onActivate={handleActivate}
      />,
    );

    await user.tab();
    const hint = await screen.findByRole("tooltip");
    expect(hint).toHaveTextContent("Order ORD-20931From order records, not AI");
    expect(hint).toHaveTextContent("Refund statusRefund under review");
    await user.click(
      screen.getByRole("button", { name: "Order facts, from order records, not AI" }),
    );

    expect(handleActivate).toHaveBeenCalledOnce();
  });
});

describe("SourceList", () => {
  it("numbers cited sources, marks the others, and opens one", async () => {
    const handleOpen = vi.fn();
    const source = {
      title: "Refund policy",
      documentId: "refund-policy",
      version: "v3",
      validity: presentationByDocumentValidity.valid,
      period: "Since 1 Sept 2026",
    };
    const { user } = renderUi(
      <SourceList
        sources={[
          { ...source, key: "a", number: 1 },
          {
            ...source,
            key: "b",
            title: "Shipping FAQ",
            validity: presentationByDocumentValidity.expired,
          },
        ]}
        onOpen={handleOpen}
      />,
    );

    const [cited, notCited] = screen.getAllByRole("listitem");
    expect(cited).not.toHaveTextContent("Not cited");
    expect(notCited).toHaveTextContent("Not cited");
    expect(notCited).toHaveTextContent("Expired");
    const title = screen.getByRole("button", { name: "Source 1: Refund policy" });
    await user.click(title);

    expect(handleOpen).toHaveBeenCalledWith("a", title);
  });
});
