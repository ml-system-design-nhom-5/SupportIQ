/**
 * The contract types of the versions operation, for the mappings in model/ (TS-09).
 */
import type { components } from "@/api/generated/backend";

/** `AdminVersionsView`: the body of `getAdminVersions`. */
export type AdminVersionsContract = components["schemas"]["AdminVersionsView"];

/** `AssetVersions`: the release and asset versions that `ai-service` serves (DATA-56). */
export type AssetVersionsContract = components["schemas"]["AssetVersions"];
