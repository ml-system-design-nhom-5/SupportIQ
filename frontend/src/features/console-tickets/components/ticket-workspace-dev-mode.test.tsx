import { screen, within } from "@testing-library/react";
import type { UserEvent } from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { openAccountMenu, switchDevMode } from "@/test/account-menu";
import { openConsole, TICKET_PATH, workspaceExample } from "@/test/console-screen";
import { createMemoryStorage, type MemoryStorage } from "@/test/memory-storage";
import { testSettings } from "@/test/render-app";

/** The key of the dev mode switch of the staff account of the session example. */
const STAFF_KEY = "supportiq.dev-mode.9a7d3e21-6c4b-4f8e-b1a2-3c5d7e9f0a12";

/** The key of the dev mode switch of the manager account of the session example. */
const MANAGER_KEY = "supportiq.dev-mode.c3e5a7b9-1d2f-4a6c-8e0b-2d4f6a8c0e14";

/** The trace ID of the draft-ready example. */
const TRACE_ID = "4bf92f3577b34da6a3ce929d0e0e4736";

/** Settings where dev mode is available. */
const devModeSettings = { ...testSettings, isDevModeAvailable: true };

/**
 * Wait until the workspace shows its draft, so its sidebar is complete.
 *
 * @returns The region of the AI draft.
 */
async function waitForWorkspace(): Promise<HTMLElement> {
  return screen.findByRole("region", { name: "AI draft" });
}

/**
 * Open the draft-ready workspace as staff where dev mode is available.
 *
 * @param memory - The browser storage, with what it already holds.
 * @returns The rendered app.
 */
function openWithDevMode(memory: MemoryStorage) {
  return openConsole(TICKET_PATH, { settings: devModeSettings, preferenceStorage: memory.storage });
}

/**
 * Open the developer details, once they are on the page.
 *
 * @param user - The user-event instance.
 */
async function openDeveloperDetails(user: UserEvent): Promise<void> {
  await user.click(await screen.findByRole("button", { name: "Developer details" }));
}

/**
 * List the terms of a part of the developer details.
 *
 * @param part - "Analysis" or "Draft".
 * @returns The terms, in order.
 */
function readTerms(part: string): readonly (string | null)[] {
  const region = screen.getByRole("region", { name: part });
  return within(region)
    .getAllByRole("term")
    .map((term) => term.textContent);
}

describe("Dev mode where it is not available (UI-35)", () => {
  it("shows no details, even when the browser kept the switch on", async () => {
    openConsole(TICKET_PATH, {
      preferenceStorage: createMemoryStorage({ [STAFF_KEY]: "on" }).storage,
    });
    await waitForWorkspace();

    expect(screen.queryByRole("button", { name: "Developer details" })).not.toBeInTheDocument();
  });

  it("offers no switch in the account menu", async () => {
    const { user } = openConsole(TICKET_PATH);
    await waitForWorkspace();

    const menu = await openAccountMenu(user);

    expect(within(menu).queryByRole("menuitemcheckbox")).not.toBeInTheDocument();
  });
});

describe("Switching dev mode where it is available (UI-35)", () => {
  it("adds the developer details once staff switch it on", async () => {
    const { user } = openWithDevMode(createMemoryStorage());
    await waitForWorkspace();
    expect(screen.queryByRole("button", { name: "Developer details" })).not.toBeInTheDocument();

    await switchDevMode(user);

    expect(await screen.findByRole("button", { name: "Developer details" })).toBeVisible();
  });

  it("keeps the choice of the account in the browser", async () => {
    const memory = createMemoryStorage();
    const { user } = openWithDevMode(memory);
    await waitForWorkspace();

    await switchDevMode(user);

    expect(memory.stored.get(STAFF_KEY)).toBe("on");
  });

  it("removes the details from the page when staff switch it off", async () => {
    const memory = createMemoryStorage({ [STAFF_KEY]: "on" });
    const { user } = openWithDevMode(memory);
    await screen.findByRole("button", { name: "Developer details" });

    await switchDevMode(user);

    expect(screen.queryByRole("button", { name: "Developer details" })).not.toBeInTheDocument();
    expect(memory.stored.get(STAFF_KEY)).toBe("off");
  });

  it("never gives one account the choice of another", async () => {
    const { user } = openWithDevMode(createMemoryStorage({ [MANAGER_KEY]: "on" }));
    await waitForWorkspace();

    expect(screen.queryByRole("button", { name: "Developer details" })).not.toBeInTheDocument();
    const menu = await openAccountMenu(user);
    expect(within(menu).getByRole("menuitemcheckbox", { name: "Dev mode" })).toHaveAttribute(
      "aria-checked",
      "false",
    );
  });
});

describe("The developer details of a suggestion (UI-35)", () => {
  it("show the trace, the raw status, the versions, and the latencies", async () => {
    const { user } = openWithDevMode(createMemoryStorage({ [STAFF_KEY]: "on" }));

    await openDeveloperDetails(user);

    const draft = screen.getByRole("region", { name: "Draft" });
    expect(screen.getByText(TRACE_ID)).toBeVisible();
    expect(draft).toHaveTextContent("draft_ready");
    expect(draft).toHaveTextContent("release-2026-11-12-sample");
    expect(draft).toHaveTextContent("3,205 ms");
  });

  it("show the warning codes of the analysis", async () => {
    const { user } = openWithDevMode(createMemoryStorage({ [STAFF_KEY]: "on" }));

    await openDeveloperDetails(user);

    expect(screen.getByRole("region", { name: "Analysis" })).toHaveTextContent(
      "source_review_overdue",
    );
  });

  it("link the trace to Grafana when a link is set up", async () => {
    const { user } = openConsole(TICKET_PATH, {
      settings: { ...devModeSettings, grafanaTraceUrl: "https://grafana.example/t/{trace_id}" },
      preferenceStorage: createMemoryStorage({ [STAFF_KEY]: "on" }).storage,
    });

    await openDeveloperDetails(user);

    expect(screen.getByRole("link", { name: /^Open in Grafana/ })).toHaveAttribute(
      "href",
      `https://grafana.example/t/${TRACE_ID}`,
    );
  });

  it("have no Grafana link when none is set up", async () => {
    const { user } = openWithDevMode(createMemoryStorage({ [STAFF_KEY]: "on" }));

    await openDeveloperDetails(user);

    expect(screen.queryByRole("link", { name: /^Open in Grafana/ })).not.toBeInTheDocument();
  });

  it("show only the raw status of a part that is pending", async () => {
    const { user } = openConsole(TICKET_PATH, {
      settings: devModeSettings,
      preferenceStorage: createMemoryStorage({ [STAFF_KEY]: "on" }).storage,
      workspace: [workspaceExample("suggestion-pending")],
    });

    await openDeveloperDetails(user);

    expect(readTerms("Draft")).toEqual(["Status"]);
    expect(screen.getByRole("region", { name: "Draft" })).toHaveTextContent("pending");
  });
});
