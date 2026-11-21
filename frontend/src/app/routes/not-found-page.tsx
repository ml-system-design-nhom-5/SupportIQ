/**
 * The page of an address that no route serves.
 */
import { Search } from "lucide-react";

import { ButtonLink, PageColumn, StateMessage } from "@/design-system";

/**
 * Render the not-found page.
 *
 * @returns The state message, with a link to the start page.
 */
export function NotFoundPage() {
  return (
    <PageColumn area="shop">
      <title>Page not found · SupportIQ</title>
      <StateMessage
        icon={Search}
        headingLevel={1}
        title="This page was not found"
        description="Check the address, or go to the start page."
        actions={<ButtonLink to="/">Go to the start page</ButtonLink>}
      />
    </PageColumn>
  );
}
