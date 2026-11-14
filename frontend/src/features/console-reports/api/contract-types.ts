/**
 * The contract types of the report operation, for the mappings in model/ (TS-09).
 */
import type { components } from "@/api/generated/backend";

type Schemas = components["schemas"];

/** `ConsoleReport`: the body of `getConsoleReport`. */
export type ConsoleReportContract = Schemas["ConsoleReport"];

/** `ModeHandlingTime`: the median handling time of the tickets of one mode. */
export type ModeHandlingTimeContract = Schemas["ModeHandlingTime"];

/** `StaffReasonReplyCount`: the replies of one draft decision with one staff reason code. */
export type StaffReasonReplyCountContract = Schemas["StaffReasonReplyCount"];

/** `CompletedDraftStatus`: the status of a draft part that left `pending`. */
export type CompletedDraftStatusContract = Schemas["CompletedDraftStatus"];
