import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { FormField } from "@/design-system/components/form-field";
import { TextArea } from "@/design-system/primitives/text-area";
import { TextInput } from "@/design-system/primitives/text-input";
import { renderUi } from "@/test/render-app";

describe("FormField with TextInput", () => {
  it("labels the input, so it can be found by its name (UI-30)", () => {
    renderUi(
      <FormField inputId="login-name" label="Login name">
        <TextInput id="login-name" placeholder="staff-1" />
      </FormField>,
    );

    expect(screen.getByRole("textbox", { name: "Login name" })).toHaveAttribute(
      "placeholder",
      "staff-1",
    );
  });

  it("keeps what the person types", async () => {
    const { user } = renderUi(
      <FormField inputId="login-name" label="Login name">
        <TextInput id="login-name" />
      </FormField>,
    );

    await user.type(screen.getByRole("textbox", { name: "Login name" }), "customer-1");

    expect(screen.getByRole("textbox", { name: "Login name" })).toHaveValue("customer-1");
  });

  it("marks an invalid value for assistive technology", () => {
    renderUi(
      <FormField inputId="login-name" label="Login name">
        <TextInput id="login-name" aria-invalid />
      </FormField>,
    );

    expect(screen.getByRole("textbox", { name: "Login name" })).toBeInvalid();
  });
});

describe("FormField with TextArea", () => {
  it("labels a four-row text area by default", () => {
    renderUi(
      <FormField inputId="message" label="Write to support about this order">
        <TextArea id="message" />
      </FormField>,
    );

    expect(
      screen.getByRole("textbox", { name: "Write to support about this order" }),
    ).toHaveAttribute("rows", "4");
  });

  it("can be disabled", () => {
    renderUi(
      <FormField inputId="message" label="Message">
        <TextArea id="message" rows={2} disabled />
      </FormField>,
    );

    expect(screen.getByRole("textbox", { name: "Message" })).toBeDisabled();
  });
});
