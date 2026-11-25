import type { Meta, StoryObj } from "@storybook/react-vite";

import {
  presentationByAiReasonCode,
  presentationByRecommendation,
} from "@/design-system/components/ai-presentations";
import { StatusBadge } from "@/design-system/components/status-badge";
import type { StatusPresentation } from "@/design-system/components/status-presentations";

const meta = {
  title: "Design system/Components/AiPresentations",
  component: StatusBadge,
  args: { presentation: presentationByRecommendation.draft },
} satisfies Meta<typeof StatusBadge>;

export default meta;

type Story = StoryObj<typeof meta>;

export const ReasonCodes: Story = { render: () => renderAll(presentationByAiReasonCode) };
export const Recommendations: Story = { render: () => renderAll(presentationByRecommendation) };

/**
 * Render every presentation of one set, so the story shows each variant (UI-04).
 *
 * @param presentations - The presentations of the set.
 * @returns The badges in a row.
 */
function renderAll(presentations: Readonly<Record<string, StatusPresentation>>) {
  return (
    <div className="flex flex-wrap gap-2">
      {Object.entries(presentations).map(([name, presentation]) => (
        <StatusBadge key={name} presentation={presentation} />
      ))}
    </div>
  );
}
