/**
 * The public API of the backend-requests feature: how every feature talks to `backend`. It parses
 * failures in one place (ERR-03), turns them into user messages with one function (TS-26),
 * decides retries (ERR-12, TS-29), provides idempotency keys (ERR-15), joins list pages (CON-14),
 * and holds the exhaustiveness check of TS-12.
 */
export type { FormIdempotencyKey } from "@/features/backend-requests/api/idempotent-writes";
export {
  buildIdempotentWriteKey,
  forgetWrites,
  IdempotencyKeyFactoryContext,
  idempotentWriteMutationKey,
  useCreateIdempotencyKey,
  useFormIdempotencyKey,
  useWriteAttemptSender,
} from "@/features/backend-requests/api/idempotent-writes";
export { requestData, requestNoContent } from "@/features/backend-requests/api/request-backend";
export type { FailureBannerProps } from "@/features/backend-requests/components/failure-banner";
export { FailureBanner } from "@/features/backend-requests/components/failure-banner";
export type { FailureStateProps } from "@/features/backend-requests/components/failure-state";
export { FailureState } from "@/features/backend-requests/components/failure-state";
export { assertNever } from "@/features/backend-requests/model/assert-never";
export { collectPageItems } from "@/features/backend-requests/model/collect-pages";
export type { MoneyContract } from "@/features/backend-requests/model/contract-values";
export {
  countContractCharacters,
  MESSAGE_MAX_LENGTH,
  requireMembers,
  toMoney,
} from "@/features/backend-requests/model/contract-values";
export type {
  FailureCategory,
  FailureDescription,
} from "@/features/backend-requests/model/describe-failure";
export {
  categorizeFailure,
  describeFailure,
} from "@/features/backend-requests/model/describe-failure";
export {
  toOrderStatus,
  toRefundStatus,
  toShipmentStatus,
} from "@/features/backend-requests/model/order-statuses";
export type {
  ProblemType,
  RequestFailure,
} from "@/features/backend-requests/model/request-failure";
export {
  getRequestFailure,
  isUnauthenticatedError,
  isWriteOutcomeUnknown,
  RequestFailureError,
} from "@/features/backend-requests/model/request-failure";
export {
  computeRetryDelayMs,
  shouldRetryRequest,
} from "@/features/backend-requests/model/retry-policy";
