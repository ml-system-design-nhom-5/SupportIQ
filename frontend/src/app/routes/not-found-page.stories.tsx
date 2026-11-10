import type { Meta, StoryObj } from "@storybook/react-vite";

import { NotFoundPage } from "@/app/routes/not-found-page";

const meta = {
  title: "App/NotFoundPage",
  component: NotFoundPage,
  parameters: { layout: "fullscreen" },
} satisfies Meta<typeof NotFoundPage>;

export default meta;

type Story = StoryObj<typeof meta>;

export const PageNotFound: Story = {};
