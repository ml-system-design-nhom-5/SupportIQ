/**
 * The path from an area's list to the current page, for example "My orders > ORD-20931".
 */
import { ChevronRight } from "lucide-react";

import { Icon } from "@/design-system/primitives/icon";
import { TextLink } from "@/design-system/primitives/text-link";

/** One step of the path. The last step is the current page and has no link. */
export type BreadcrumbStep = {
  readonly label: string;
  /** The app path; absent for the current page. */
  readonly to?: string;
  /** Shows an identifier in JetBrains Mono (UI-08). */
  readonly isIdentifier?: boolean;
};

/** Props of {@link Breadcrumbs}. */
export type BreadcrumbsProps = {
  readonly steps: readonly BreadcrumbStep[];
};

/**
 * Render the breadcrumb navigation.
 *
 * @param props - The steps, from the area's list to the current page.
 * @returns The navigation landmark.
 */
export function Breadcrumbs({ steps }: BreadcrumbsProps) {
  return (
    <nav aria-label="Breadcrumb">
      <ol className="flex flex-wrap items-center gap-2 text-sm text-text-muted">
        {steps.map((step) => (
          <li key={step.to ?? step.label} className="flex items-center gap-2">
            {step.to === undefined ? (
              <CurrentStep step={step} />
            ) : (
              <>
                <TextLink to={step.to}>{step.label}</TextLink>
                <Icon icon={ChevronRight} />
              </>
            )}
          </li>
        ))}
      </ol>
    </nav>
  );
}

/**
 * Render the last step of the path, which is the current page.
 *
 * @param props - The step.
 * @returns The text of the step.
 */
function CurrentStep({ step }: { readonly step: BreadcrumbStep }) {
  return (
    <span
      aria-current="page"
      className={step.isIdentifier === true ? "font-mono text-xs wrap-anywhere" : "wrap-anywhere"}
    >
      {step.label}
    </span>
  );
}
