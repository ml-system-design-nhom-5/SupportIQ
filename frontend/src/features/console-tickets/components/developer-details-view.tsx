/**
 * The "Developer details" panel at the bottom of the AI sidebar (console UI design, Workspace
 * regions; UI-35), collapsed until opened: the trace ID with its Grafana link when one is set up,
 * the suggestion and its trigger, and for each part the raw status, the reason codes, the
 * versions, and the latencies. Values are rendered as text, as `backend` sent them; IDs and
 * versions are in monospace (UI-08).
 */
import { Code } from "lucide-react";

import {
  DescriptionList,
  DisclosurePanel,
  Heading,
  Identifier,
  Stack,
  TraceId,
} from "@/design-system";
import {
  buildDetailLines,
  type DetailLine,
  type DeveloperDetails,
} from "@/features/console-tickets/model/developer-details";

/** Props of {@link DeveloperDetailsView}. */
export type DeveloperDetailsViewProps = {
  readonly details: DeveloperDetails;
  /** The link to the trace in Grafana; absent when no Grafana is set up. */
  readonly traceHref?: string;
};

/**
 * Render the developer details of a suggestion.
 *
 * @param props - The details and the trace link.
 * @returns The collapsed panel.
 */
export function DeveloperDetailsView({ details, traceHref }: DeveloperDetailsViewProps) {
  const parts = [
    { title: "Analysis", lines: buildDetailLines(details.analysis, details.analysisWarningCodes) },
    { title: "Draft", lines: buildDetailLines(details.draft) },
  ];
  return (
    <DisclosurePanel title="Developer details" icon={Code}>
      <Stack gap="3">
        <TraceId traceId={details.traceId} {...(traceHref === undefined ? {} : { traceHref })} />
        <DescriptionList
          items={[
            { term: "Suggestion", description: <Identifier>{details.suggestionId}</Identifier> },
            { term: "Trigger", description: details.trigger },
          ]}
        />
        {parts.map((part) => (
          <Stack key={part.title} as="section" label={part.title} gap="2">
            <Heading level={3} size="item">
              {part.title}
            </Heading>
            <DescriptionList items={part.lines.map(toDescriptionItem)} />
          </Stack>
        ))}
      </Stack>
    </DisclosurePanel>
  );
}

/**
 * Turn a line into an item of the description list.
 *
 * @param line - The term and its value.
 * @returns The item, with an identifier in monospace.
 */
function toDescriptionItem(line: DetailLine) {
  return {
    term: line.term,
    description: line.isIdentifier ? <Identifier>{line.value}</Identifier> : line.value,
  };
}
