import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, screen, within } from "storybook/test";

import { AccountsPage } from "@/features/admin-accounts/components/accounts-page";
import {
  changeAccountRoleRoute,
  changeAccountStatusRoute,
  getCurrentSessionRoute,
  listAdminAccountsRoute,
} from "@/test/backend-routes";
import { exampleAnswer, type FakeBackend } from "@/test/fake-backend";
import { withFakeBackend } from "@/test/story-backend";

const meta = {
  title: "Admin/Accounts",
  component: AccountsPage,
} satisfies Meta<typeof AccountsPage>;

export default meta;

type Story = StoryObj<typeof meta>;

export const FirstPage: Story = {
  decorators: [
    withFakeBackend((backend) => {
      answerAdminSession(backend);
      backend.answer(listAdminAccountsRoute, exampleAnswer(200, "listAdminAccounts", "first-page"));
    }),
  ],
};

export const LoadingMore: Story = {
  decorators: [
    withFakeBackend((backend) => {
      answerAdminSession(backend);
      backend.answer(
        listAdminAccountsRoute,
        exampleAnswer(200, "listAdminAccounts", "first-page"),
        {
          kind: "no_answer",
        },
      );
    }),
  ],
  play: async ({ canvas, userEvent }) => {
    await userEvent.click(await canvas.findByRole("button", { name: "Show more accounts" }));

    await expect(await canvas.findByRole("button", { name: "Loading…" })).toHaveAttribute(
      "aria-disabled",
      "true",
    );
  },
};

export const LoadingMoreFailed: Story = {
  decorators: [
    withFakeBackend((backend) => {
      answerAdminSession(backend);
      backend.answer(
        listAdminAccountsRoute,
        exampleAnswer(200, "listAdminAccounts", "first-page"),
        exampleAnswer(503, "problems", "not-ready"),
      );
    }),
  ],
  play: async ({ canvas, userEvent }) => {
    await userEvent.click(await canvas.findByRole("button", { name: "Show more accounts" }));

    await expect(await canvas.findByRole("alert")).toHaveTextContent("Details: trace");
  },
};

export const LastPageWithOwnAccount: Story = {
  decorators: [
    withFakeBackend((backend) => {
      answerAdminSession(backend);
      backend.answer(listAdminAccountsRoute, exampleAnswer(200, "listAdminAccounts", "last-page"));
    }),
  ],
};

export const Loading: Story = {
  decorators: [
    withFakeBackend((backend) => {
      answerAdminSession(backend);
      backend.answer(listAdminAccountsRoute, { kind: "no_answer" });
    }),
  ],
};

export const LoadError: Story = {
  decorators: [
    withFakeBackend((backend) => {
      answerAdminSession(backend);
      backend.answer(listAdminAccountsRoute, exampleAnswer(503, "problems", "not-ready"));
    }),
  ],
};

export const PermissionDenied: Story = {
  decorators: [
    withFakeBackend((backend) => {
      answerAdminSession(backend);
      backend.answer(listAdminAccountsRoute, exampleAnswer(403, "problems", "forbidden-role"));
    }),
  ],
};

export const ConfirmRoleChange: Story = {
  decorators: [
    withFakeBackend((backend) => {
      answerAdminSession(backend);
      backend.answer(listAdminAccountsRoute, exampleAnswer(200, "listAdminAccounts", "first-page"));
    }),
  ],
  play: async ({ canvas, userEvent }) => {
    await userEvent.click(await canvas.findByRole("button", { name: /Make manager/ }));

    await expect(await screen.findByRole("alertdialog")).toHaveTextContent(
      "Make Mai Nguyen a manager?",
    );
  },
};

export const ConfirmDeactivation: Story = {
  decorators: [
    withFakeBackend((backend) => {
      answerAdminSession(backend);
      backend.answer(listAdminAccountsRoute, exampleAnswer(200, "listAdminAccounts", "first-page"));
    }),
  ],
  play: async ({ canvas, userEvent }) => {
    await userEvent.click(await canvas.findByRole("button", { name: /Deactivate.*Hoa Pham/ }));

    await expect(await screen.findByRole("alertdialog")).toHaveTextContent("Deactivate Hoa Pham?");
  },
};

export const LastManagerRefused: Story = {
  decorators: [
    withFakeBackend((backend) => {
      answerAdminSession(backend);
      backend.answer(listAdminAccountsRoute, exampleAnswer(200, "listAdminAccounts", "first-page"));
      backend.answer(
        changeAccountStatusRoute,
        exampleAnswer(422, "problems", "last-active-manager"),
      );
    }),
  ],
  play: async ({ canvas, userEvent }) => {
    await userEvent.click(await canvas.findByRole("button", { name: /Deactivate.*Hoa Pham/ }));
    const dialog = await screen.findByRole("alertdialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Deactivate" }));

    await expect(await canvas.findByRole("alert")).toHaveTextContent(
      "This change would leave no active manager.",
    );
  },
};

export const ChangeOutcomeUnknown: Story = {
  decorators: [
    withFakeBackend((backend) => {
      answerAdminSession(backend);
      backend.answer(listAdminAccountsRoute, exampleAnswer(200, "listAdminAccounts", "first-page"));
      backend.answer(changeAccountStatusRoute, { kind: "ingress", status: 504 });
    }),
  ],
  play: async ({ canvas, userEvent }) => {
    await userEvent.click(await canvas.findByRole("button", { name: /Deactivate.*Hoa Pham/ }));
    const dialog = await screen.findByRole("alertdialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Deactivate" }));

    await expect(await canvas.findByRole("alert")).toHaveTextContent(
      "Hoa Pham may have been deactivated.",
    );
  },
};

export const OtherRefusal: Story = {
  decorators: [
    withFakeBackend((backend) => {
      answerAdminSession(backend);
      backend.answer(listAdminAccountsRoute, exampleAnswer(200, "listAdminAccounts", "first-page"));
      backend.answer(changeAccountRoleRoute, exampleAnswer(422, "problems", "role-unchanged"));
    }),
  ],
  play: async ({ canvas, userEvent }) => {
    await userEvent.click(await canvas.findByRole("button", { name: /Make manager/ }));
    const dialog = await screen.findByRole("alertdialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Make manager" }));

    await expect(await canvas.findByRole("alert")).toHaveTextContent("Reload the list");
  },
};

/**
 * Answer the session of the admin example.
 *
 * @param backend - The fake backend of the story.
 */
function answerAdminSession(backend: FakeBackend): void {
  backend.answer(getCurrentSessionRoute, exampleAnswer(200, "getCurrentSession", "admin"));
}
