/**
 * The sources of the suggestion (UI-20; console UI design, Sources): every KB document version that
 * the analysis retrieved, with its citation number, validity, and effective period. Opening one
 * shows its full text in a side sheet.
 */
import { FileText } from "lucide-react";

import {
  Panel,
  PanelHeader,
  PanelSection,
  presentationByDocumentValidity,
  SourceList,
  type SourceListItem,
  Text,
} from "@/design-system";
import type { Source } from "@/features/console-tickets/model/sources";

/** Props of {@link SourcesPanel}. */
type SourcesPanelProps = {
  readonly sources: readonly Source[];
  readonly onOpenSource: (source: Source, opener: HTMLElement) => void;
};

/**
 * Render the sources.
 *
 * @param props - The sources and the handler that opens one.
 * @returns The panel.
 */
export function SourcesPanel({ sources, onOpenSource }: SourcesPanelProps) {
  const sourceByKey = new Map(sources.map((source) => [source.key, source]));
  return (
    <Panel density="compact" as="section" label="Sources">
      <PanelHeader
        icon={FileText}
        level={2}
        title="Sources"
        trailing={
          <Text size="xs" tone="muted">
            Open a source to read the full version
          </Text>
        }
      />
      <PanelSection>
        {sources.length === 0 ? (
          <Text tone="muted">No document in effect supports this request.</Text>
        ) : (
          <SourceList
            sources={sources.map(toSourceListItem)}
            onOpen={(key, opener) => {
              const source = sourceByKey.get(key);
              if (source !== undefined) {
                onOpenSource(source, opener);
              }
            }}
          />
        )}
      </PanelSection>
    </Panel>
  );
}

/**
 * Map a source to an item of the source list.
 *
 * @param source - The source.
 * @returns The item, with the presentation of its validity (UI-12).
 */
function toSourceListItem(source: Source): SourceListItem {
  return {
    key: source.key,
    ...(source.number === undefined ? {} : { number: source.number }),
    title: source.title,
    documentId: source.documentId,
    version: source.version,
    validity: presentationByDocumentValidity[source.validity],
    period: source.period,
  };
}
