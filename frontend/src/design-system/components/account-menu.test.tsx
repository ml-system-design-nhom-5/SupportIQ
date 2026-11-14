import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AccountMenu, type AccountMenuProps } from "@/design-system/components/account-menu";
import { renderUi } from "@/test/render-app";

/** A staff account in the console, with handlers that these tests do not check. */
const staffMenu: AccountMenuProps = {
  variant: "console",
  displayName: "Mai Nguyen",
  roleLabel: "Staff",
  isSigningOut: false,
  onChangePassword: () => undefined,
  onSignOut: () => undefined,
};

/** The name of the trigger of {@link staffMenu}. */
const TRIGGER_NAME = "Mai Nguyen · Staff";

/**
 * Render the menu and open it with a click.
 *
 * @param props - The props of the menu.
 * @returns The user-event instance.
 */
async function openMenu(props: AccountMenuProps) {
  const { user } = renderUi(<AccountMenu {...props} />);
  await user.click(screen.getByRole("button", { name: TRIGGER_NAME }));
  await screen.findByRole("menu");
  return user;
}

describe("AccountMenu", () => {
  it.each(["console", "shop"] as const)(
    "holds only Change password and Sign out in the %s without dev mode",
    async (variant) => {
      await openMenu({ ...staffMenu, variant });

      expect(screen.getAllByRole("menuitem").map((item) => item.textContent)).toEqual([
        "Change password",
        "Sign out",
      ]);
      expect(screen.queryByRole("menuitemcheckbox")).not.toBeInTheDocument();
      expect(screen.getAllByRole("separator")).toHaveLength(1);
    },
  );

  it.each([false, true])("announces dev mode as checked: %s (UI-35)", async (isOn) => {
    await openMenu({ ...staffMenu, devMode: { isOn, onChange: () => undefined } });

    expect(screen.getByRole("menuitemcheckbox", { name: "Dev mode" })).toHaveAttribute(
      "aria-checked",
      String(isOn),
    );
  });

  it("places dev mode as its own group between Change password and Sign out", async () => {
    await openMenu({ ...staffMenu, devMode: { isOn: false, onChange: () => undefined } });

    const menu = screen.getByRole("menu");
    const roles = [...menu.querySelectorAll("[role]")].map((element) =>
      element.getAttribute("role"),
    );
    expect(roles).toEqual([
      "separator",
      "menuitem",
      "separator",
      "menuitemcheckbox",
      "separator",
      "menuitem",
    ]);
  });

  it.each([
    [false, true],
    [true, false],
  ])("switches dev mode from %s to %s and closes the menu", async (isOn, isNextOn) => {
    const onChange = vi.fn<(isOn: boolean) => void>();
    const user = await openMenu({ ...staffMenu, devMode: { isOn, onChange } });

    await user.click(screen.getByRole("menuitemcheckbox", { name: "Dev mode" }));

    expect(onChange).toHaveBeenCalledExactlyOnceWith(isNextOn);
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });

  it("reaches dev mode with the arrow keys and switches it with Enter (UI-30)", async () => {
    const onChange = vi.fn<(isOn: boolean) => void>();
    const { user } = renderUi(<AccountMenu {...staffMenu} devMode={{ isOn: false, onChange }} />);
    const trigger = screen.getByRole("button", { name: TRIGGER_NAME });
    trigger.focus();

    await user.keyboard("{Enter}");
    expect(await screen.findByRole("menuitem", { name: "Change password" })).toHaveFocus();
    await user.keyboard("{ArrowDown}");
    expect(screen.getByRole("menuitemcheckbox", { name: "Dev mode" })).toHaveFocus();
    await user.keyboard("{Enter}");

    expect(onChange).toHaveBeenCalledExactlyOnceWith(true);
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });
});
