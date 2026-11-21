/**
 * The limits of `createAdminAccount` in the backend contract that the create dialog checks before
 * sending (account management design, Login names). `backend` enforces them with `422`; a unit test
 * compares them with the contract.
 */

/** The `minimum` of `login_number` (contracts/backend.openapi.yaml). */
export const LOGIN_NUMBER_MIN = 1;

/** The `maximum` of `login_number` (contracts/backend.openapi.yaml). */
export const LOGIN_NUMBER_MAX = 9999;

/** The `minLength` of `display_name` in `CreateAdminAccountRequest`. */
export const DISPLAY_NAME_MIN_LENGTH = 1;

/** The `maxLength` of `display_name` in `CreateAdminAccountRequest`. */
export const DISPLAY_NAME_MAX_LENGTH = 100;
