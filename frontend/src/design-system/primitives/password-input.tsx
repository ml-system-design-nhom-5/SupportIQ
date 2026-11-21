/**
 * The input of every password field, the sign-in field included (UI-46; account management design,
 * Password fields). A toggle at the end of the field shows or hides the password. The password is
 * hidden on every load, and a form shows it hidden again after a successful submission because it
 * unmounts the field. The field never blocks paste or autofill and never truncates: it has no
 * `maxLength`, and the form checks the length instead.
 */
import { Eye } from "lucide-react";
import { useState } from "react";

import { cn } from "@/design-system/primitives/class-names";
import { FOCUS_RING_CLASSES } from "@/design-system/primitives/focus-ring";
import { Icon } from "@/design-system/primitives/icon";
import { TEXT_INPUT_CLASSES, type TextInputProps } from "@/design-system/primitives/text-input";

/** The fixed accessible name of the toggle; `aria-pressed` carries its state (UI-46). */
const SHOW_PASSWORD_LABEL = "Show password";

/** Props of {@link PasswordInput}: the native input attributes, with a password autocomplete. */
export type PasswordInputProps = Omit<
  TextInputProps,
  "type" | "autoComplete" | "maxLength" | "leadingText"
> & {
  /** `current-password` for a password that exists, `new-password` for one that is being set. */
  readonly autoComplete: "current-password" | "new-password";
};

/**
 * Render a password input with its show and hide toggle.
 *
 * @param props - The autocomplete value and the native input attributes.
 * @returns The input with the toggle at its end.
 */
export function PasswordInput({ autoComplete, ...inputAttributes }: PasswordInputProps) {
  const [isShown, setIsShown] = useState(false);
  return (
    <div className="relative w-full min-w-0">
      <input
        {...inputAttributes}
        type={isShown ? "text" : "password"}
        autoComplete={autoComplete}
        // A shown password is still Secret: no spell checker or autocorrection reads it (SEC-01).
        spellCheck={false}
        autoCapitalize="off"
        className={cn(TEXT_INPUT_CLASSES, "pr-8")}
      />
      <button
        type="button"
        aria-label={SHOW_PASSWORD_LABEL}
        aria-pressed={isShown}
        className={cn(
          "absolute top-1/2 right-1 flex -translate-y-1/2 rounded-sm p-1 text-text-muted hover:text-text aria-pressed:text-text",
          FOCUS_RING_CLASSES,
        )}
        // A click keeps the focus and the caret in the field (UI-46); the keyboard still reaches it.
        onMouseDown={(event) => {
          event.preventDefault();
        }}
        onClick={() => {
          setIsShown(!isShown);
        }}
      >
        <Icon icon={Eye} />
      </button>
    </div>
  );
}
