import { screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { switchDevMode } from "@/test/account-menu";
import { readExampleWith } from "@/test/contract-examples";
import { adminDevModeSettings } from "@/test/dev-mode-settings";
import { openVersions } from "@/test/versions-screen";

/**
 * Open the Versions screen where dev mode is available, switch dev mode on, and open the details.
 *
 * @param body - The body of `getAdminVersions`; the `ai-service-available` example by default.
 * @returns The rendered app and the open panel.
 */
async function openDeveloperDetails(body?: unknown) {
  const rendered = openVersions({
    settings: adminDevModeSettings,
    ...(body === undefined ? {} : { versions: [{ kind: "body", status: 200, body }] }),
  });
  await screen.findByRole("region", { name: "ai-service" });
  await switchDevMode(rendered.user);
  await rendered.user.click(await screen.findByRole("button", { name: "Developer details" }));
  return rendered;
}

describe("The Versions screen in dev mode (admin UI design, Developer details; UI-35)", () => {
  it("shows the raw ai_service_status, also one that this version shows as Unavailable", async () => {
    await openDeveloperDetails(
      readExampleWith("getAdminVersions", "ai-service-unavailable", {
        ai_service_status: "a_later_status",
      }),
    );

    expect(screen.getByRole("region", { name: "ai-service" })).toHaveTextContent("Unavailable");
    expect(screen.getByText("a_later_status")).toBeVisible();
    expect(screen.getByRole("region", { name: "Frontend" })).toBeVisible();
  });

  it("copies the version block for a bug report", async () => {
    const { user } = await openDeveloperDetails();
    const writeText = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue();
    const block = screen.getByRole("region", { name: "Version block" });

    await user.click(within(block).getByRole("button", { name: "Copy text" }));

    expect(writeText).toHaveBeenCalledWith(
      expect.stringMatching(/^backend_version: .+\nai_service_status: available\nrelease_id: /),
    );
  });

  it("stays as it is while dev mode is off", async () => {
    openVersions({ settings: adminDevModeSettings });
    await screen.findByRole("region", { name: "ai-service" });

    expect(screen.queryByRole("button", { name: "Developer details" })).not.toBeInTheDocument();
  });
});
