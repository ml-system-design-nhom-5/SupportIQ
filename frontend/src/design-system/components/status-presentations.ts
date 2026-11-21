/**
 * The one presentation of each status (UI-12): a tone, an icon, and a label, so color is never
 * the only signal (UI-11). Screens never define their own status colors. The values follow the
 * Status presentations tables of the shop UI design, the admin UI design, and the console UI
 * design.
 *
 * Each set of a contract enum includes `unknown`, the safe presentation of a value that `backend`
 * added after this version (CON-22), unless the contract maps an unknown value to a known one.
 * Feature models map contract values to these sets.
 */
import {
  CircleArrowUp,
  CircleCheck,
  CircleDot,
  CircleHelp,
  CircleX,
  ClipboardList,
  Clock,
  LoaderCircle,
  type LucideIcon,
  Minus,
  Package,
  PackageOpen,
  Shield,
  Sparkles,
  TriangleAlert,
  User,
  Warehouse,
} from "lucide-react";

const unknownStatusPresentation: StatusPresentation = {
  tone: "neutral",
  icon: CircleHelp,
  label: "Status unknown",
};

/** Manual handling: the AI status of a `manual` ticket and the label of its handling mode. */
const manualHandlingPresentation: StatusPresentation = {
  tone: "neutral",
  icon: User,
  label: "Manual handling",
};

/** Order statuses: shop UI design, Status presentations. */
export const presentationByOrderStatus: Readonly<Record<OrderStatusName, StatusPresentation>> = {
  placed: { tone: "neutral", icon: ClipboardList, label: "Placed" },
  processing: { tone: "info", icon: PackageOpen, label: "Processing" },
  shipped: { tone: "info", icon: Package, label: "Shipped" },
  delivered: { tone: "success", icon: CircleCheck, label: "Delivered" },
  cancelled: { tone: "neutral", icon: CircleX, label: "Cancelled" },
  unknown: unknownStatusPresentation,
};

/** Shipment statuses: shop UI design, Status presentations. */
export const presentationByShipmentStatus: Readonly<
  Record<ShipmentStatusName, StatusPresentation>
> = {
  not_shipped: { tone: "neutral", icon: Warehouse, label: "Not shipped" },
  in_transit: { tone: "info", icon: Package, label: "In transit" },
  delivered: { tone: "success", icon: CircleCheck, label: "Delivered" },
  delayed: { tone: "warning", icon: Clock, label: "Delayed" },
  lost: { tone: "danger", icon: TriangleAlert, label: "Lost" },
  unknown: unknownStatusPresentation,
};

/** Refund statuses: shop UI design, Status presentations. */
export const presentationByRefundStatus: Readonly<Record<RefundStatusName, StatusPresentation>> = {
  requested: { tone: "info", icon: Clock, label: "Refund requested" },
  under_review: { tone: "info", icon: Clock, label: "Refund under review" },
  approved: { tone: "success", icon: CircleCheck, label: "Refund approved" },
  rejected: { tone: "danger", icon: CircleX, label: "Refund rejected" },
  paid: { tone: "success", icon: CircleCheck, label: "Refund paid" },
  none: { tone: "neutral", icon: Minus, label: "No refund" },
  unknown: { tone: "neutral", icon: CircleHelp, label: "Refund status unknown" },
};

/** Ticket statuses for customers: shop UI design, Status presentations. */
export const presentationByShopTicketStatus: Readonly<
  Record<ShopTicketStatusName, StatusPresentation>
> = {
  received: { tone: "info", icon: Clock, label: "Received" },
  replied: { tone: "success", icon: CircleCheck, label: "Replied" },
};

/** Roles: admin UI design, Status presentations. */
export const presentationByInternalRole: Readonly<Record<InternalRoleName, StatusPresentation>> = {
  staff: { tone: "neutral", icon: User, label: "Staff" },
  manager: { tone: "info", icon: Shield, label: "Manager" },
  admin: { tone: "neutral", icon: Shield, label: "Admin" },
  unknown: { tone: "neutral", icon: CircleHelp, label: "Unknown role" },
};

/** Account statuses: admin UI design, Status presentations. */
export const presentationByAccountStatus: Readonly<Record<AccountStatusName, StatusPresentation>> =
  {
    active: { tone: "success", icon: CircleCheck, label: "Active" },
    deactivated: { tone: "neutral", icon: CircleX, label: "Deactivated" },
  };

/**
 * Whether `backend` could read the versions of `ai-service`: admin UI design, Status
 * presentations.
 */
export const presentationByAiServiceStatus: Readonly<
  Record<AiServiceStatusName, StatusPresentation>
> = {
  available: { tone: "success", icon: CircleCheck, label: "Available" },
  unavailable: { tone: "danger", icon: CircleX, label: "Unavailable" },
};

/** Ticket statuses for staff and managers: console UI design, Status presentations. */
export const presentationByConsoleTicketStatus: Readonly<
  Record<ConsoleTicketStatusName, StatusPresentation>
> = {
  open: { tone: "info", icon: CircleDot, label: "Open" },
  awaiting_approval: { tone: "warning", icon: Clock, label: "Awaiting approval" },
  escalated: { tone: "warning", icon: CircleArrowUp, label: "Escalated" },
  closed: { tone: "success", icon: CircleCheck, label: "Closed" },
  unknown: unknownStatusPresentation,
};

/**
 * What the AI produced for a ticket: the draft statuses, `unavailable` for an AI part that is
 * `unavailable` or a draft that is `llm_unavailable`, and `manual` for a `manual` ticket (console
 * UI design, Status presentations).
 */
export const presentationByAiStatus: Readonly<Record<AiStatusName, StatusPresentation>> = {
  pending: { tone: "info", icon: LoaderCircle, label: "Generating draft" },
  draft_ready: { tone: "ai", icon: Sparkles, label: "Draft ready" },
  abstained: { tone: "warning", icon: TriangleAlert, label: "AI abstained" },
  escalation_recommended: { tone: "warning", icon: CircleArrowUp, label: "Escalation recommended" },
  unavailable: { tone: "danger", icon: CircleX, label: "AI unavailable" },
  manual: manualHandlingPresentation,
};

/**
 * The status of a completed draft part (`CompletedDraftStatus` of the contract), as the reports
 * count it (FR-10, UI-44). Unlike {@link presentationByAiStatus}, a draft that is `llm_unavailable`
 * keeps its own label, because the report counts it apart from `unavailable`.
 */
export const presentationByCompletedDraftStatus: Readonly<
  Record<CompletedDraftStatusName, StatusPresentation>
> = {
  draft_ready: presentationByAiStatus.draft_ready,
  abstained: presentationByAiStatus.abstained,
  escalation_recommended: presentationByAiStatus.escalation_recommended,
  llm_unavailable: { tone: "danger", icon: CircleX, label: "LLM unavailable" },
  unavailable: presentationByAiStatus.unavailable,
  unknown: unknownStatusPresentation,
};

/** Handling modes: console UI design, Status presentations and the ticket header. */
export const presentationByHandlingMode: Readonly<Record<HandlingModeName, StatusPresentation>> = {
  assisted: { tone: "neutral", icon: Sparkles, label: "Assisted" },
  manual: manualHandlingPresentation,
};

/** Validity of a KB document version: console UI design, Status presentations. */
export const presentationByDocumentValidity: Readonly<
  Record<DocumentValidityName, StatusPresentation>
> = {
  valid: { tone: "success", icon: CircleCheck, label: "In effect" },
  expired: { tone: "warning", icon: Clock, label: "Expired" },
  conflicting: { tone: "danger", icon: TriangleAlert, label: "Conflicting" },
};

/** A ticket where authority is required (FR-06): the inbox flag and the workspace banner. */
export const authorityRequiredPresentation: StatusPresentation = {
  tone: "warning",
  icon: Shield,
  label: "Authority required",
};

/** The tone of a badge: a color role of UI-06, or `neutral`. */
export type StatusTone = "neutral" | "info" | "success" | "warning" | "danger" | "ai";

/** How one status looks. */
export type StatusPresentation = {
  readonly tone: StatusTone;
  readonly icon: LucideIcon;
  readonly label: string;
};

/** Order statuses (`OrderStatus` of the contract). */
export type OrderStatusName =
  "placed" | "processing" | "shipped" | "delivered" | "cancelled" | "unknown";

/** Shipment statuses (`ShipmentStatus` of the contract). */
export type ShipmentStatusName =
  "not_shipped" | "in_transit" | "delivered" | "delayed" | "lost" | "unknown";

/** Refund statuses (`RefundStatus` of the contract), and `none` for an order without a refund. */
export type RefundStatusName =
  "requested" | "under_review" | "approved" | "rejected" | "paid" | "none" | "unknown";

/** Ticket statuses as the customer sees them (`ShopTicketStatus` of the contract). */
export type ShopTicketStatusName = "received" | "replied";

/** Roles of internal accounts (`InternalAccountRole` of the contract). */
export type InternalRoleName = "staff" | "manager" | "admin" | "unknown";

/** Whether an internal account can sign in. */
export type AccountStatusName = "active" | "deactivated";

/**
 * Whether `backend` could read the versions of `ai-service` (`AiServiceStatus` of the contract; an
 * unknown value is `unavailable`).
 */
export type AiServiceStatusName = "available" | "unavailable";

/** Ticket statuses as staff see them (`ConsoleTicketStatus` of the contract). */
export type ConsoleTicketStatusName =
  "open" | "awaiting_approval" | "escalated" | "closed" | "unknown";

/** What the AI produced for a ticket, as {@link presentationByAiStatus} lists it. */
export type AiStatusName =
  "pending" | "draft_ready" | "abstained" | "escalation_recommended" | "unavailable" | "manual";

/** The status of a completed draft part (`CompletedDraftStatus` of the contract). */
export type CompletedDraftStatusName =
  | "draft_ready"
  | "abstained"
  | "escalation_recommended"
  | "llm_unavailable"
  | "unavailable"
  | "unknown";

/** Handling modes (`HandlingMode` of the contract; an unknown value is `manual`). */
export type HandlingModeName = "assisted" | "manual";

/** Validity of a KB document version (`DocumentValidity`; an unknown value is `expired`). */
export type DocumentValidityName = "valid" | "expired" | "conflicting";
