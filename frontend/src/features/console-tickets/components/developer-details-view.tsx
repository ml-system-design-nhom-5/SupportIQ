/**
 * The "Developer details" panel at the bottom of the AI sidebar (console UI design, Workspace
 * regions; UI-35), collapsed until opened: the trace ID with its Grafana link when one is set up,
 * the suggestion and its trigger, and for each part the raw status, the reason codes, the
 * versions, and the latencies. Values are rendered as text, as `backend` sent them.
 */
import { Code } from "lucide-react";

import { DescriptionList, DisclosurePanel, Heading, Stack, TraceId } from "@/design-system";
import {
  describePartDetails,
  type DeveloperDetails,
} from "@/features/console-tickets/model/developer-details";

/** The heading of each part. */
const partTitles = { analysis: "Analysis", draft: "Draft" } as const;

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
  return (
    <DisclosurePanel title="Developer details" icon={Code}>
      <Stack gap="3">
        <TraceId traceId={details.traceId} {...(traceHref === undefined ? {} : { traceHref })} />
        <DescriptionList
          items={[
            { term: "Suggestion", description: details.suggestionId },
            { term: "Trigger", description: details.trigger },
          ]}
        />
        {[details.analysis, details.draft].map((part) => (
          <Stack key={part.part} as="section" label={partTitles[part.part]} gap="2">
            <Heading level={3} size="item">
              {partTitles[part.part]}
            </Heading>
            <DescriptionList
              items={describePartDetails(part).map((line) => ({
                term: line.term,
                description: line.value,
              }))}
            />
          </Stack>
        ))}
      </Stack>
    </DisclosurePanel>
  );
}
