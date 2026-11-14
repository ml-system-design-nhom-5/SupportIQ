import { screen, within } from "@testing-library/react";
import type { UserEvent } from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { openConsole, TICKET_PATH, workspaceExample } from "@/test/console-screen";
import { createMemoryStorage } from "@/test/memory-storage";
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
 * Open the account menu of the app bar.
 *
 * @param user - The user-event instance.
 * @returns The menu.
 */
async function openAccountMenu(user: UserEvent): Promise<HTMLElement> {
  const bar = await screen.findByRole("banner");
  await user.click(within(bar).getByRole("button", { expanded: false }));
  return screen.findByRole("menu");
}

/**
 * Wait until the workspace shows its draft, so its sidebar is complete.
 *
 * @returns The region of the AI draft.
 */
async function waitForWorkspace(): Promise<HTMLElement> {
  return screen.findByRole("region", { name: "AI draft" });
}

describe("Dev mode where it is not available (UI-35)", () => {
  it("offers no switch and shows no details, even when the browser kept the switch on", async () => {
    const { storage } = createMemoryStorage({ [STAFF_KEY]: "on" });
    const { user } = openConsole(TICKET_PATH, { preferenceStorage: storage });
    await waitForWorkspace();

    expect(screen.queryByRole("button", { name: "Developer details" })).not.toBeInTheDocument();
    const menu = await openAccountMenu(user);
    expect(within(menu).queryByRole("menuitemcheckbox")).not.toBeInTheDocument();
  });
});

describe("Dev mode where it is available (UI-35)", () => {
  it("adds the developer details once staff switch it on, and keeps the choice", async () => {
    const { storage, stored } = createMemoryStorage();
    const { user } = openConsole(TICKET_PATH, {
      settings: devModeSettings,
      preferenceStorage: storage,
    });
    await waitForWorkspace();
    expect(screen.queryByRole("button", { name: "Developer details" })).not.toBeInTheDocument();

    const menu = await openAccountMenu(user);
    await user.click(within(menu).getByRole("menuitemcheckbox", { name: "Dev mode" }));
    await user.click(await screen.findByRole("button", { name: "Developer details" }));

    const draft = screen.getByRole("region", { name: "Draft" });
    expect(screen.getByText(TRACE_ID)).toBeVisible();
    expect(draft).toHaveTextContent("draft_ready");
    expect(draft).toHaveTextContent("release-2026-11-12-sample");
    expect(draft).toHaveTextContent("3,205 ms");
    expect(screen.getByRole("region", { name: "Analysis" })).toHaveTextContent(
      "source_review_overdue",
    );
    expect(stored.get(STAFF_KEY)).toBe("on");
  });

  it("removes the details from the page when staff switch it off", async () => {
    const { storage, stored } = createMemoryStorage({ [STAFF_KEY]: "on" });
    const { user } = openConsole(TICKET_PATH, {
      settings: devModeSettings,
      preferenceStorage: storage,
    });
    await screen.findByRole("button", { name: "Developer details" });

    const menu = await openAccountMenu(user);
    const item = within(menu).getByRole("menuitemcheckbox", { name: "Dev mode" });
    expect(item).toHaveAttribute("aria-checked", "true");
    await user.click(item);

    expect(screen.queryByRole("button", { name: "Developer details" })).not.toBeInTheDocument();
    expect(stored.get(STAFF_KEY)).toBe("off");
  });

  it("never gives one account the choice of another", async () => {
    const { storage } = createMemoryStorage({ [MANAGER_KEY]: "on" });
    const { user } = openConsole(TICKET_PATH, {
      settings: devModeSettings,
      preferenceStorage: storage,
    });
    await waitForWorkspace();

    expect(screen.queryByRole("button", { name: "Developer details" })).not.toBeInTheDocument();
    const menu = await openAccountMenu(user);
    expect(within(menu).getByRole("menuitemcheckbox", { name: "Dev mode" })).toHaveAttribute(
      "aria-checked",
      "false",
    );
  });

  it("links the trace to Grafana when a link is set up", async () => {
    const { storage } = createMemoryStorage({ [STAFF_KEY]: "on" });
    const { user } = openConsole(TICKET_PATH, {
      settings: { ...devModeSettings, grafanaTraceUrl: "https://grafana.example/t/{trace_id}" },
      preferenceStorage: storage,
    });

    await user.click(await screen.findByRole("button", { name: "Developer details" }));

    expect(screen.getByRole("link", { name: /^Open in Grafana/ })).toHaveAttribute(
      "href",
      `https://grafana.example/t/${TRACE_ID}`,
    );
  });

  it("shows only the raw status of a part that has no call yet", async () => {
    const { storage } = createMemoryStorage({ [STAFF_KEY]: "on" });
    const { user } = openConsole(TICKET_PATH, {
      settings: devModeSettings,
      preferenceStorage: storage,
      workspace: [workspaceExample("suggestion-pending")],
    });

    await user.click(await screen.findByRole("button", { name: "Developer details" }));

    const draft = screen.getByRole("region", { name: "Draft" });
    expect(draft).toHaveTextContent("pending");
    expect(draft).not.toHaveTextContent("Release");
    expect(draft).not.toHaveTextContent("ms");
    expect(screen.queryByRole("link", { name: /^Open in Grafana/ })).not.toBeInTheDocument();
  });
});
