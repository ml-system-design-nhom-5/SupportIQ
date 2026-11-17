import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { getConsoleTicketRoute } from "@/test/backend-routes";
import { openConsole, TICKET_PATH, workspaceExample } from "@/test/console-screen";
import { createMemoryStorage } from "@/test/memory-storage";

/** The key of the column layout of the staff account of the session example. */
const STAFF_KEY = "supportiq.console-columns.9a7d3e21-6c4b-4f8e-b1a2-3c5d7e9f0a12";

/** The name of the mark of a hidden staff note. */
const STAFF_NOTE_MARK = "Note for staff in AI details";

/**
 * Wait until the workspace of the ticket has loaded, which replaces the loading workspace.
 *
 * @returns The ticket heading.
 */
async function waitForWorkspace(): Promise<HTMLElement> {
  return screen.findByRole("heading", { level: 1, name: "Ticket TCK-1042" });
}

/**
 * Store a layout for the staff account.
 *
 * @param isInboxCollapsed - Whether the inbox is collapsed.
 * @param isAiDetailsCollapsed - Whether the AI sidebar is collapsed.
 * @returns The browser storage that holds the layout.
 */
function storeLayout(isInboxCollapsed: boolean, isAiDetailsCollapsed: boolean) {
  return createMemoryStorage({
    [STAFF_KEY]: JSON.stringify({
      inbox: { width: 272, isCollapsed: isInboxCollapsed },
      aiDetails: { width: 340, isCollapsed: isAiDetailsCollapsed },
    }),
  });
}

describe("The console columns (console UI design, Column controls)", () => {
  it("collapses the inbox to a rail whose Open inbox opens it again", async () => {
    const { user } = openConsole(TICKET_PATH);

    await user.click(await screen.findByRole("button", { name: "Collapse inbox", expanded: true }));
    await user.click(screen.getByRole("button", { name: "Open inbox", expanded: false }));

    expect(screen.getByRole("button", { name: "Collapse inbox" })).toBeInTheDocument();
  });

  it("collapses the AI sidebar to a rail whose Open AI details opens it again", async () => {
    const { user } = openConsole(TICKET_PATH);
    await waitForWorkspace();

    await user.click(screen.getByRole("button", { name: "Collapse AI details", expanded: true }));
    await user.click(screen.getByRole("button", { name: "Open AI details", expanded: false }));

    expect(screen.getByRole("button", { name: "Collapse AI details" })).toBeInTheDocument();
  });

  it("collapses the AI sidebar with Enter on its splitter", async () => {
    const { user } = openConsole(TICKET_PATH);
    await waitForWorkspace();

    screen.getByRole("separator", { name: "Resize AI details" }).focus();
    await user.keyboard("{Enter}");

    expect(screen.getByRole("button", { name: "Open AI details" })).toBeInTheDocument();
  });

  it("keeps the layout under the account in the browser", async () => {
    const memory = createMemoryStorage();
    const { user } = openConsole(TICKET_PATH, { preferenceStorage: memory.storage });

    await user.click(await screen.findByRole("button", { name: "Collapse inbox" }));

    expect(JSON.parse(memory.stored.get(STAFF_KEY) ?? "")).toEqual({
      inbox: { width: 272, isCollapsed: true },
      aiDetails: { width: 340, isCollapsed: false },
    });
  });

  it("keeps the collapsed columns when staff open another ticket (UI-15)", async () => {
    const { user, router, backend } = openConsole(TICKET_PATH);
    await waitForWorkspace();
    await user.click(screen.getByRole("button", { name: "Collapse inbox" }));
    await user.click(screen.getByRole("button", { name: "Collapse AI details" }));

    await router.navigate("/console/tickets/TCK-1038");
    await waitFor(() => {
      expect(backend.requestsTo(getConsoleTicketRoute).at(-1)?.path).toBe(
        "/v1/console/tickets/TCK-1038",
      );
    });
    await waitForWorkspace();

    expect(screen.getByRole("button", { name: "Open inbox" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open AI details" })).toBeInTheDocument();
  });

  it("opens with the layout that the browser kept, as after a reload", async () => {
    openConsole(TICKET_PATH, { preferenceStorage: storeLayout(true, true).storage });
    await waitForWorkspace();

    expect(screen.getByRole("button", { name: "Open inbox" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open AI details" })).toBeInTheDocument();
  });

  it("uses the default layout, which still collapses, when the browser refuses storage", async () => {
    const refusingStorage = {
      getItem: () => {
        throw new DOMException("The storage is blocked.", "SecurityError");
      },
      setItem: () => {
        throw new DOMException("The storage is blocked.", "SecurityError");
      },
    };
    const { user } = openConsole(TICKET_PATH, { preferenceStorage: refusingStorage });

    await user.click(await screen.findByRole("button", { name: "Collapse inbox" }));

    expect(screen.getByRole("button", { name: "Open inbox" })).toBeInTheDocument();
  });
});

describe("The mark of a hidden staff note (console UI design, Column controls)", () => {
  it("shows on the rail of the collapsed AI sidebar while the draft has a staff note", async () => {
    openConsole(TICKET_PATH, {
      workspace: [workspaceExample("abstained-low-confidence")],
      preferenceStorage: storeLayout(false, true).storage,
    });

    expect(await screen.findByRole("img", { name: STAFF_NOTE_MARK })).toBeInTheDocument();
  });

  it("is absent when the draft has no staff note", async () => {
    openConsole(TICKET_PATH, { preferenceStorage: storeLayout(false, true).storage });
    await waitForWorkspace();

    expect(screen.queryByRole("img", { name: STAFF_NOTE_MARK })).not.toBeInTheDocument();
  });

  it("is absent while the AI sidebar is open, which shows the note itself", async () => {
    openConsole(TICKET_PATH, { workspace: [workspaceExample("abstained-low-confidence")] });
    await screen.findByRole("region", { name: "For staff only" });

    expect(screen.queryByRole("img", { name: STAFF_NOTE_MARK })).not.toBeInTheDocument();
  });
});
