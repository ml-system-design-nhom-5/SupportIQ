/**
 * Sign in through the screen, as a person does. The password is a dummy value: the Prism mock
 * accepts any credentials that match the contract.
 */
import type { Page } from "@playwright/test";

const LOGIN_NAME = "customer-1";
const DUMMY_PASSWORD = "not-a-real-password";

/**
 * Fill in the sign-in form and submit it.
 *
 * @param page - A page on the sign-in screen.
 */
export async function submitSignIn(page: Page): Promise<void> {
  await page.getByRole("textbox", { name: "Login name" }).fill(LOGIN_NAME);
  await page.getByLabel("Password").fill(DUMMY_PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
}

/**
 * Create a session without the screen, for a flow that starts signed in. The cookie lands in the
 * browser context of the page.
 *
 * @param page - The page.
 */
export async function createSessionCookie(page: Page): Promise<void> {
  await page.request.post("/v1/sessions", {
    data: { login_name: LOGIN_NAME, password: DUMMY_PASSWORD },
  });
}
