/**
 * The one presentation of each status (UI-12): a tone, an icon, and a label, so color is never
 * the only signal (UI-11). Screens never define their own status colors. The values follow the
 * Status presentations tables of the shop UI design and the admin UI design.
 *
 * Each set includes `unknown`, the safe presentation of a value that `backend` added after this
 * version (CON-22). Feature models map contract values to these sets.
 */
import {
  CircleCheck,
  CircleHelp,
  CircleX,
  ClipboardList,
  Clock,
  type LucideIcon,
  Minus,
  Package,
  PackageOpen,
  Shield,
  TriangleAlert,
  User,
  Warehouse,
} from "lucide-react";

const unknownStatusPresentation: StatusPresentation = {
  tone: "neutral",
  icon: CircleHelp,
  label: "Status unknown",
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
