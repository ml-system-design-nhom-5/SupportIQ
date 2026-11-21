/**
 * The contract types that the backend-requests model maps (TS-09), from the generated client of
 * the `backend` contract.
 */
import type { components } from "@/api/generated/backend";

/** The `type` of `ProblemDetails`: a problem type URN of the contract. */
export type ProblemTypeUrnContract = components["schemas"]["ProblemDetails"]["type"];
