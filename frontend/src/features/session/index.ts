/**
 * The public API of the session feature: sign-in, sign-out, the signed-in account, and the end of
 * a session (ADR-0009).
 */
export { endSession } from "@/features/session/api/session-cache";
export { useSignedInAccountId } from "@/features/session/api/use-current-session";
export type { SignInCredentials } from "@/features/session/api/use-sign-in";
export type { AreaLoadFailureProps } from "@/features/session/components/area-load-failure";
export { AreaLoadFailure } from "@/features/session/components/area-load-failure";
export type {
  AreaPermissionDeniedProps,
  RestrictedArea,
} from "@/features/session/components/area-permission-denied";
export { AreaPermissionDenied } from "@/features/session/components/area-permission-denied";
export type { RequireSessionProps } from "@/features/session/components/require-session";
export { RequireSession } from "@/features/session/components/require-session";
export { SignInPage } from "@/features/session/components/sign-in-page";
export type {
  SignOutButtonPlacement,
  SignOutButtonProps,
} from "@/features/session/components/sign-out-button";
export { SignOutButton } from "@/features/session/components/sign-out-button";
export { StartPage } from "@/features/session/components/start-page";
export type { AccountRole, AppArea, Session } from "@/features/session/model/session";
export { getRoleLabel, rootPathByArea } from "@/features/session/model/session";
export { SIGN_IN_PATH } from "@/features/session/model/sign-in-paths";
