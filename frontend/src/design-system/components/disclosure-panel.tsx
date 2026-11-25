/**
 * A collapsible section of a column, such as "Developer details" at the bottom of the AI sidebar
 * (UI-35; console UI design mockups, the developer details row). Closed, it is one muted, small
 * row: an icon, the title, and a chevron that points right. The row is a ghost {@link Button}
 * that follows the WAI-ARIA disclosure pattern: `aria-expanded` says whether it is open, and
 * `aria-controls` names the content while the content exists. Open, the chevron points down, and
 * the content shows below the row in a compact {@link Panel}. Closed, the content is not
 * rendered at all, so nothing in it is read, focused, or found. It is closed by default.
 */
import { ChevronDown, ChevronRight, type LucideIcon } from "lucide-react";
import { type ReactNode, useId, useState } from "react";

import { Button } from "@/design-system/primitives/button";
import { Icon } from "@/design-system/primitives/icon";
import { Panel } from "@/design-system/primitives/panel";
import { PanelSection } from "@/design-system/primitives/panel-section";

/** Props of {@link DisclosurePanel}. */
export type DisclosurePanelProps = {
  /** The text of the row, such as "Developer details"; it is also the name of the button. */
  readonly title: string;
  readonly icon: LucideIcon;
  /**
   * The level of the heading that holds the button, as the panels next to it use (UI-30), so a
   * screen reader can jump to it; 2 by default.
   */
  readonly level?: 2 | 3;
  /** True to show the content on the first render; closed otherwise. */
  readonly isDefaultOpen?: boolean;
  /** The content, rendered only while the panel is open. */
  readonly children: ReactNode;
};

/**
 * Render the row and, while it is open, the content below it.
 *
 * @param props - The title, the icon, the heading level, whether it starts open, and the content.
 * @returns The row, followed by the content when it is open.
 */
export function DisclosurePanel({
  title,
  icon,
  level = 2,
  isDefaultOpen = false,
  children,
}: DisclosurePanelProps) {
  const [isOpen, setIsOpen] = useState(isDefaultOpen);
  const contentId = useId();
  const HeadingElement = level === 2 ? "h2" : "h3";
  return (
    <div className="flex flex-col gap-2">
      {/* The row starts at the padding of the panels above it, and the button fits its text. */}
      <HeadingElement className="flex px-2">
        <Button
          variant="ghost"
          size="sm"
          leadingIcon={icon}
          aria-expanded={isOpen}
          // An ID reference must name an element that exists, so it is set only while open.
          aria-controls={isOpen ? contentId : undefined}
          onClick={() => {
            setIsOpen(!isOpen);
          }}
        >
          {title}
          <Icon icon={isOpen ? ChevronDown : ChevronRight} />
        </Button>
      </HeadingElement>
      {isOpen ? (
        <div id={contentId}>
          <Panel density="compact">
            <PanelSection>{children}</PanelSection>
          </Panel>
        </div>
      ) : null}
    </div>
  );
}
