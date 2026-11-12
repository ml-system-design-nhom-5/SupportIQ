/**
 * The public API of the session feature: sign-in, sign-out, the account menu, the own password
 * change, the signed-in account, and the end of a session (ADR-0009, ADR-0015).
 */
export { endSession } from "@/features/session/api/session-cache";
export { useSignedInAccountId, useSignedInRole } from "@/features/session/api/use-current-session";
export type { SignInCredentials } from "@/features/session/api/use-sign-in";
export type { AreaLoadFailureProps } from "@/features/session/components/area-load-failure";
export { AreaLoadFailure } from "@/features/session/components/area-load-failure";
export type {
  AreaPermissionDeniedProps,
  RestrictedArea,
} from "@/features/session/components/area-permission-denied";
export { AreaPermissionDenied } from "@/features/session/components/area-permission-denied";
export { ChangePasswordPage } from "@/features/session/components/change-password-page";
export type { RequireSessionProps } from "@/features/session/components/require-session";
export { RequireSession } from "@/features/session/components/require-session";
export type { SessionAccountMenuProps } from "@/features/session/components/session-account-menu";
export { SessionAccountMenu } from "@/features/session/components/session-account-menu";
export { SignInPage } from "@/features/session/components/sign-in-page";
export { StartPage } from "@/features/session/components/start-page";
export type { PasswordLength } from "@/features/session/model/password";
export { classifyPasswordLength, PASSWORD_TOO_LONG_TEXT } from "@/features/session/model/password";
export { CHANGE_PASSWORD_PATH } from "@/features/session/model/password-change";
export type { AccountRole, AppArea, Session } from "@/features/session/model/session";
export { getRoleArea, rootPathByArea } from "@/features/session/model/session";
export { SIGN_IN_PATH } from "@/features/session/model/sign-in-paths";
