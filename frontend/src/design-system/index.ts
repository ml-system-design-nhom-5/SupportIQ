/**
 * The public API of the design system (ADR-0008, UI-01). Features and app/ import only from here.
 */
export type { AccountMenuProps, AccountMenuVariant } from "@/design-system/components/account-menu";
export { AccountMenu } from "@/design-system/components/account-menu";
export type { AppBarProps, AppBarVariant } from "@/design-system/components/app-bar";
export { AppBar } from "@/design-system/components/app-bar";
export type { BreadcrumbsProps, BreadcrumbStep } from "@/design-system/components/breadcrumbs";
export { Breadcrumbs } from "@/design-system/components/breadcrumbs";
export type { CenteredPanelProps } from "@/design-system/components/centered-panel";
export { CenteredPanel } from "@/design-system/components/centered-panel";
export type { DateTextProps } from "@/design-system/components/date-text";
export { DateText } from "@/design-system/components/date-text";
export type { FormFieldProps } from "@/design-system/components/form-field";
export { FormField, getFieldDescriptionId } from "@/design-system/components/form-field";
export type {
  InlineMessageProps,
  InlineMessageTone,
} from "@/design-system/components/inline-message";
export { InlineMessage } from "@/design-system/components/inline-message";
export type { LoadMoreButtonProps } from "@/design-system/components/load-more-button";
export { LoadMoreButton } from "@/design-system/components/load-more-button";
export type {
  MessageBoxLimit,
  MessageBoxProps,
  MessageBoxText,
} from "@/design-system/components/message-box";
export { MessageBox } from "@/design-system/components/message-box";
export type { MessageAuthor, MessageBubbleProps } from "@/design-system/components/message-bubble";
export { MessageBubble } from "@/design-system/components/message-bubble";
export type { MoneyTextProps } from "@/design-system/components/money-text";
export { MoneyText } from "@/design-system/components/money-text";
export type { OrderRowProps, OrderRowStatus } from "@/design-system/components/order-row";
export { OrderRow } from "@/design-system/components/order-row";
export type {
  OrderSummaryLine,
  OrderSummaryProps,
  OrderSummaryStatus,
} from "@/design-system/components/order-summary";
export { OrderSummary } from "@/design-system/components/order-summary";
export type { PageHeaderDensity, PageHeaderProps } from "@/design-system/components/page-header";
export { PageHeader } from "@/design-system/components/page-header";
export type { ProductCardProps } from "@/design-system/components/product-card";
export { ProductCard } from "@/design-system/components/product-card";
export { ProductCardSkeleton } from "@/design-system/components/product-card-skeleton";
export type { ProductDetailsProps } from "@/design-system/components/product-details";
export { ProductDetails } from "@/design-system/components/product-details";
export type { ProductImageProps, ProductImageSize } from "@/design-system/components/product-image";
export { ProductImage } from "@/design-system/components/product-image";
export type { RelativeTimeProps } from "@/design-system/components/relative-time";
export { RelativeTime } from "@/design-system/components/relative-time";
export type { RelativeTimeTextProps } from "@/design-system/components/relative-time-text";
export { RelativeTimeText } from "@/design-system/components/relative-time-text";
export type { RowListProps } from "@/design-system/components/row-list";
export { RowList } from "@/design-system/components/row-list";
export type {
  RowListItemProps,
  RowTrailingOnPhone,
} from "@/design-system/components/row-list-item";
export { RowListItem } from "@/design-system/components/row-list-item";
export type { StateMessageProps } from "@/design-system/components/state-message";
export { StateMessage } from "@/design-system/components/state-message";
export type { StatusBadgeProps } from "@/design-system/components/status-badge";
export { StatusBadge } from "@/design-system/components/status-badge";
export type { StatusBannerProps, StatusBannerTone } from "@/design-system/components/status-banner";
export { StatusBanner } from "@/design-system/components/status-banner";
export type {
  AccountStatusName,
  InternalRoleName,
  OrderStatusName,
  RefundStatusName,
  ShipmentStatusName,
  ShopTicketStatusName,
  StatusPresentation,
  StatusTone,
} from "@/design-system/components/status-presentations";
export {
  presentationByAccountStatus,
  presentationByInternalRole,
  presentationByOrderStatus,
  presentationByRefundStatus,
  presentationByShipmentStatus,
  presentationByShopTicketStatus,
} from "@/design-system/components/status-presentations";
export type { TicketItemProps, TicketItemReply } from "@/design-system/components/ticket-item";
export { TicketItem } from "@/design-system/components/ticket-item";
export type { TraceIdProps } from "@/design-system/components/trace-id";
export { TraceId } from "@/design-system/components/trace-id";
export type { Clock } from "@/design-system/format/clock";
export { ClockContext, systemClock, useNow } from "@/design-system/format/clock";
export { formatDate, formatDateTime, formatRelativeTime } from "@/design-system/format/date-time";
export type { Money } from "@/design-system/format/money";
export { formatMoney } from "@/design-system/format/money";
export { formatCount } from "@/design-system/format/number";
export type {
  ButtonProps,
  ButtonSize,
  ButtonVariant,
  ButtonWidth,
} from "@/design-system/primitives/button";
export { Button } from "@/design-system/primitives/button";
export type { ButtonLinkProps } from "@/design-system/primitives/button-link";
export { ButtonLink } from "@/design-system/primitives/button-link";
export type { CheckboxProps } from "@/design-system/primitives/checkbox";
export { Checkbox } from "@/design-system/primitives/checkbox";
export type {
  ConfirmDialogProps,
  ConfirmDialogText,
  ConfirmDialogTone,
} from "@/design-system/primitives/confirm-dialog";
export { ConfirmDialog } from "@/design-system/primitives/confirm-dialog";
export type {
  DataTableColumn,
  DataTableProps,
  DataTableRow,
} from "@/design-system/primitives/data-table";
export { buildRowHeaderId, DataTable } from "@/design-system/primitives/data-table";
export type { DialogReturnFocus } from "@/design-system/primitives/dialog-return-focus";
export type { FieldLabelProps } from "@/design-system/primitives/field-label";
export { FieldLabel } from "@/design-system/primitives/field-label";
export type { FormDialogProps, FormDialogText } from "@/design-system/primitives/form-dialog";
export { FormDialog } from "@/design-system/primitives/form-dialog";
export type { GridProps } from "@/design-system/primitives/grid";
export { Grid } from "@/design-system/primitives/grid";
export type { HeadingProps, HeadingSize } from "@/design-system/primitives/heading";
export { Heading } from "@/design-system/primitives/heading";
export type { IconProps, IconSize, IconTone } from "@/design-system/primitives/icon";
export { Icon } from "@/design-system/primitives/icon";
export type { IdentifierProps, IdentifierSize } from "@/design-system/primitives/identifier";
export { Identifier } from "@/design-system/primitives/identifier";
export type { NavItemProps } from "@/design-system/primitives/nav-item";
export { NavItem } from "@/design-system/primitives/nav-item";
export type { PageColumnArea, PageColumnProps } from "@/design-system/primitives/page-column";
export { PageColumn } from "@/design-system/primitives/page-column";
export type { PanelProps } from "@/design-system/primitives/panel";
export { Panel } from "@/design-system/primitives/panel";
export type { PanelHeaderProps } from "@/design-system/primitives/panel-header";
export { PanelHeader } from "@/design-system/primitives/panel-header";
export type {
  PanelSectionLayout,
  PanelSectionProps,
} from "@/design-system/primitives/panel-section";
export { PanelSection } from "@/design-system/primitives/panel-section";
export type { PasswordInputProps } from "@/design-system/primitives/password-input";
export { PasswordInput } from "@/design-system/primitives/password-input";
export type { RadioGroupProps, RadioOption } from "@/design-system/primitives/radio-group";
export { RadioGroup } from "@/design-system/primitives/radio-group";
export type {
  SkeletonHeight,
  SkeletonProps,
  SkeletonWidth,
} from "@/design-system/primitives/skeleton";
export { Skeleton } from "@/design-system/primitives/skeleton";
export type {
  SpacingStep,
  StackDirection,
  StackElement,
  StackProps,
} from "@/design-system/primitives/stack";
export { Stack } from "@/design-system/primitives/stack";
export type { TextOverflow, TextProps, TextSize, TextTone } from "@/design-system/primitives/text";
export { Text } from "@/design-system/primitives/text";
export type { TextAreaProps } from "@/design-system/primitives/text-area";
export { TextArea } from "@/design-system/primitives/text-area";
export type { TextInputProps } from "@/design-system/primitives/text-input";
export { TextInput } from "@/design-system/primitives/text-input";
export type { TextLinkEmphasis, TextLinkProps } from "@/design-system/primitives/text-link";
export { TextLink } from "@/design-system/primitives/text-link";
export type { TooltipProps } from "@/design-system/primitives/tooltip";
export { Tooltip } from "@/design-system/primitives/tooltip";
export type { ClipboardCopy, CopyOutcome } from "@/design-system/primitives/use-copy-to-clipboard";
export { useCopyToClipboard } from "@/design-system/primitives/use-copy-to-clipboard";
export type { VisuallyHiddenProps } from "@/design-system/primitives/visually-hidden";
export { VisuallyHidden } from "@/design-system/primitives/visually-hidden";
