/**
 * What frontend tells about itself in the developer details (admin UI design, Developer details in
 * the admin area; UI-35): its build version, every `VITE_` setting with the value in use, and the
 * links to the Grafana dashboards whose setting is set. Values are in monospace (UI-08).
 */
import {
  Cluster,
  DescriptionList,
  ExternalLink,
  Heading,
  Identifier,
  Stack,
  Text,
} from "@/design-system";
import type { FrontendDetails } from "@/features/session/model/dev-mode";

/** Props of {@link FrontendDetailsView}. */
export type FrontendDetailsViewProps = {
  readonly details: FrontendDetails;
};

/**
 * Render the details of frontend.
 *
 * @param props - The build version, the settings, and the dashboards.
 * @returns The section.
 */
export function FrontendDetailsView({ details }: FrontendDetailsViewProps) {
  const items = [
    { term: "Build version", description: renderValue(details.buildVersion) },
    ...details.settings.map((setting) => ({
      term: setting.name,
      description: renderValue(setting.value),
    })),
  ];
  return (
    <Stack as="section" label="Frontend" gap="2">
      <Heading level={3} size="item">
        Frontend
      </Heading>
      <DescriptionList items={items} />
      {details.dashboards.length === 0 ? null : (
        <Cluster>
          {details.dashboards.map((dashboard) => (
            <ExternalLink key={dashboard.title} href={dashboard.href}>
              {dashboard.title}
            </ExternalLink>
          ))}
        </Cluster>
      )}
    </Stack>
  );
}

/**
 * Render a value in monospace, or "Not set".
 *
 * @param value - The value, or undefined when it is not set.
 * @returns The value.
 */
function renderValue(value: string | undefined) {
  return value === undefined ? <Text tone="muted">Not set</Text> : <Identifier>{value}</Identifier>;
}
