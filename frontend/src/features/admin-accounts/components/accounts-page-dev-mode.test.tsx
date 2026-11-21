import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { switchDevMode } from "@/test/account-menu";
import { findRow, openAccounts } from "@/test/accounts-screen";
import { adminDevModeSettings, SYSTEM_OVERVIEW_URL } from "@/test/dev-mode-settings";

describe("The Accounts screen in dev mode (admin UI design, Developer details; UI-35)", () => {
  it("shows the raw role and is_active of each row", async () => {
    const { user } = openAccounts({ settings: adminDevModeSettings });
    await findRow("Mai Nguyen");

    await switchDevMode(user);

    expect(await screen.findByRole("columnheader", { name: "Raw values" })).toBeVisible();
    expect(await findRow("Mai Nguyen")).toHaveTextContent("role: staff · is_active: true");
  });

  it("shows the build version, the settings, and the dashboard links of frontend", async () => {
    const { user } = openAccounts({ settings: adminDevModeSettings });
    await findRow("Mai Nguyen");
    await switchDevMode(user);

    await user.click(await screen.findByRole("button", { name: "Developer details" }));

    const frontend = screen.getByRole("region", { name: "Frontend" });
    expect(frontend).toHaveTextContent("Build versioncc489d3");
    expect(frontend).toHaveTextContent("VITE_DEV_MODEtrue");
    expect(frontend).toHaveTextContent("VITE_GRAFANA_TRACE_URLNot set");
    expect(
      within(frontend).getByRole("link", { name: "System overview (opens in a new tab)" }),
    ).toHaveAttribute("href", SYSTEM_OVERVIEW_URL);
    expect(within(frontend).queryByRole("link", { name: /AI pipeline/ })).not.toBeInTheDocument();
  });

  it("stays as it is while dev mode is off", async () => {
    openAccounts({ settings: adminDevModeSettings });
    await findRow("Mai Nguyen");

    expect(screen.queryByRole("columnheader", { name: "Raw values" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Developer details" })).not.toBeInTheDocument();
  });
});
