/**
 * Settings of the tests of the developer details in the admin area: dev mode is available, and
 * frontend has a build version, a dashboard link, and two settings to list (admin UI design).
 */
import type { FrontendSettings } from "@/app/settings";
import { testSettings } from "@/test/render-app";

/** The link to the dashboard System overview of the local stack. */
export const SYSTEM_OVERVIEW_URL = "http://localhost:3000/d/system-overview";

/** Settings where dev mode is available, with the details of frontend. */
export const adminDevModeSettings: FrontendSettings = {
  ...testSettings,
  isDevModeAvailable: true,
  frontendBuildVersion: "cc489d3",
  grafanaSystemOverviewUrl: SYSTEM_OVERVIEW_URL,
  viteSettings: [{ name: "VITE_DEV_MODE", value: "true" }, { name: "VITE_GRAFANA_TRACE_URL" }],
};
