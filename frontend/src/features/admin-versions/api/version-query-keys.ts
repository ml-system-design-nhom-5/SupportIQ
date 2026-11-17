/**
 * The query keys of the admin versions feature (TS-19).
 */

/** The one key factory of the admin versions feature. */
export const versionQueryKeys = {
  all: ["admin-versions"] as const,
  versions: () => [...versionQueryKeys.all, "versions"] as const,
};
