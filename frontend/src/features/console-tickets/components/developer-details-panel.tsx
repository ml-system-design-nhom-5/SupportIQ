/**
 * The developer details of the current suggestion, only while dev mode is available and the
 * signed-in account switched it on (UI-35). Otherwise nothing is rendered, so the details are not
 * in the page at all. Dev mode changes nothing else on the workspace.
 */
import { DeveloperDetailsView } from "@/features/console-tickets/components/developer-details-view";
import type { Suggestion } from "@/features/console-tickets/model/workspace";
import { useDevMode } from "@/features/session";

/** Props of {@link DeveloperDetailsPanel}. */
type DeveloperDetailsPanelProps = {
  /** The current suggestion; undefined when the ticket has none. */
  readonly suggestion: Suggestion | undefined;
};

/**
 * Render the developer details when dev mode is on and there is a suggestion.
 *
 * @param props - The current suggestion.
 * @returns The panel, or nothing.
 */
export function DeveloperDetailsPanel({ suggestion }: DeveloperDetailsPanelProps) {
  const devMode = useDevMode();
  if (!devMode.isOn || suggestion === undefined) {
    return null;
  }
  const details = suggestion.developerDetails;
  const traceHref = devMode.traceHrefOf(details.traceId);
  return (
    <DeveloperDetailsView details={details} {...(traceHref === undefined ? {} : { traceHref })} />
  );
}
