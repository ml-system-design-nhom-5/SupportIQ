/**
 * The public API of the console reports feature (console UI design, Reports; UI-44): the Reports
 * page of managers, its path, and the rule of who reads the report.
 */
export { ReportsPage } from "@/features/console-reports/components/reports-page";
export { canReadReports } from "@/features/console-reports/model/reports-access";
export { REPORTS_PATH, REPORTS_ROUTE } from "@/features/console-reports/model/reports-paths";
