/**
 * The public API of the admin accounts feature: the Accounts screen (admin UI design, UI-45), and
 * the random source of its suggested passwords, which the composition root provides.
 */
export { RandomBytesContext } from "@/features/admin-accounts/api/random-bytes";
export { AccountsPage } from "@/features/admin-accounts/components/accounts-page";
export { ACCOUNTS_PATH, ACCOUNTS_ROUTE } from "@/features/admin-accounts/model/accounts-paths";
export type { RandomBytes } from "@/features/admin-accounts/model/suggested-password";
