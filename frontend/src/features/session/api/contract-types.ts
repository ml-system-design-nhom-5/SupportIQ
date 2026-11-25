/**
 * The contract types of the session operations, for the mappings in model/ (TS-09).
 */
import type { components } from "@/api/generated/backend";

/** `SessionView`: the signed-in account of a session. */
export type SessionViewContract = components["schemas"]["SessionView"];
