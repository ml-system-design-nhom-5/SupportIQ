/**
 * The versions in use as the Versions screen shows them (admin UI design, Versions in use): the
 * build of `backend`, and the release and asset versions that `ai-service` serves (DATA-56), or
 * that they are unknown because `backend` could not read them. Every value is Internal data. A body
 * without a member that the contract requires stops the mapping, so it never shows as versions
 * (CODE-32).
 */
import type { AiServiceStatusName } from "@/design-system";
import type {
  AdminVersionsContract,
  AssetVersionsContract,
} from "@/features/admin-versions/api/contract-types";
import { requireMembers } from "@/features/backend-requests";

/** The terms of the rows of `ai-service`, in the order of `AssetVersions` (admin UI design). */
const assetTerms: readonly (readonly [keyof AssetVersions, string])[] = [
  ["releaseId", "Release"],
  ["modelVersion", "Model artifact"],
  ["kbVersion", "KB"],
  ["mappingVersion", "Document-to-intent mapping"],
  ["promptVersion", "Prompts"],
  ["routingVersion", "Routing configuration"],
  ["indexVersion", "Retrieval index"],
];

/** An `AdminVersionsView` with `ai_service_versions`, as the contract sends it when available. */
type AvailableVersionsContract = AdminVersionsContract & {
  readonly ai_service_versions: AssetVersionsContract;
};

/** The release and asset versions that `ai-service` serves (`AssetVersions`). */
export type AssetVersions = {
  readonly releaseId: string;
  readonly modelVersion: string;
  readonly kbVersion: string;
  readonly mappingVersion: string;
  readonly promptVersion: string;
  readonly routingVersion: string;
  readonly indexVersion: string;
};

/**
 * What `backend` could read of `ai-service`.
 * `available`: `ai-service` answered in time, so its versions are known.
 * `unavailable`: it did not answer in time, it answered with an error, or `backend` sent a status
 * that this version does not know (CON-22), so its versions are unknown.
 */
export type AiServiceVersions =
  | { readonly status: "available"; readonly assetVersions: AssetVersions }
  | { readonly status: "unavailable" };

/** The versions in use. */
export type VersionsInUse = {
  /** The build version of `backend`, such as a commit SHA. */
  readonly backendVersion: string;
  readonly aiService: AiServiceVersions;
};

/** One row of the `ai-service` panel: an asset and its version. */
export type AssetVersionRow = {
  readonly term: string;
  /** Absent while the version is unknown. */
  readonly version?: string;
};

/**
 * Map the body of `getAdminVersions`.
 *
 * @param view - An `AdminVersionsView`.
 * @returns The build of `backend` and what `backend` could read of `ai-service`.
 */
export function toVersionsInUse(view: AdminVersionsContract): VersionsInUse {
  requireMembers(view, ["backend_version", "ai_service_status"]);
  return { backendVersion: view.backend_version, aiService: toAiServiceVersions(view) };
}

/**
 * Map the status of `ai-service`.
 *
 * @param value - The `ai_service_status` of an `AdminVersionsView`.
 * @returns The status, or `unavailable` for a value that this version does not know (CON-22).
 */
export function toAiServiceStatus(value: string): AiServiceStatusName {
  return value === "available" ? "available" : "unavailable";
}

/**
 * Build the rows of the `ai-service` panel.
 *
 * @param aiService - What `backend` could read of `ai-service`.
 * @returns One row per asset, in the order of `AssetVersions`, each with its version while
 *   `ai-service` is available and without one otherwise.
 */
export function buildAssetVersionRows(aiService: AiServiceVersions): readonly AssetVersionRow[] {
  return assetTerms.map(([key, term]) =>
    aiService.status === "available" ? { term, version: aiService.assetVersions[key] } : { term },
  );
}

/**
 * Map what `backend` could read of `ai-service`.
 *
 * @param view - An `AdminVersionsView` with its required members.
 * @returns The versions when the status is `available`, and nothing otherwise.
 * @throws TypeError when the status is `available` and the versions are missing.
 */
function toAiServiceVersions(view: AdminVersionsContract): AiServiceVersions {
  if (toAiServiceStatus(view.ai_service_status) === "unavailable") {
    return { status: "unavailable" };
  }
  requireAssetVersions(view);
  return { status: "available", assetVersions: toAssetVersions(view.ai_service_versions) };
}

/**
 * Stop at an `available` body without `ai_service_versions`: the contract sends them exactly when
 * the status is `available`.
 *
 * @param view - An `AdminVersionsView` whose status is `available`.
 * @throws TypeError naming `ai_service_versions` when the body lacks it.
 */
function requireAssetVersions(
  view: AdminVersionsContract,
): asserts view is AvailableVersionsContract {
  requireMembers(view, ["ai_service_versions"]);
}

/**
 * Map the release and asset versions.
 *
 * @param versions - An `AssetVersions`.
 * @returns The view model.
 */
function toAssetVersions(versions: AssetVersionsContract): AssetVersions {
  requireMembers(versions, [
    "release_id",
    "model_version",
    "kb_version",
    "mapping_version",
    "prompt_version",
    "routing_version",
    "index_version",
  ]);
  return {
    releaseId: versions.release_id,
    modelVersion: versions.model_version,
    kbVersion: versions.kb_version,
    mappingVersion: versions.mapping_version,
    promptVersion: versions.prompt_version,
    routingVersion: versions.routing_version,
    indexVersion: versions.index_version,
  };
}
