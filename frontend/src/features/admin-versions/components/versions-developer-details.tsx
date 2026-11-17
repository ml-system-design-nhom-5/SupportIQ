/**
 * What dev mode adds to the Versions screen (admin UI design, Developer details in the admin area;
 * UI-35): the raw `ai_service_status`, also a value that this version does not know and shows as
 * Unavailable (CON-22), and the version block to copy for a bug report.
 */
import { CopyableText, DescriptionList, Identifier } from "@/design-system";
import {
  buildVersionBlock,
  type VersionsInUse,
} from "@/features/admin-versions/model/versions-in-use";
import { DevModeDetailsPanel } from "@/features/session";

/** Props of {@link VersionsDeveloperDetails}. */
export type VersionsDeveloperDetailsProps = {
  readonly versions: VersionsInUse;
};

/**
 * Render the developer details of the versions, while dev mode is on.
 *
 * @param props - The versions in use.
 * @returns The panel, or nothing while dev mode is off.
 */
export function VersionsDeveloperDetails({ versions }: VersionsDeveloperDetailsProps) {
  return (
    <DevModeDetailsPanel>
      <DescriptionList
        items={[
          {
            term: "ai_service_status",
            description: <Identifier>{versions.rawStatus}</Identifier>,
          },
        ]}
      />
      <CopyableText label="Version block">{buildVersionBlock(versions)}</CopyableText>
    </DevModeDetailsPanel>
  );
}
