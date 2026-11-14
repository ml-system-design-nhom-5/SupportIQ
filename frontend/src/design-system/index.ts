/**
 * The public API of the design system (ADR-0008, UI-01). Features and app/ import only from here.
 */
export type {
  AccountMenuDevMode,
  AccountMenuProps,
  AccountMenuVariant,
} from "@/design-system/components/account-menu";
export { AccountMenu } from "@/design-system/components/account-menu";
export type { ActionBarProps, ActionMenuItem } from "@/design-system/components/action-bar";
export { ActionBar } from "@/design-system/components/action-bar";
export type {
  AiReasonCodeName,
  RecommendationName,
} from "@/design-system/components/ai-presentations";
export {
  presentationByAiReasonCode,
  presentationByRecommendation,
} from "@/design-system/components/ai-presentations";
export { AppBar, type AppBarProps, type AppBarVariant } from "@/design-system/components/app-bar";
export type { BreadcrumbsProps, BreadcrumbStep } from "@/design-system/components/breadcrumbs";
export { Breadcrumbs } from "@/design-system/components/breadcrumbs";
export type { CenteredContentProps } from "@/design-system/components/centered-content";
export { CenteredContent } from "@/design-system/components/centered-content";
export { CenteredPanel, type CenteredPanelProps } from "@/design-system/components/centered-panel";
export { Chip, type ChipProps } from "@/design-system/components/chip";
export type {
  CitationMarkerProps,
  CitationSource,
} from "@/design-system/components/citation-marker";
export { CitationMarker } from "@/design-system/components/citation-marker";
export type {
  ConfidenceBandName,
  ConfidenceMeterProps,
} from "@/design-system/components/confidence-meter";
export { ConfidenceMeter } from "@/design-system/components/confidence-meter";
export { ConsolePage, type ConsolePageProps } from "@/design-system/components/console-page";
export { ConsoleShell, type ConsoleShellProps } from "@/design-system/components/console-shell";
export type {
  CustomerOrderOption,
  CustomerOrdersProps,
} from "@/design-system/components/customer-orders";
export { CustomerOrders } from "@/design-system/components/customer-orders";
export { DateText, type DateTextProps } from "@/design-system/components/date-text";
export type { DisclosurePanelProps } from "@/design-system/components/disclosure-panel";
export { DisclosurePanel } from "@/design-system/components/disclosure-panel";
export type {
  DraftTextParagraph,
  DraftTextProps,
  DraftTextSegment,
  DraftTextTone,
} from "@/design-system/components/draft-text";
export { DraftText } from "@/design-system/components/draft-text";
export type { FigureTableProps, FigureTableRow } from "@/design-system/components/figure-table";
export { FigureTable } from "@/design-system/components/figure-table";
export type { FormFieldProps } from "@/design-system/components/form-field";
export { FormField, getFieldDescriptionId } from "@/design-system/components/form-field";
export { InboxItem, type InboxItemProps } from "@/design-system/components/inbox-item";
export { InboxItemSkeleton } from "@/design-system/components/inbox-item-skeleton";
export { InboxLayout, type InboxLayoutProps } from "@/design-system/components/inbox-layout";
export { InboxMessage, type InboxMessageProps } from "@/design-system/components/inbox-message";
export { InboxPanel, type InboxPanelProps } from "@/design-system/components/inbox-panel";
export type {
  InlineMessageProps,
  InlineMessageTone,
} from "@/design-system/components/inline-message";
export { InlineMessage } from "@/design-system/components/inline-message";
export type {
  IntentChoiceCandidate,
  IntentChoiceProps,
  IntentUse,
} from "@/design-system/components/intent-choice";
export { IntentChoice } from "@/design-system/components/intent-choice";
export type {
  IntentConfidence,
  IntentCorrection,
  IntentOption,
  IntentStripCandidate,
  IntentStripProps,
} from "@/design-system/components/intent-strip";
export { IntentStrip } from "@/design-system/components/intent-strip";
export type { KbDocumentTextProps } from "@/design-system/components/kb-document-text";
export { KbDocumentText } from "@/design-system/components/kb-document-text";
export type { LoadMoreButtonProps } from "@/design-system/components/load-more-button";
export { LoadMoreButton } from "@/design-system/components/load-more-button";
export type {
  MarkedTextLayer,
  MarkedTextPart,
  MarkedTextProps,
} from "@/design-system/components/marked-text";
export { MarkedText } from "@/design-system/components/marked-text";
export type {
  MessageBoxLimit,
  MessageBoxProps,
  MessageBoxText,
} from "@/design-system/components/message-box";
export { MessageBox } from "@/design-system/components/message-box";
export type { MessageAuthor, MessageBubbleProps } from "@/design-system/components/message-bubble";
export { MessageBubble } from "@/design-system/components/message-bubble";
export { MoneyText, type MoneyTextProps } from "@/design-system/components/money-text";
export { OrderChip, type OrderChipProps } from "@/design-system/components/order-chip";
export type {
  CitedOrderFact,
  OrderCitationMarkerProps,
} from "@/design-system/components/order-citation-marker";
export { OrderCitationMarker } from "@/design-system/components/order-citation-marker";
export type { OrderFactItem, OrderFactsProps } from "@/design-system/components/order-facts";
export { OrderFacts } from "@/design-system/components/order-facts";
export { OrderRecord, type OrderRecordProps } from "@/design-system/components/order-record";
export type { OrderRecordHeaderProps } from "@/design-system/components/order-record-header";
export { OrderRecordHeader } from "@/design-system/components/order-record-header";
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
export { ProductCard, type ProductCardProps } from "@/design-system/components/product-card";
export { ProductCardSkeleton } from "@/design-system/components/product-card-skeleton";
export type { ProductDetailsProps } from "@/design-system/components/product-details";
export { ProductDetails } from "@/design-system/components/product-details";
export type { ProductImageProps, ProductImageSize } from "@/design-system/components/product-image";
export { ProductImage } from "@/design-system/components/product-image";
export type { ProposalComparisonProps } from "@/design-system/components/proposal-comparison";
export { ProposalComparison } from "@/design-system/components/proposal-comparison";
export { RelativeTime, type RelativeTimeProps } from "@/design-system/components/relative-time";
export type { RelativeTimeTextProps } from "@/design-system/components/relative-time-text";
export { RelativeTimeText } from "@/design-system/components/relative-time-text";
export { ReplyEditor, type ReplyEditorProps } from "@/design-system/components/reply-editor";
export { ReplyPreview, type ReplyPreviewProps } from "@/design-system/components/reply-preview";
export { RowList, type RowListProps } from "@/design-system/components/row-list";
export type {
  RowListItemProps,
  RowTrailingOnPhone,
} from "@/design-system/components/row-list-item";
export { RowListItem } from "@/design-system/components/row-list-item";
export type { SourceListItem, SourceListProps } from "@/design-system/components/source-list";
export { SourceList } from "@/design-system/components/source-list";
export { StaffNote, type StaffNoteProps } from "@/design-system/components/staff-note";
export { StateMessage, type StateMessageProps } from "@/design-system/components/state-message";
export { StatusBadge, type StatusBadgeProps } from "@/design-system/components/status-badge";
export type { StatusBannerProps, StatusBannerTone } from "@/design-system/components/status-banner";
export { StatusBanner } from "@/design-system/components/status-banner";
export type {
  AccountStatusName,
  AiStatusName,
  CompletedDraftStatusName,
  ConsoleTicketStatusName,
  DocumentValidityName,
  HandlingModeName,
  InternalRoleName,
  OrderStatusName,
  RefundStatusName,
  ShipmentStatusName,
  ShopTicketStatusName,
  StatusPresentation,
  StatusTone,
} from "@/design-system/components/status-presentations";
export {
  authorityRequiredPresentation,
  presentationByAccountStatus,
  presentationByAiStatus,
  presentationByCompletedDraftStatus,
  presentationByConsoleTicketStatus,
  presentationByDocumentValidity,
  presentationByHandlingMode,
  presentationByInternalRole,
  presentationByOrderStatus,
  presentationByRefundStatus,
  presentationByShipmentStatus,
  presentationByShopTicketStatus,
} from "@/design-system/components/status-presentations";
export { Tag, type TagProps } from "@/design-system/components/tag";
export { TicketHeader, type TicketHeaderProps } from "@/design-system/components/ticket-header";
export { TicketHeaderSkeleton } from "@/design-system/components/ticket-header-skeleton";
export type { TicketItemProps, TicketItemReply } from "@/design-system/components/ticket-item";
export { TicketItem } from "@/design-system/components/ticket-item";
export type {
  ToggleChipGroupProps,
  ToggleChipOption,
} from "@/design-system/components/toggle-chip-group";
export { ToggleChipGroup } from "@/design-system/components/toggle-chip-group";
export { TraceId, type TraceIdProps } from "@/design-system/components/trace-id";
export type { WarningListItem, WarningListProps } from "@/design-system/components/warning-list";
export { WarningList } from "@/design-system/components/warning-list";
export type { WorkspaceLayoutProps } from "@/design-system/components/workspace-layout";
export { WorkspaceLayout } from "@/design-system/components/workspace-layout";
export { type Clock, ClockContext, systemClock, useNow } from "@/design-system/format/clock";
export { formatDate, formatDateTime, formatRelativeTime } from "@/design-system/format/date-time";
export { formatDuration } from "@/design-system/format/duration";
export { formatMicroUsd, formatMoney, type Money } from "@/design-system/format/money";
export { formatCount, formatPercent, formatShareOneDecimal } from "@/design-system/format/number";
export type {
  ButtonProps,
  ButtonSize,
  ButtonVariant,
  ButtonWidth,
} from "@/design-system/primitives/button";
export { Button } from "@/design-system/primitives/button";
export { ButtonLink, type ButtonLinkProps } from "@/design-system/primitives/button-link";
export { Checkbox, type CheckboxProps } from "@/design-system/primitives/checkbox";
export { Cluster, type ClusterProps } from "@/design-system/primitives/cluster";
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
export type {
  DescriptionItem,
  DescriptionListProps,
} from "@/design-system/primitives/description-list";
export { DescriptionList } from "@/design-system/primitives/description-list";
export type { DialogReturnFocus } from "@/design-system/primitives/dialog-return-focus";
export { FieldLabel, type FieldLabelProps } from "@/design-system/primitives/field-label";
export type { FormDialogProps, FormDialogText } from "@/design-system/primitives/form-dialog";
export { FormDialog } from "@/design-system/primitives/form-dialog";
export { Grid, type GridProps } from "@/design-system/primitives/grid";
export { Heading, type HeadingProps, type HeadingSize } from "@/design-system/primitives/heading";
export type { IconProps, IconSize, IconTone } from "@/design-system/primitives/icon";
export { Icon } from "@/design-system/primitives/icon";
export type { IdentifierProps, IdentifierSize } from "@/design-system/primitives/identifier";
export { Identifier } from "@/design-system/primitives/identifier";
export type { MenuSelectOption, MenuSelectProps } from "@/design-system/primitives/menu-select";
export { MenuSelect } from "@/design-system/primitives/menu-select";
export { NavItem, type NavItemProps } from "@/design-system/primitives/nav-item";
export type { PageColumnArea, PageColumnProps } from "@/design-system/primitives/page-column";
export { PageColumn } from "@/design-system/primitives/page-column";
export type { PanelHeight, PanelProps, PanelTone } from "@/design-system/primitives/panel";
export { Panel } from "@/design-system/primitives/panel";
export { PanelHeader, type PanelHeaderProps } from "@/design-system/primitives/panel-header";
export type {
  PanelSectionLayout,
  PanelSectionProps,
} from "@/design-system/primitives/panel-section";
export { PanelSection } from "@/design-system/primitives/panel-section";
export { PasswordInput, type PasswordInputProps } from "@/design-system/primitives/password-input";
export { Popover, type PopoverProps, type PopoverWidth } from "@/design-system/primitives/popover";
export type { RadioGroupProps, RadioOption } from "@/design-system/primitives/radio-group";
export { RadioGroup } from "@/design-system/primitives/radio-group";
export { Sheet, type SheetProps } from "@/design-system/primitives/sheet";
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
export { TextArea, type TextAreaProps } from "@/design-system/primitives/text-area";
export { TextInput, type TextInputProps } from "@/design-system/primitives/text-input";
export type { TextLinkEmphasis, TextLinkProps } from "@/design-system/primitives/text-link";
export { TextLink } from "@/design-system/primitives/text-link";
export { Tooltip, type TooltipProps } from "@/design-system/primitives/tooltip";
export type { ClipboardCopy, CopyOutcome } from "@/design-system/primitives/use-copy-to-clipboard";
export { useCopyToClipboard } from "@/design-system/primitives/use-copy-to-clipboard";
export type { VisuallyHiddenProps } from "@/design-system/primitives/visually-hidden";
export { VisuallyHidden } from "@/design-system/primitives/visually-hidden";
