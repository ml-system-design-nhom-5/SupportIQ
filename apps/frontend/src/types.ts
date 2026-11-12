export type Role = 'customer' | 'staff' | 'manager' | 'admin'
export interface Session { account_id: string; display_name: string; role: Role }
export interface Page<T> { items: T[]; next_cursor: string | null }
export interface Money { amount_minor: number; currency: string }
export interface Product { product_id: string; name: string; description: string; category: string; price: Money }
export interface Order {
  order_id: string; order_status: string; source_status: string; placed_at: string; order_total: Money; shipping_cost: Money;
  date_is_synthetic?: boolean;
  lines: { product_id: string; product_name: string; quantity: number }[];
  shipment: { shipment_status: string; tracking_code?: string; carrier?: string; estimated_delivery_text?: string; delivered_at?: string; timeline: {time: string; status: string}[] };
  refund: { refund_status: string; refund_amount: Money; expected_refund_time?: string } | null;
}
export interface ShopTicket { ticket_id: string; order_id: string | null; message: string; created_at: string; customer_status: string; reply: {body: string; sent_at: string} | null }
export interface Intent { label: string; probability: number; confidence_band: string; source?: string; score_kind?: string }
export interface Source { document_id: string; version: string; title: string; snippet: string; effective_from?: string; effective_to?: string; validity: string; rank: number }
export interface Citation { citation_id: string; source_type: 'kb_document' | 'order_context'; document_id?: string; version?: string; snippet?: string; field?: string; value?: unknown }
export interface Draft { text: string; segments: {segment_id: string; paragraph_index: number; text: string; citation_ids: string[]}[]; citations: Citation[] }
export interface Suggestion {
  suggestion_id: string; created_at: string; trigger: string; analysis_status: string; draft_status: string; intent_override?: string;
  analysis?: {intent: Intent; alternatives: Intent[]; documents: Source[]; routing: {recommendation: string; reason_codes: string[]}};
  draft?: Draft; warnings: {warning_id: string; reason_code?: string; code?: string}[]; reason_codes: string[]; staff_note?: string;
  versions?: Record<string, string>; step_latency_ms: Record<string, number>; trace_id: string;
}
export interface TicketSummary {ticket_id: string; created_at: string; status: string; handling_mode: string; is_authority_required: boolean; handling_started_at?: string; customer: {display_name: string}; excerpt: string; draft_status?: string; intent?: Intent}
export interface Proposal {proposal_id: string; basis: string; body: string; by: string; created_at: string}
export interface Workspace extends TicketSummary {message: {body: string; created_at: string}; order: Order | null; other_orders: Order[]; suggestion: Suggestion | null; proposal: Proposal | null; escalation: {staff_reason_codes: string[]; note?: string; by: string} | null; reply: {body: string; by: string; sent_at: string} | null; allowed_actions: string[]}
export interface Account extends Session {is_active: boolean}
export interface Versions {backend_build: string; ai_service_status: string; release_id: string | null; versions: Record<string, string> | null}
export interface Report {period: {start_at: string; end_at: string}; ticket_counts: Record<string, {created: number; closed: number}>; draft_decisions: Record<string, {count: number; share: number}>; escalations: Record<string, number>; ai_outcomes: Record<string, number>; ai_error_rate: number; end_to_end_latency_ms: {p50: number | null; p95: number | null}; suggestion_latency_ms: Record<string, {p50: number | null; p95: number | null}>; llm_cost_micro_usd: {total: number; average: number | null}; handling_time_ms: Record<string, {p50: number | null}>}
