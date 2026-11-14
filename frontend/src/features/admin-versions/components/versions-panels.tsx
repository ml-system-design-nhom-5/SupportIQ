/**
 * The versions in use (admin UI design, Versions in use; admin-versions.png and
 * admin-versions-unavailable.png): a `danger` banner while `ai-service` cannot be reached, the
 * `ai-service` panel with its status and one row per asset, and the `backend` panel with its
 * build. Versions are identifiers in monospace (UI-08); a version that is unknown says so in muted
 * text. Each panel is a section named by its heading text, so a screen reader can jump to it.
 */
import type { ReactNode } from "react";

import {
  type DescriptionItem,
  DescriptionList,
  Identifier,
  Panel,
  PanelHeader,
  PanelSection,
  presentationByAiServiceStatus,
  StatusBadge,
  StatusBanner,
  Text,
} from "@/design-system";
import {
  type AssetVersionRow,
  buildAssetVersionRows,
  type VersionsInUse,
} from "@/features/admin-versions/model/versions-in-use";

/** The value of a version that `backend` could not read. */
const UNKNOWN_VERSION_TEXT = "Unknown";

/** Props of {@link VersionsPanels}. */
export type VersionsPanelsProps = {
  readonly versions: VersionsInUse;
};

/** Props of {@link VersionPanel}. */
type VersionPanelProps = {
  /** The name of the component, such as `ai-service`: the heading and the section's name. */
  readonly title: string;
  /** The status badge at the end of the header, when the component has a status. */
  readonly status?: ReactNode;
  readonly items: readonly DescriptionItem[];
};

/**
 * Render the versions in use.
 *
 * @param props - The versions.
 * @returns The banner when `ai-service` cannot be reached, then the two panels.
 */
export function VersionsPanels({ versions }: VersionsPanelsProps) {
  const { aiService } = versions;
  const presentation = presentationByAiServiceStatus[aiService.status];
  return (
    <>
      {aiService.status === "available" ? null : (
        <StatusBanner tone="danger" icon={presentation.icon} lead="ai-service cannot be reached.">
          Its versions are unknown. Reload this page later.
        </StatusBanner>
      )}
      <VersionPanel
        title="ai-service"
        status={<StatusBadge presentation={presentation} />}
        items={buildAssetVersionRows(aiService).map(toDescriptionItem)}
      />
      <VersionPanel
        title="backend"
        items={[{ term: "Build", description: <Identifier>{versions.backendVersion}</Identifier> }]}
      />
    </>
  );
}

/**
 * Render the panel of one component: a header with its name and status, then its versions.
 *
 * @param props - The name, the status badge, and the rows.
 * @returns The panel, as a named section.
 */
function VersionPanel({ title, status, items }: VersionPanelProps) {
  return (
    <Panel as="section" label={title}>
      <PanelHeader level={2} title={title} trailing={status} />
      <PanelSection>
        <DescriptionList items={items} />
      </PanelSection>
    </Panel>
  );
}

/**
 * Turn a row of `ai-service` into an item of the description list.
 *
 * @param row - The asset and its version.
 * @returns The item: the version in monospace, or "Unknown" in muted text.
 */
function toDescriptionItem(row: AssetVersionRow): DescriptionItem {
  return {
    term: row.term,
    description:
      row.version === undefined ? (
        <Text tone="muted">{UNKNOWN_VERSION_TEXT}</Text>
      ) : (
        <Identifier>{row.version}</Identifier>
      ),
  };
}
