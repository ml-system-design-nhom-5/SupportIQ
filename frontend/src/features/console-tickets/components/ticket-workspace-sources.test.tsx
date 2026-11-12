import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { getConsoleKbDocumentVersionRoute } from "@/test/backend-routes";
import { openConsole, TICKET_PATH, workspaceExample } from "@/test/console-screen";
import { exampleAnswer, type FakeAnswer } from "@/test/fake-backend";

/**
 * Open the workspace of TCK-1042 and wait for it.
 *
 * @param answers - The answers of `getConsoleTicket` and `getConsoleKbDocumentVersion`.
 * @returns The rendered app and the `main` landmark.
 */
async function openWorkspace(
  answers: { readonly workspace?: FakeAnswer; readonly kbDocument?: FakeAnswer } = {},
) {
  const rendered = openConsole(TICKET_PATH, {
    workspace: [answers.workspace ?? workspaceExample("draft-ready")],
    ...(answers.kbDocument === undefined ? {} : { kbDocument: [answers.kbDocument] }),
  });
  await screen.findByRole("heading", { level: 1, name: /^Ticket / });
  return { ...rendered, main: screen.getByRole("main") };
}

/**
 * Find the KB citation marker of the draft.
 *
 * @param main - The `main` landmark.
 * @returns The marker of source 1.
 */
function getCitationMarker(main: HTMLElement): HTMLElement {
  return within(within(main).getByRole("region", { name: "AI draft" })).getByRole("button", {
    name: "Source 1: Sample refund document",
  });
}

/**
 * Find the order citation marker of the draft.
 *
 * @param main - The `main` landmark.
 * @returns The marker.
 */
function getOrderMarker(main: HTMLElement): HTMLElement {
  return within(main).getByRole("button", { name: "Order facts, from order records, not AI" });
}

describe("The KB document version (UI-20)", () => {
  it("opens from a citation marker, with the cited passage highlighted", async () => {
    const { user, main, backend } = await openWorkspace();

    await user.click(getCitationMarker(main));

    const sheet = await screen.findByRole("dialog", { name: "Sample refund document" });
    expect(sheet).toHaveTextContent("SAMPLE-REFUND-001 · 1.0In effect");
    expect(sheet).toHaveTextContent("In effect1 Jan 2026 to 1 Jan 2027OwnerPolicy owner (sample)");
    expect(
      within(sheet).getByText("This is sample text. It is not KB content and not a policy.")
        .tagName,
    ).toBe("MARK");
    expect(backend.requestsTo(getConsoleKbDocumentVersionRoute)[0]?.path).toBe(
      "/v1/console/kb-documents/SAMPLE-REFUND-001/versions/1.0",
    );
  });

  it("opens from the Sources panel and returns the focus to the source when it closes", async () => {
    const { user, main } = await openWorkspace();
    const source = within(within(main).getByRole("region", { name: "Sources" })).getByRole(
      "button",
      { name: "Source 1: Sample refund document" },
    );

    await user.click(source);
    await screen.findByRole("dialog", { name: "Sample refund document" });
    await user.click(screen.getByRole("button", { name: "Close" }));

    await waitFor(() => {
      expect(source).toHaveFocus();
    });
  });

  it("lists a retrieved source that the draft does not cite", async () => {
    const { main } = await openWorkspace({
      workspace: workspaceExample("abstained-low-confidence"),
    });

    expect(within(main).getByRole("region", { name: "Sources" })).toHaveTextContent("Not cited");
  });

  it("says that no document supports the request when the analysis found none", async () => {
    const { main } = await openWorkspace({ workspace: workspaceExample("escalated") });

    expect(within(main).getByRole("region", { name: "Sources" })).toHaveTextContent(
      "No document in effect supports this request.",
    );
  });

  it.each([
    [exampleAnswer(404, "problems", "not-found"), "This document version was not found"],
    [exampleAnswer(503, "problems", "ai-service-not-ready"), "This document could not be loaded"],
  ])("shows a failure of the version in the sheet", async (kbDocument, title) => {
    const { user, main } = await openWorkspace({ kbDocument });

    await user.click(getCitationMarker(main));

    const sheet = await screen.findByRole("dialog", { name: "Sample refund document" });
    expect(await within(sheet).findByRole("heading", { name: title })).toBeVisible();
    expect(within(sheet).getByText(/Details: trace/)).toBeVisible();
  });

  it("shows a skeleton while the version loads", async () => {
    const { user, main } = await openWorkspace({ kbDocument: { kind: "no_answer" } });

    await user.click(getCitationMarker(main));

    const sheet = await screen.findByRole("dialog", { name: "Sample refund document" });
    expect(within(sheet).getByRole("status")).toHaveTextContent("Loading the document…");
  });
});

describe("The order chip (console UI design, Order chip)", () => {
  it("lists the customer's orders, the ticket's order first and selected", async () => {
    const { user, main } = await openWorkspace();

    await user.click(within(main).getByRole("button", { name: /^ORD-20931 Delivered/ }));

    const popover = await screen.findByRole("dialog", { name: "Orders of this customer" });
    expect(within(popover).getByRole("button", { name: /ORD-20931 This ticket/ })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(popover).toHaveTextContent("Ship to12 Sample Street, Sample City");
    expect(popover).toHaveTextContent("From order records, not AI");
  });

  it("previews another order without its address, and says that the AI did not use it", async () => {
    const { user, main } = await openWorkspace();
    await user.click(within(main).getByRole("button", { name: /^ORD-20931 Delivered/ }));
    const popover = await screen.findByRole("dialog", { name: "Orders of this customer" });

    await user.click(within(popover).getByRole("button", { name: /ORD-20990/ }));

    expect(popover).toHaveTextContent("Not the order of this ticket. The AI did not use it.");
    expect(popover).toHaveTextContent("ItemsDesk lamp × 1");
    expect(popover).not.toHaveTextContent("Ship to");
  });

  it("shows the facts of a single order", async () => {
    const { user, main } = await openWorkspace({ workspace: workspaceExample("closed") });

    await user.click(within(main).getByRole("button", { name: /^ORD-20931/ }));

    const popover = await screen.findByRole("dialog", { name: "Order ORD-20931" });
    expect(popover).toHaveTextContent("OrderDelivered · Placed 2 Oct 2026");
  });

  it("opens from the order citation marker of the draft", async () => {
    const { user, main } = await openWorkspace();

    await user.click(getOrderMarker(main));

    expect(await screen.findByRole("dialog", { name: "Orders of this customer" })).toBeVisible();
  });

  it("selects the ticket's order again when the marker opens it after another order was chosen", async () => {
    const { user, main } = await openWorkspace();
    await user.click(within(main).getByRole("button", { name: /^ORD-20931 Delivered/ }));
    const popover = await screen.findByRole("dialog", { name: "Orders of this customer" });
    await user.click(within(popover).getByRole("button", { name: /ORD-20990/ }));
    await user.keyboard("{Escape}");

    await user.click(getOrderMarker(main));

    const reopened = await screen.findByRole("dialog", { name: "Orders of this customer" });
    expect(within(reopened).getByRole("button", { name: /ORD-20931 This ticket/ })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(within(reopened).getByRole("button", { name: /ORD-20990/ })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
    expect(reopened).toHaveTextContent("Ship to12 Sample Street, Sample City");
  });

  it("returns the focus to the order marker that opened it (UI-30)", async () => {
    const { user, main } = await openWorkspace();
    await user.click(getOrderMarker(main));
    await screen.findByRole("dialog", { name: "Orders of this customer" });

    await user.keyboard("{Escape}");

    await waitFor(() => {
      expect(getOrderMarker(main)).toHaveFocus();
    });
  });
});
