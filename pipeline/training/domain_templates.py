"""Independent policy-derived domain template generator for Task A.

Authors domain query template families strictly from approved policy and KB
terminology (`data/knowledge/approved_kb.v2.json` and
`apps/core_backend/config/policies/intent_policy.v2.json`), never from frozen
benchmark prompts. Template families are assigned to disjoint `train`,
`calibration`, and `evaluation` groups BEFORE paraphrasing, and every output is
checked against all frozen benchmark files for exact or high-similarity overlap.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from pipeline.preparation.utils import CORE_PRODUCT_INTENTS

REPO_ROOT = Path(__file__).resolve().parents[2]

FROZEN_BENCHMARK_PATHS: Tuple[str, ...] = (
    "data/benchmarks/autoeval/v1/ml_noise.jsonl",
    "data/benchmarks/autoeval/v1/ml_oos.jsonl",
    "data/benchmarks/autoeval/v1/llm_cases.jsonl",
    "data/benchmarks/system/v1/cases.jsonl",
    "data/benchmarks/system/v2/dev/cases.jsonl",
    "data/benchmarks/system/v2/acceptance/cases.jsonl",
    "data/benchmarks/final_acceptance/cases.jsonl",
    "data/benchmarks/final_acceptance_supplement/cases.jsonl",
    "data/benchmarks/app_retrieval_gold_v2.json",
)


@dataclass(frozen=True)
class TemplateFamily:
    """A semantically distinct template family assigned atomically to one split."""

    template_group_id: str
    intent: str
    policy_source: str
    patterns: Tuple[str, ...]


# Independently authored from approved_kb.v2.json and intent_policy.v2.json concepts.
# Exactly 6 distinct template families per supported intent:
#   - 3 families -> train
#   - 1 family   -> calibration
#   - 2 families -> evaluation
POLICY_TEMPLATE_FAMILIES: Tuple[TemplateFamily, ...] = (
    # ------------------------------------------------------------------
    # 1. track_order (POL-ORD-001)
    # ------------------------------------------------------------------
    TemplateFamily(
        template_group_id="trk_ord_my_orders_nav",
        intent="track_order",
        policy_source="POL-ORD-001",
        patterns=(
            "Where inside My Orders can I inspect the current shipment stage of my purchase?",
            "Which tab under My Orders shows whether a checkout is preparing or dispatched?",
            "Which menu in the Tiki app displays Pending Confirmation versus In Transit stages?",
        ),
    ),
    TemplateFamily(
        template_group_id="trk_ord_pickup_stage",
        intent="track_order",
        policy_source="POL-ORD-001",
        patterns=(
            "What does Pick Up in Progress mean for my Tiki purchase right now?",
            "My order status says Pick Up in Progress; has the carrier collected it yet?",
            "Does Pick Up in Progress mean the seller already packed the parcel for dispatch?",
        ),
    ),
    TemplateFamily(
        template_group_id="trk_ord_code_checkpoint",
        intent="track_order",
        policy_source="POL-ORD-001",
        patterns=(
            "Where can I enter my shipment reference code to see carrier checkpoints?",
            "How do I check every sorting checkpoint listed under my Tiki shipment code?",
            "Can I tap the carrier tracking number in My Orders to view parcel movement?",
        ),
    ),
    TemplateFamily(
        template_group_id="trk_ord_pending_confirm",
        intent="track_order",
        policy_source="POL-ORD-001",
        patterns=(
            "My purchase is still listed as Pending Confirmation; how do I follow its progress?",
            "Where do I watch an order move from Pending Confirmation to In Transit?",
            "How can I check whether the merchant finished preparing my Pending Confirmation order?",
        ),
    ),
    TemplateFamily(
        template_group_id="trk_ord_parcel_route",
        intent="track_order",
        policy_source="POL-ORD-001",
        patterns=(
            "How can I follow the real-time route of an In Transit Tiki parcel?",
            "Which section shows the courier movement history once an order enters In Transit?",
            "Where is the live shipment timeline shown after a seller dispatches my item?",
        ),
    ),
    TemplateFamily(
        template_group_id="trk_ord_hub_progress",
        intent="track_order",
        policy_source="POL-ORD-001",
        patterns=(
            "How do I inspect the delivery checkpoints between sorting hubs for my parcel?",
            "Where does the app display each dispatch station my shipped order visited?",
            "Can I look up which logistics checkpoint currently holds my Tiki parcel?",
        ),
    ),
    # ------------------------------------------------------------------
    # 2. cancel_order (POL-ORD-002)
    # ------------------------------------------------------------------
    TemplateFamily(
        template_group_id="cnc_ord_processing_btn",
        intent="cancel_order",
        policy_source="POL-ORD-002",
        patterns=(
            "How do I stop a Tiki purchase that is still in Processing status?",
            "Where is the Cancel Order option when an order is still Processing?",
            "Can I void my order before the seller finishes preparing it?",
        ),
    ),
    TemplateFamily(
        template_group_id="cnc_ord_before_carrier",
        intent="cancel_order",
        policy_source="POL-ORD-002",
        patterns=(
            "Am I allowed to abort an order free of charge before carrier handover?",
            "Is there any fee if I withdraw an unfulfilled order prior to courier pickup?",
            "Can an order be stopped without penalty while it has not left for the courier?",
        ),
    ),
    TemplateFamily(
        template_group_id="cnc_ord_in_transit_rule",
        intent="cancel_order",
        policy_source="POL-ORD-002",
        patterns=(
            "The cancel button disappeared once my parcel became In Transit; how do I stop delivery?",
            "What is the procedure to turn down an In Transit shipment that can no longer be canceled?",
            "Since my purchase already entered In Transit, can I reject it when the driver calls?",
        ),
    ),
    TemplateFamily(
        template_group_id="cnc_ord_prepaid_cancel",
        intent="cancel_order",
        policy_source="POL-ORD-002",
        patterns=(
            "If I cancel an already-paid order before dispatch, what happens to the transaction?",
            "How do I request cancellation of a prepaid purchase before shipping handover?",
            "Can I withdraw a card-paid order prior to fulfillment and have it stopped immediately?",
        ),
    ),
    TemplateFamily(
        template_group_id="cnc_ord_packing_stage",
        intent="cancel_order",
        policy_source="POL-ORD-002",
        patterns=(
            "Is self-service cancellation available while my order sits in Awaiting Packing?",
            "How do I terminate a purchase in Awaiting Packing before courier handoff?",
            "Does Tiki let buyers tap Cancel Order during the Awaiting Packing stage?",
        ),
    ),
    TemplateFamily(
        template_group_id="cnc_ord_cutoff_window",
        intent="cancel_order",
        policy_source="POL-ORD-002",
        patterns=(
            "What is the cutoff stage after which an order can no longer be stopped in-app?",
            "At what shipment status does the direct Cancel Order button get disabled?",
            "Can I still abort a Tiki checkout right before it is handed to the delivery carrier?",
        ),
    ),
    # ------------------------------------------------------------------
    # 3. delivery_time (POL-SHIP-001)
    # ------------------------------------------------------------------
    TemplateFamily(
        template_group_id="del_time_fast_urban",
        intent="delivery_time",
        policy_source="POL-SHIP-001",
        patterns=(
            "How many business days does Fast Delivery take across major urban centers?",
            "What is the expected arrival window when choosing Tiki Fast Delivery in a city?",
            "How soon will a Fast Delivery parcel arrive compared with Standard Delivery?",
        ),
    ),
    TemplateFamily(
        template_group_id="del_time_standard_rural",
        intent="delivery_time",
        policy_source="POL-SHIP-001",
        patterns=(
            "How long does Standard Delivery usually take for inter-provincial or rural addresses?",
            "What is the typical transit duration for Standard Delivery outside major cities?",
            "How many business days should I allow for rural Standard Delivery on Tiki?",
        ),
    ),
    TemplateFamily(
        template_group_id="del_time_peak_weather",
        intent="delivery_time",
        policy_source="POL-SHIP-001",
        patterns=(
            "By how many days can shipping timelines extend during public holidays or severe weather?",
            "Do peak shopping seasons add extra transit days to Tiki delivery estimates?",
            "How much delay is expected during storms or holiday surges?",
        ),
    ),
    TemplateFamily(
        template_group_id="del_time_package_compare",
        intent="delivery_time",
        policy_source="POL-SHIP-001",
        patterns=(
            "What are the delivery timeframes across TikiNOW, Fast, and Standard shipping tiers?",
            "Could you compare arrival speeds for Tiki shipping service packages?",
            "How many hours or business days does each Tiki delivery tier require?",
        ),
    ),
    TemplateFamily(
        template_group_id="del_time_tikinow_express",
        intent="delivery_time",
        policy_source="POL-SHIP-001",
        patterns=(
            "How fast does TikiNOW Express arrive in inner districts of Hanoi or Da Nang?",
            "What is the promised arrival window for TikiNOW Express service?",
            "In which urban districts does TikiNOW Express complete delivery in two hours?",
        ),
    ),
    TemplateFamily(
        template_group_id="del_time_interprovincial",
        intent="delivery_time",
        policy_source="POL-SHIP-001",
        patterns=(
            "When I place an inter-provincial order, how many working days does shipping take?",
            "What transit duration applies when shipping between provinces via Standard Delivery?",
            "How long will an order take to reach a distant district under Standard service?",
        ),
    ),
    # ------------------------------------------------------------------
    # 4. delivery_issue (POL-SHIP-004)
    # ------------------------------------------------------------------
    TemplateFamily(
        template_group_id="del_iss_overdue_parcel",
        intent="delivery_issue",
        policy_source="POL-SHIP-004",
        patterns=(
            "My Tiki parcel passed its estimated arrival date and still has not turned up.",
            "The scheduled delivery window expired yesterday without any courier contact.",
            "What should I do when an order exceeds its promised delivery date?",
        ),
    ),
    TemplateFamily(
        template_group_id="del_iss_lost_replacement",
        intent="delivery_issue",
        policy_source="POL-SHIP-004",
        patterns=(
            "My shipment appears lost in transit; how do I report a missing parcel for investigation?",
            "If the courier misplaced my parcel, how does Tiki handle replacement or compensation?",
            "Who verifies courier GPS records when a Tiki shipment goes missing on the route?",
        ),
    ),
    TemplateFamily(
        template_group_id="del_iss_report_window",
        intent="delivery_issue",
        policy_source="POL-SHIP-004",
        patterns=(
            "Within how many hours must I notify support about a non-arriving shipment?",
            "What is the reporting window for flagging a late or misdelivered parcel?",
            "How quickly should I report an overdue delivery after the expected arrival date?",
        ),
    ),
    TemplateFamily(
        template_group_id="del_iss_hub_verification",
        intent="delivery_issue",
        policy_source="POL-SHIP-004",
        patterns=(
            "My shipment seems stuck without arrival; can dispatch check the delivery hub?",
            "How do I ask the dispatch team to trace a stalled parcel with the local hub?",
            "Can support inspect carrier GPS logs for a shipment that never showed up?",
        ),
    ),
    TemplateFamily(
        template_group_id="del_iss_marked_delivered",
        intent="delivery_issue",
        policy_source="POL-SHIP-004",
        patterns=(
            "The tracking page reads Successfully Delivered even though nobody handed me a parcel.",
            "Why does my order show Successfully Delivered when no package arrived at my door?",
            "I did not receive any item, yet the carrier marked the shipment Successfully Delivered.",
        ),
    ),
    TemplateFamily(
        template_group_id="del_iss_discrepant_drop",
        intent="delivery_issue",
        policy_source="POL-SHIP-004",
        patterns=(
            "No package was left at my address despite the courier closing the order as delivered.",
            "How do I dispute a false delivery completion when the parcel is still missing?",
            "The carrier logged delivery completion, but nothing reached my building.",
        ),
    ),
    # ------------------------------------------------------------------
    # 5. shipping_costs (POL-SHIP-002)
    # ------------------------------------------------------------------
    TemplateFamily(
        template_group_id="ship_cost_weight_distance",
        intent="shipping_costs",
        policy_source="POL-SHIP-002",
        patterns=(
            "How does Tiki compute delivery charges based on parcel weight and distance?",
            "Where can I preview the exact shipping charge before completing checkout?",
            "Why did the delivery fee increase for a heavier parcel on checkout?",
        ),
    ),
    TemplateFamily(
        template_group_id="ship_cost_tikipro",
        intent="shipping_costs",
        policy_source="POL-SHIP-002",
        patterns=(
            "What shipping fee discounts do TikiPRO members receive on eligible orders?",
            "How much shipping fee reduction does a Freeship voucher cover on Tiki?",
            "What minimum basket total qualifies an order for Freeship discount vouchers?",
        ),
    ),
    TemplateFamily(
        template_group_id="ship_cost_base_rates",
        intent="shipping_costs",
        policy_source="POL-SHIP-002",
        patterns=(
            "What is the standard VND delivery charge range for local city shipments?",
            "How much do inter-provincial shipping rates typically cost on Tiki?",
            "What base courier fee applies before Freeship vouchers are deducted?",
        ),
    ),
    TemplateFamily(
        template_group_id="ship_cost_threshold_149k",
        intent="shipping_costs",
        policy_source="POL-SHIP-002",
        patterns=(
            "Does an order above 149,000 VND unlock Freeship shipping fee support?",
            "How do I apply a Freeship voucher to lower my delivery charge at checkout?",
            "Up to how many VND in shipping costs can Freeship waive on one purchase?",
        ),
    ),
    TemplateFamily(
        template_group_id="ship_cost_city_vs_prov",
        intent="shipping_costs",
        policy_source="POL-SHIP-002",
        patterns=(
            "How do local intra-city courier fees compare to cross-province delivery charges?",
            "What is the price difference between same-city and inter-provincial shipping?",
            "Why is shipping to another province higher than intra-city delivery?",
        ),
    ),
    TemplateFamily(
        template_group_id="ship_cost_voucher_stack",
        intent="shipping_costs",
        policy_source="POL-SHIP-002",
        patterns=(
            "How is the final shipping charge calculated after applying TikiPRO Freeship?",
            "Will my checkout screen show the shipping fee breakdown with Freeship applied?",
            "What shipping charge remains if my delivery fee exceeds the Freeship discount cap?",
        ),
    ),
    # ------------------------------------------------------------------
    # 6. return_policy (POL-RET-001, POL-RET-003)
    # ------------------------------------------------------------------
    TemplateFamily(
        template_group_id="ret_pol_packaging_rules",
        intent="return_policy",
        policy_source="POL-RET-001",
        patterns=(
            "What condition must an item and its original packaging be in to qualify for return?",
            "Do I need to include promotional gifts, accessories, and invoices when returning an item?",
            "Does breaking the security seal disqualify a product from standard return eligibility?",
        ),
    ),
    TemplateFamily(
        template_group_id="ret_pol_restricted_food",
        intent="return_policy",
        policy_source="POL-RET-003",
        patterns=(
            "Are Tiki Ngon fresh groceries or dietary supplements eligible for change-of-mind returns?",
            "Which categories are excluded from returns if I simply decide I do not want them?",
            "Can electronic service vouchers or mobile top-up cards be sent back after purchase?",
        ),
    ),
    TemplateFamily(
        template_group_id="ret_pol_defect_exception",
        intent="return_policy",
        policy_source="POL-RET-003",
        patterns=(
            "If a restricted category item arrives with a manufacturer defect, can it still be returned?",
            "Are clearance items marked non-returnable covered if Tiki sent the wrong product?",
            "What exceptions allow returning underwear or swimwear when an error occurred?",
        ),
    ),
    TemplateFamily(
        template_group_id="ret_pol_seller_windows",
        intent="return_policy",
        policy_source="POL-RET-001",
        patterns=(
            "How many days do I have to return a Tiki Trading item versus a third-party seller item?",
            "Does the 30-day return window apply to marketplace partner stores or only Tiki Trading?",
            "What is the return deadline for marketplace partner products after delivery?",
        ),
    ),
    TemplateFamily(
        template_group_id="ret_pol_unsealed_cosmetic",
        intent="return_policy",
        policy_source="POL-RET-003",
        patterns=(
            "Are opened cosmetics or unsealed skincare items allowed for personal-preference returns?",
            "What is the rule on returning chemical or beauty products once the seal is broken?",
            "Can I send back opened makeup just because I changed my mind?",
        ),
    ),
    TemplateFamily(
        template_group_id="ret_pol_laundered_used",
        intent="return_policy",
        policy_source="POL-RET-001",
        patterns=(
            "Are apparel items still eligible for return if they were washed or worn once?",
            "Does Tiki accept returns on products showing signs of usage?",
            "What happens to return eligibility if promotional gifts are missing from the box?",
        ),
    ),
    # ------------------------------------------------------------------
    # 7. return_product (POL-RET-002)
    # ------------------------------------------------------------------
    TemplateFamily(
        template_group_id="ret_prod_app_steps",
        intent="return_product",
        policy_source="POL-RET-002",
        patterns=(
            "Which menu in Account > Order Management lets me initiate a product return?",
            "Walk me through submitting a return request for a Delivered order on the app.",
            "How do I start sending back a defective item from my Order Management page?",
        ),
    ),
    TemplateFamily(
        template_group_id="ret_prod_evidence_upload",
        intent="return_product",
        policy_source="POL-RET-002",
        patterns=(
            "How many defect photos or videos must I attach when filing a return request?",
            "Do I need to upload pictures showing the fault before submitting a product return?",
            "What media files are required inside the Request Return/Exchange form?",
        ),
    ),
    TemplateFamily(
        template_group_id="ret_prod_dropoff_option",
        intent="return_product",
        policy_source="POL-RET-002",
        patterns=(
            "Can I drop off a return parcel at a Tiki partner post office instead of waiting at home?",
            "Where do I bring an approved return item if I prefer post-office drop-off?",
            "How do partner post-office drop-offs work for Tiki product returns?",
        ),
    ),
    TemplateFamily(
        template_group_id="ret_prod_courier_pickup",
        intent="return_product",
        policy_source="POL-RET-002",
        patterns=(
            "Within how many business days does the courier arrive to collect a return package?",
            "How do I arrange free doorstep pickup after filing a return on Tiki?",
            "Does Tiki send a shipping courier to pick up returned products at no cost?",
        ),
    ),
    TemplateFamily(
        template_group_id="ret_prod_submit_exchange",
        intent="return_product",
        policy_source="POL-RET-002",
        patterns=(
            "I want to send back a damaged delivery and file a return on my Delivered order.",
            "How do I log a return submission in the Tiki app for an item I received?",
            "Where do I tap Request Return/Exchange to hand an item back to the courier?",
        ),
    ),
    TemplateFamily(
        template_group_id="ret_prod_handover_flow",
        intent="return_product",
        policy_source="POL-RET-002",
        patterns=(
            "What steps do I follow to hand my returned package over to Tiki logistics?",
            "After selecting a return reason in the app, how is parcel collection scheduled?",
            "How do I complete the in-app return workflow and hand the parcel to the driver?",
        ),
    ),
    # ------------------------------------------------------------------
    # 8. refund_policy (POL-REFUND-001, POL-REFUND-002)
    # ------------------------------------------------------------------
    TemplateFamily(
        template_group_id="ref_pol_warehouse_inspect",
        intent="refund_policy",
        policy_source="POL-REFUND-001",
        patterns=(
            "Does the Tiki warehouse need to inspect returned goods before a refund is approved?",
            "What conditions must be met before a refund is authorized on a returned item?",
            "When does Tiki qualify an order for monetary reimbursement?",
        ),
    ),
    TemplateFamily(
        template_group_id="ref_pol_shipping_nonrefund",
        intent="refund_policy",
        policy_source="POL-REFUND-001",
        patterns=(
            "Are original delivery charges reimbursed if I return an order for personal reasons?",
            "Under what circumstances are initial shipping fees excluded from a refund?",
            "Does Tiki refund outward shipping costs on a change-of-mind return?",
        ),
    ),
    TemplateFamily(
        template_group_id="ref_pol_reconciliation",
        intent="refund_policy",
        policy_source="POL-REFUND-001",
        patterns=(
            "Why must authorized customer service staff reconcile refund approvals first?",
            "What are Tiki's general rules governing refund eligibility and reconciliation?",
            "Can a refund be issued prior to order cancellation or return inspection?",
        ),
    ),
    TemplateFamily(
        template_group_id="ref_pol_method_rules",
        intent="refund_policy",
        policy_source="POL-REFUND-002",
        patterns=(
            "What refund rules apply across Tiki Coins, e-wallets, domestic ATM, and credit cards?",
            "How does Tiki's refund policy specify payout timeframes for different card types?",
            "What is the official policy on how refunds return to the original payment channel?",
        ),
    ),
    TemplateFamily(
        template_group_id="ref_pol_approval_criteria",
        intent="refund_policy",
        policy_source="POL-REFUND-001",
        patterns=(
            "What criteria govern refund approval and whether shipping fees are covered?",
            "What are the general terms for getting a full refund versus paying original shipping?",
            "Explain the rules deciding whether an order qualifies for full reimbursement.",
        ),
    ),
    TemplateFamily(
        template_group_id="ref_pol_cancel_vs_return",
        intent="refund_policy",
        policy_source="POL-REFUND-001",
        patterns=(
            "How do refund eligibility rules differ between pre-dispatch cancellations and returns?",
            "Are weekends and public holidays excluded under Tiki's card refund policy?",
            "What policy governs whether original freight charges are refunded?",
        ),
    ),
    # ------------------------------------------------------------------
    # 9. request_refund (POL-REFUND-001, POL-REFUND-002)
    # ------------------------------------------------------------------
    TemplateFamily(
        template_group_id="req_ref_submit_claim",
        intent="request_refund",
        policy_source="POL-REFUND-001",
        patterns=(
            "I canceled a prepaid checkout prior to dispatch and need to initiate reimbursement.",
            "I want to apply for my money back now that my return passed inspection.",
            "How do I file a reimbursement claim after returning an item to the warehouse?",
        ),
    ),
    TemplateFamily(
        template_group_id="req_ref_card_payout",
        intent="request_refund",
        policy_source="POL-REFUND-002",
        patterns=(
            "I would like my refund credited back to my Visa credit card.",
            "Can you initiate a refund payout to my domestic Napas ATM card?",
            "Please submit my refund to the original MoMo e-wallet I used at checkout.",
        ),
    ),
    TemplateFamily(
        template_group_id="req_ref_tiki_coins",
        intent="request_refund",
        policy_source="POL-REFUND-002",
        patterns=(
            "I want to claim my refund into my Tiki Coins Wallet.",
            "Please process a reimbursement request for my canceled purchase.",
            "How do I trigger a money-back request for an order I canceled before dispatch?",
        ),
    ),
    TemplateFamily(
        template_group_id="req_ref_wait_days",
        intent="request_refund",
        policy_source="POL-REFUND-002",
        patterns=(
            "I am requesting a refund; how long until the money reaches my bank card or wallet?",
            "When I submit a refund to ZaloPay or Viettel Money, how soon will I get paid?",
            "How many working days after I request a refund will my Visa card be credited?",
        ),
    ),
    TemplateFamily(
        template_group_id="req_ref_initiate_action",
        intent="request_refund",
        policy_source="POL-REFUND-001",
        patterns=(
            "Help me submit a refund request for the order I returned yesterday.",
            "I need to ask for a refund on a transaction that was canceled prior to shipping.",
            "Can I initiate a reimbursement back to my original bank account now?",
        ),
    ),
    TemplateFamily(
        template_group_id="req_ref_timeline_ask",
        intent="request_refund",
        policy_source="POL-REFUND-002",
        patterns=(
            "I want my money back to my linked bank card; how many days will that take?",
            "Please process my refund request and let me know the payout window for Napas ATM.",
            "Can you start a refund to my e-wallet and confirm the 1-2 business day window?",
        ),
    ),
    # ------------------------------------------------------------------
    # 10. refund_status (POL-REFUND-007)
    # ------------------------------------------------------------------
    TemplateFamily(
        template_group_id="ref_stat_menu_nav",
        intent="refund_status",
        policy_source="POL-REFUND-007",
        patterns=(
            "Where under Account Details > Return & Refund Management can I check my refund progress?",
            "How do I inspect the current stage of my pending refund in the Tiki app?",
            "Which screen lists my refund history and live payout state?",
        ),
    ),
    TemplateFamily(
        template_group_id="ref_stat_stages",
        intent="refund_status",
        policy_source="POL-REFUND-007",
        patterns=(
            "My refund reads Reconciliation Processing; what does that status mean right now?",
            "What is the difference between Reconciliation Processing and Transferred to Bank?",
            "My refund says Transferred to Bank, so when will it update to Refund Succeeded?",
        ),
    ),
    TemplateFamily(
        template_group_id="ref_stat_succeeded_check",
        intent="refund_status",
        policy_source="POL-REFUND-007",
        patterns=(
            "Has my refund moved to Refund Succeeded yet?",
            "How do I check whether Tiki already dispatched my refund to the issuing bank?",
            "Where can I see if my reimbursement is still under customer support review?",
        ),
    ),
    TemplateFamily(
        template_group_id="ref_stat_trace_code",
        intent="refund_status",
        policy_source="POL-REFUND-007",
        patterns=(
            "Where do I find the bank transaction tracing reference code for a completed refund?",
            "My refund shows Refund Succeeded; how can I view its bank tracing reference number?",
            "Can I look up the payout reference code inside Return & Refund Management?",
        ),
    ),
    TemplateFamily(
        template_group_id="ref_stat_lookup_progress",
        intent="refund_status",
        policy_source="POL-REFUND-007",
        patterns=(
            "How can I monitor whether my refund transfer has cleared with the bank?",
            "Where do I check the latest status update on my reimbursement claim?",
            "I want to look up my refund state and bank reference number in my account.",
        ),
    ),
    TemplateFamily(
        template_group_id="ref_stat_pending_check",
        intent="refund_status",
        policy_source="POL-REFUND-007",
        patterns=(
            "Why is my refund still sitting in Reconciliation Processing?",
            "How do I track an already-submitted refund from Transferred to Bank to completion?",
            "Where can I see the current status of the refund Tiki approved for me?",
        ),
    ),
    # ------------------------------------------------------------------
    # 11. payment_issue (POL-PAY-001, POL-PAY-004)
    # ------------------------------------------------------------------
    TemplateFamily(
        template_group_id="pay_iss_gateway_latency",
        intent="payment_issue",
        policy_source="POL-PAY-001",
        patterns=(
            "Money left my e-wallet during checkout, yet my Tiki purchase still failed to confirm.",
            "Why does my order stay unconfirmed after the payment gateway deducted my funds?",
            "My card was charged, but the checkout order did not transition out of pending payment.",
        ),
    ),
    TemplateFamily(
        template_group_id="pay_iss_auto_reconcile",
        intent="payment_issue",
        policy_source="POL-PAY-001",
        patterns=(
            "If payment gateway transmission lags, how long until Tiki reconciles or auto-refunds?",
            "My payment deducted over an hour ago and the order is still unconfirmed; what now?",
            "Will an unconfirmed debited transaction reverse automatically within 24-72 business hours?",
        ),
    ),
    TemplateFamily(
        template_group_id="pay_iss_double_charge",
        intent="payment_issue",
        policy_source="POL-PAY-004",
        patterns=(
            "Network lag caused my credit card to be billed twice for the same Tiki order code.",
            "I see two identical deductions on my e-wallet for one single order.",
            "How does Tiki resolve a duplicate charge recorded during end-of-day bank settlement?",
        ),
    ),
    TemplateFamily(
        template_group_id="pay_iss_awaiting_payment",
        intent="payment_issue",
        policy_source="POL-PAY-001",
        patterns=(
            "My bank account shows a debit, yet the order remains stuck in Awaiting Payment.",
            "Why is my order still marked Awaiting Payment even though my wallet was charged?",
            "The transaction succeeded on my banking app, but Tiki still displays Awaiting Payment.",
        ),
    ),
    TemplateFamily(
        template_group_id="pay_iss_duplicate_settlement",
        intent="payment_issue",
        policy_source="POL-PAY-004",
        patterns=(
            "My card statement has a double deduction for one purchase; do I need a dispute form?",
            "Wait 48 business hours or file a dispute when charged twice on the same order code?",
            "Two charges went through for one checkout; when will the extra charge be reversed?",
        ),
    ),
    TemplateFamily(
        template_group_id="pay_iss_failed_checkout",
        intent="payment_issue",
        policy_source="POL-PAY-001",
        patterns=(
            "Checkout timed out with a payment error right after deducting money from my bank.",
            "My e-wallet balance dropped, yet the Tiki payment screen never confirmed the order.",
            "A banking deduction happened for a failed transaction; how will it be reconciled?",
        ),
    ),
    # ------------------------------------------------------------------
    # 12. human_agent (intent_policy.v2.json / FR-04 / FR-05)
    # ------------------------------------------------------------------
    TemplateFamily(
        template_group_id="hum_agt_live_rep",
        intent="human_agent",
        policy_source="intent_policy.v2.json",
        patterns=(
            "Can you connect me directly with a live customer support representative?",
            "I would like to speak with a human support agent instead of automated help.",
            "Please transfer my conversation to a real CSKH specialist right away.",
        ),
    ),
    TemplateFamily(
        template_group_id="hum_agt_escalate_person",
        intent="human_agent",
        policy_source="intent_policy.v2.json",
        patterns=(
            "Can a human specialist take over and review this case manually?",
            "Route me to a live support staff member who can handle my inquiry.",
            "I need an actual support representative to assist me directly.",
        ),
    ),
    TemplateFamily(
        template_group_id="hum_agt_operator_chat",
        intent="human_agent",
        policy_source="intent_policy.v2.json",
        patterns=(
            "Put me through to an operator from customer care.",
            "How do I reach a live person on Tiki customer support?",
            "I prefer talking to a human agent rather than automated replies.",
        ),
    ),
    TemplateFamily(
        template_group_id="hum_agt_staff_handoff",
        intent="human_agent",
        policy_source="intent_policy.v2.json",
        patterns=(
            "Please hand my ticket over to a human customer service officer.",
            "Is a live support agent available right now to chat with me?",
            "Let me talk to a real customer care person about my issue.",
        ),
    ),
    TemplateFamily(
        template_group_id="hum_agt_direct_specialist",
        intent="human_agent",
        policy_source="intent_policy.v2.json",
        patterns=(
            "I want to escalate straight to a human customer support agent.",
            "Connect this ticket to a live staff member for personal assistance.",
            "Can someone from the support team speak with me directly?",
        ),
    ),
    TemplateFamily(
        template_group_id="hum_agt_supervisor_req",
        intent="human_agent",
        policy_source="intent_policy.v2.json",
        patterns=(
            "May I speak to a live customer service agent or supervisor?",
            "Transfer me to a human representative to resolve this personally.",
            "Please assign a live customer support specialist to my inquiry.",
        ),
    ),
)

# Deterministic split assignment per template family index (0..5) within each intent:
#   indices 0, 1, 2 -> train (3 families/intent = 36 groups)
#   index 3         -> calibration (1 family/intent = 12 groups)
#   indices 4, 5    -> evaluation (2 families/intent = 24 groups)
GROUP_INDEX_TO_PARTITION: Dict[int, str] = {
    0: "train",
    1: "train",
    2: "train",
    3: "calibration",
    4: "evaluation",
    5: "evaluation",
}


def normalize_text(text: str) -> str:
    """Lowercase alphanumeric normalization for leakage checks."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", text.lower())).strip()


def tokenize(text: str) -> List[str]:
    """Tokenize normalized text into whitespace-delimited words."""
    norm = normalize_text(text)
    return norm.split() if norm else []


def token_f1(text_a: str, text_b: str) -> float:
    """Compute bag-of-tokens F1 similarity between two texts."""
    toks_a = tokenize(text_a)
    toks_b = tokenize(text_b)
    if not toks_a or not toks_b:
        return 0.0
    counts_a = Counter(toks_a)
    counts_b = Counter(toks_b)
    overlap = sum(min(counts_a[t], counts_b[t]) for t in counts_a)
    if overlap == 0:
        return 0.0
    prec = overlap / len(toks_a)
    rec = overlap / len(toks_b)
    return 2.0 * prec * rec / (prec + rec)


def load_frozen_benchmark_texts(repo_root: Path = REPO_ROOT) -> List[Dict[str, str]]:
    """Load all query/text prompts from frozen benchmark files for contamination auditing."""
    entries: List[Dict[str, str]] = []
    for rel_path in FROZEN_BENCHMARK_PATHS:
        full_path = repo_root / rel_path
        if not full_path.exists():
            continue
        if full_path.suffix == ".jsonl":
            with full_path.open("r", encoding="utf-8") as f:
                for idx, line in enumerate(f):
                    if not line.strip():
                        continue
                    obj = json.loads(line)
                    text = obj.get("text") or obj.get("query") or ""
                    if text:
                        entries.append({
                            "source": rel_path,
                            "case_id": str(obj.get("id", f"row-{idx}")),
                            "text": str(text),
                        })
        elif full_path.suffix == ".json":
            data = json.loads(full_path.read_text(encoding="utf-8"))
            items = data if isinstance(data, list) else data.get("cases", [])
            for idx, obj in enumerate(items):
                if isinstance(obj, dict):
                    text = obj.get("query") or obj.get("text") or ""
                    if text:
                        entries.append({
                            "source": rel_path,
                            "case_id": str(obj.get("id", f"row-{idx}")),
                            "text": str(text),
                        })
    return entries


def generate_grouped_domain_records() -> List[Dict[str, Any]]:
    """Assign template families to partitions BEFORE expanding paraphrases."""
    by_intent: Dict[str, List[TemplateFamily]] = {}
    for fam in POLICY_TEMPLATE_FAMILIES:
        by_intent.setdefault(fam.intent, []).append(fam)

    if set(by_intent.keys()) != set(CORE_PRODUCT_INTENTS):
        raise ValueError(
            f"Expected 12 CORE_PRODUCT_INTENTS, found mismatch: "
            f"missing={sorted(set(CORE_PRODUCT_INTENTS) - set(by_intent.keys()))}, "
            f"extra={sorted(set(by_intent.keys()) - set(CORE_PRODUCT_INTENTS))}"
        )

    records: List[Dict[str, Any]] = []
    for intent in sorted(by_intent.keys()):
        families = by_intent[intent]
        if len(families) != 6:
            raise ValueError(f"Expected 6 template families for {intent}, got {len(families)}")
        for idx, fam in enumerate(families):
            partition = GROUP_INDEX_TO_PARTITION[idx]
            for p_idx, text in enumerate(fam.patterns):
                sample_id = f"dom_{fam.template_group_id}_{p_idx:02d}"
                records.append({
                    "sample_id": sample_id,
                    "instruction": text,
                    "intent": fam.intent,
                    "template_group_id": fam.template_group_id,
                    "partition": partition,
                    "policy_source": fam.policy_source,
                })
    return records


def check_gold_benchmark_leakage(
    records: Sequence[Dict[str, Any]],
    *,
    repo_root: Path = REPO_ROOT,
    max_token_f1: float = 0.65,
) -> Dict[str, Any]:
    """Verify zero exact matches and bounded token-F1 against all frozen benchmarks."""
    gold_entries = load_frozen_benchmark_texts(repo_root)
    gold_norm_map = {normalize_text(e["text"]): e for e in gold_entries}

    exact_matches: List[Dict[str, str]] = []
    high_similarity: List[Dict[str, Any]] = []
    global_max_f1 = 0.0
    max_pair: Dict[str, Any] = {}

    for rec in records:
        text = rec["instruction"]
        norm = normalize_text(text)
        if norm in gold_norm_map:
            match = gold_norm_map[norm]
            exact_matches.append({
                "sample_id": rec["sample_id"],
                "gold_source": match["source"],
                "gold_case_id": match["case_id"],
            })

        best_f1 = 0.0
        best_gold: Dict[str, str] | None = None
        for g in gold_entries:
            score = token_f1(text, g["text"])
            if score > best_f1:
                best_f1 = score
                best_gold = g

        if best_f1 > global_max_f1 and best_gold is not None:
            global_max_f1 = best_f1
            max_pair = {
                "sample_id": rec["sample_id"],
                "sample_text": text,
                "gold_source": best_gold["source"],
                "gold_case_id": best_gold["case_id"],
                "gold_text": best_gold["text"],
                "token_f1": round(best_f1, 4),
            }

        if best_f1 >= max_token_f1 and best_gold is not None:
            high_similarity.append({
                "sample_id": rec["sample_id"],
                "sample_text": text,
                "gold_source": best_gold["source"],
                "gold_case_id": best_gold["case_id"],
                "token_f1": round(best_f1, 4),
            })

    report = {
        "frozen_benchmark_prompts_checked": len(gold_entries),
        "domain_records_checked": len(records),
        "max_allowed_token_f1": max_token_f1,
        "observed_max_token_f1": round(global_max_f1, 4),
        "max_similarity_pair": max_pair,
        "exact_match_count": len(exact_matches),
        "high_similarity_count": len(high_similarity),
        "exact_matches": exact_matches,
        "high_similarity": high_similarity,
        "passed": (len(exact_matches) == 0 and len(high_similarity) == 0),
    }
    if not report["passed"]:
        raise ValueError(
            f"Gold benchmark contamination check failed: "
            f"exact={len(exact_matches)}, high_sim={len(high_similarity)}, max_f1={global_max_f1:.4f}"
        )
    return report


def export_domain_dataset(
    output_dir: Path,
    *,
    repo_root: Path = REPO_ROOT,
    max_token_f1: float = 0.65,
) -> Dict[str, Any]:
    """Generate, validate, and write the grouped policy-derived domain dataset."""
    records = generate_grouped_domain_records()

    # Verify zero template_group_id overlap across partitions
    groups_by_part: Dict[str, set[str]] = {"train": set(), "calibration": set(), "evaluation": set()}
    counts_by_part: Dict[str, int] = {"train": 0, "calibration": 0, "evaluation": 0}
    for rec in records:
        part = rec["partition"]
        groups_by_part[part].add(rec["template_group_id"])
        counts_by_part[part] += 1

    assert groups_by_part["train"].isdisjoint(groups_by_part["calibration"])
    assert groups_by_part["train"].isdisjoint(groups_by_part["evaluation"])
    assert groups_by_part["calibration"].isdisjoint(groups_by_part["evaluation"])

    leakage_report = check_gold_benchmark_leakage(
        records, repo_root=repo_root, max_token_f1=max_token_f1
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = output_dir / "domain_templates.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    dataset_sha256 = hashlib.sha256(jsonl_path.read_bytes()).hexdigest().lower()
    try:
        rel_dataset_path = str(jsonl_path.relative_to(repo_root)).replace("\\", "/")
    except ValueError:
        rel_dataset_path = str(jsonl_path)

    manifest = {
        "dataset_path": rel_dataset_path,
        "dataset_sha256": dataset_sha256,
        "total_records": len(records),
        "supported_intents_count": len(CORE_PRODUCT_INTENTS),
        "partition_sample_counts": counts_by_part,
        "partition_template_group_counts": {k: len(v) for k, v in groups_by_part.items()},
        "disjoint_template_groups_verified": True,
        "leakage_audit": leakage_report,
    }
    (output_dir / "domain_templates_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return manifest


@dataclass(frozen=True)
class NegativeTemplateFamily:
    """An independent out-of-scope or ambiguous negative template family assigned to one split."""

    template_group_id: str
    negative_kind: str  # "off_domain", "underspecified_ambiguous", "unsupported_platform"
    partition: str  # "train", "calibration", or "evaluation"
    patterns: Tuple[str, ...]


# Independently authored non-supported / OOD / ambiguous negative families (30 groups, 3 paraphrases each = 90).
# Partitioned strictly by template_group_id BEFORE paraphrasing:
#   - 12 groups (36 rows) -> train (for KL-to-uniform negative regularization)
#   -  9 groups (27 rows) -> calibration (for choosing scalar calibration vs learned rejection)
#   -  9 groups (27 rows) -> evaluation (independent held-out OOD benchmark)
# Authored without inspecting or paraphrasing any failed frozen benchmark prompts.
NEGATIVE_TEMPLATE_FAMILIES: Tuple[NegativeTemplateFamily, ...] = (
    # --- TRAIN (12 families: 4 off_domain, 4 underspecified_ambiguous, 4 unsupported_platform) ---
    NegativeTemplateFamily(
        template_group_id="neg_trn_weather_forecast",
        negative_kind="off_domain",
        partition="train",
        patterns=(
            "Will the monsoon rain reach downtown Ho Chi Minh City tomorrow afternoon?",
            "Could you tell me the humidity forecast for Hanoi this coming weekend?",
            "What kind of evening temperatures should travelers expect in Da Nang tonight?",
        ),
    ),
    NegativeTemplateFamily(
        template_group_id="neg_trn_cooking_recipe",
        negative_kind="off_domain",
        partition="train",
        patterns=(
            "How long should I simmer beef bones to get clear broth for noodle soup?",
            "What ratio of flour to butter works best when baking crisp croissants?",
            "Can I substitute coconut milk for heavy cream in a vegetable curry dish?",
        ),
    ),
    NegativeTemplateFamily(
        template_group_id="neg_trn_software_syntax",
        negative_kind="off_domain",
        partition="train",
        patterns=(
            "Why does a Python generator raise StopIteration when exhausted inside a helper?",
            "How do I rebase two diverging feature branches in Git without losing commits?",
            "What causes a CSS flex container to overflow horizontally on small screens?",
        ),
    ),
    NegativeTemplateFamily(
        template_group_id="neg_trn_fitness_routine",
        negative_kind="off_domain",
        partition="train",
        patterns=(
            "How many minutes of moderate cycling per week improve cardiovascular endurance?",
            "Which shoulder warm-up stretches prevent stiffness after heavy desk work?",
            "Should distance runners drink electrolytes before or after an early morning run?",
        ),
    ),
    NegativeTemplateFamily(
        template_group_id="neg_trn_vague_broken",
        negative_kind="underspecified_ambiguous",
        partition="train",
        patterns=(
            "Something looks wrong on my end and nothing is moving forward.",
            "Can someone take a look because what happened earlier still seems broken?",
            "Things feel stuck right now and I have no idea what step comes next.",
        ),
    ),
    NegativeTemplateFamily(
        template_group_id="neg_trn_vague_explain",
        negative_kind="underspecified_ambiguous",
        partition="train",
        patterns=(
            "Why did it suddenly do that when I tried finishing things just now?",
            "This whole thing makes zero sense to me; could you clear it up?",
            "I am confused about whatever changed since yesterday evening.",
        ),
    ),
    NegativeTemplateFamily(
        template_group_id="neg_trn_vague_fix",
        negative_kind="underspecified_ambiguous",
        partition="train",
        patterns=(
            "Please help fix the problem I noticed earlier today.",
            "Is there any way to sort this whole situation out quickly?",
            "I keep running into an obstacle here and need someone to handle it.",
        ),
    ),
    NegativeTemplateFamily(
        template_group_id="neg_trn_vague_status",
        negative_kind="underspecified_ambiguous",
        partition="train",
        patterns=(
            "Any update on the thing I asked about a couple of days back?",
            "Could you check whether that went through yet on your side?",
            "I just wanted to see where everything stands at the moment.",
        ),
    ),
    NegativeTemplateFamily(
        template_group_id="neg_trn_loyalty_points",
        negative_kind="unsupported_platform",
        partition="train",
        patterns=(
            "How do I redeem silver tier reward points toward movie theater vouchers?",
            "When do accrued member Astra bonus coins expire inside my loyalty tier?",
            "Can reward points earned from dining partners transfer to another member wallet?",
        ),
    ),
    NegativeTemplateFamily(
        template_group_id="neg_trn_careers_jobs",
        negative_kind="unsupported_platform",
        partition="train",
        patterns=(
            "Where do software engineering candidates upload resumes for seasonal internships?",
            "Does your fulfillment center in Binh Duong have open warehouse associate shifts?",
            "Whom should university graduates contact regarding corporate operations internships?",
        ),
    ),
    NegativeTemplateFamily(
        template_group_id="neg_trn_seller_onboarding",
        negative_kind="unsupported_platform",
        partition="train",
        patterns=(
            "What business registration papers do third-party merchants submit to open a storefront?",
            "How long does marketplace compliance take to approve a new brand merchant account?",
            "Where can wholesale suppliers view marketplace commission fee tiers for electronics?",
        ),
    ),
    NegativeTemplateFamily(
        template_group_id="neg_trn_newsletter_ads",
        negative_kind="unsupported_platform",
        partition="train",
        patterns=(
            "How can I turn off seasonal promotional push notifications without disabling SMS?",
            "Where is the preference toggle to opt out of weekly marketing digests?",
            "Why am I still receiving flash-sale reminder emails after muting newsletters?",
        ),
    ),
    # --- CALIBRATION (9 families: 3 off_domain, 3 underspecified_ambiguous, 3 unsupported_platform) ---
    NegativeTemplateFamily(
        template_group_id="neg_cal_astronomy_facts",
        negative_kind="off_domain",
        partition="calibration",
        patterns=(
            "How many Earth days does Jupiter take to complete one orbit around the Sun?",
            "Why do total solar eclipses appear visible only along a narrow geographic path?",
            "Which optical telescope lenses work best for spotting Saturn rings from a balcony?",
        ),
    ),
    NegativeTemplateFamily(
        template_group_id="neg_cal_gardening_tips",
        negative_kind="off_domain",
        partition="calibration",
        patterns=(
            "How often should indoor peace lilies be watered during dry winter air?",
            "What soil pH range helps potted blueberry shrubs produce sweeter fruit?",
            "Why do basil leaves turn yellow at the bottom stem when placed in shade?",
        ),
    ),
    NegativeTemplateFamily(
        template_group_id="neg_cal_music_theory",
        negative_kind="off_domain",
        partition="calibration",
        patterns=(
            "What notes make up a diminished seventh chord starting on F sharp?",
            "How do jazz pianists voice a minor nine chord cleanly in the left hand?",
            "Why does tuning a guitar half a step flat reduce string tension on acoustic necks?",
        ),
    ),
    NegativeTemplateFamily(
        template_group_id="neg_cal_vague_unclear",
        negative_kind="underspecified_ambiguous",
        partition="calibration",
        patterns=(
            "Everything stopped responding halfway through and I cannot finish.",
            "That button behaved strangely again—what am I supposed to press next?",
            "Wait, did that actually work or do I need to redo everything from scratch?",
        ),
    ),
    NegativeTemplateFamily(
        template_group_id="neg_cal_vague_mystery",
        negative_kind="underspecified_ambiguous",
        partition="calibration",
        patterns=(
            "Why does this keep giving me the exact same strange result every time?",
            "Can someone clarify what I might have missed earlier?",
            "I tried twice already and still have no clue what went sideways.",
        ),
    ),
    NegativeTemplateFamily(
        template_group_id="neg_cal_vague_multi",
        negative_kind="underspecified_ambiguous",
        partition="calibration",
        patterns=(
            "Hold on, should I wait longer or restart the whole process right now?",
            "None of these messages seem to match what actually showed up for me.",
            "I am not sure which rule applies here given everything happening at once.",
        ),
    ),
    NegativeTemplateFamily(
        template_group_id="neg_cal_gift_registry",
        negative_kind="unsupported_platform",
        partition="calibration",
        patterns=(
            "Can wedding guests contribute partial amounts toward an appliance gift registry?",
            "How do recipients send custom printed thank-you notes for registry gifts?",
            "Is there a way to mark a public baby registry hidden from search engines?",
        ),
    ),
    NegativeTemplateFamily(
        template_group_id="neg_cal_press_media",
        negative_kind="unsupported_platform",
        partition="calibration",
        patterns=(
            "Who handles media interview requests and high-resolution corporate brand logos?",
            "Where can technology journalists download your latest annual sustainability report?",
            "Is there a public press office inbox for podcast sponsorship inquiries?",
        ),
    ),
    NegativeTemplateFamily(
        template_group_id="neg_cal_campus_discount",
        negative_kind="unsupported_platform",
        partition="calibration",
        patterns=(
            "How do university students verify enrollment to unlock academic software bundles?",
            "Do alumni email addresses qualify for annual education membership renewals?",
            "Where can teachers submit school ID scans for classroom supply rebates?",
        ),
    ),
    # --- EVALUATION (9 families: 3 off_domain, 3 underspecified_ambiguous, 3 unsupported_platform) ---
    NegativeTemplateFamily(
        template_group_id="neg_evl_transit_history",
        negative_kind="off_domain",
        partition="evaluation",
        patterns=(
            "Which historical railway line connected northern and southern cities in 1936?",
            "How fast do high-speed magnetic levitation commuter trains accelerate?",
            "What time does the earliest municipal bus usually depart from district terminals?",
        ),
    ),
    NegativeTemplateFamily(
        template_group_id="neg_evl_photography_optics",
        negative_kind="off_domain",
        partition="evaluation",
        patterns=(
            "How does narrowing camera aperture to f/11 increase depth of field in landscapes?",
            "Why do raw camera files preserve wider highlight detail than compressed JPEGs?",
            "Which tripod head style makes panning smooth for outdoor wildlife video?",
        ),
    ),
    NegativeTemplateFamily(
        template_group_id="neg_evl_marine_biology",
        negative_kind="off_domain",
        partition="evaluation",
        patterns=(
            "How deep do emperor penguins typically dive when hunting squid under sea ice?",
            "What causes bioluminescent plankton to glow brightly along warm coastal waves?",
            "Why do coral reefs depend on symbiotic algae for vibrant surface coloration?",
        ),
    ),
    NegativeTemplateFamily(
        template_group_id="neg_evl_vague_stuck",
        negative_kind="underspecified_ambiguous",
        partition="evaluation",
        patterns=(
            "Wait a second, why is nothing loading properly after I tapped continue?",
            "Something unexpected popped up right at the end and wiped my progress.",
            "Could anybody check what just happened because everything looks blank now?",
        ),
    ),
    NegativeTemplateFamily(
        template_group_id="neg_evl_vague_concern",
        negative_kind="underspecified_ambiguous",
        partition="evaluation",
        patterns=(
            "I feel pretty uncertain whether that step actually saved on your servers.",
            "Nobody responded clearly yet about the unusual error message I saw.",
            "Why does this keep bouncing me back to the beginning without explaining why?",
        ),
    ),
    NegativeTemplateFamily(
        template_group_id="neg_evl_vague_request",
        negative_kind="underspecified_ambiguous",
        partition="evaluation",
        patterns=(
            "Please tell me honestly if this whole setup is even going to work out.",
            "I need guidance before I touch anything else and make it worse.",
            "What am I missing here when everything looks identical to yesterday?",
        ),
    ),
    NegativeTemplateFamily(
        template_group_id="neg_evl_affiliate_program",
        negative_kind="unsupported_platform",
        partition="evaluation",
        patterns=(
            "How long are affiliate referral cookies tracked after a blogger shares a link?",
            "What minimum payout balance is required for creator commission bank transfers?",
            "Where can video creators generate UTM campaign tags in the partner hub?",
        ),
    ),
    NegativeTemplateFamily(
        template_group_id="neg_evl_b2b_procurement",
        negative_kind="unsupported_platform",
        partition="evaluation",
        patterns=(
            "Does your enterprise sales desk accept net-60 corporate purchase orders?",
            "How can municipal offices register tax-exempt certificates for bulk stationery?",
            "Who drafts annual master service agreements for corporate office procurement?",
        ),
    ),
    NegativeTemplateFamily(
        template_group_id="neg_evl_accessibility_facility",
        negative_kind="unsupported_platform",
        partition="evaluation",
        patterns=(
            "Are wheelchair ramps available at the main street pickup locker plaza?",
            "Do your regional experience showrooms offer quiet shopping hours on Sundays?",
            "Where can deaf visitors request sign-language assistance at flagship events?",
        ),
    ),
)


def generate_grouped_negative_records() -> List[Dict[str, Any]]:
    """Expand negative template families into group-isolated train/calibration/evaluation records."""
    records: List[Dict[str, Any]] = []
    seen_groups: set[str] = set()
    for fam in NEGATIVE_TEMPLATE_FAMILIES:
        if fam.template_group_id in seen_groups:
            raise ValueError(f"Duplicate negative template_group_id: {fam.template_group_id}")
        seen_groups.add(fam.template_group_id)
        for p_idx, text in enumerate(fam.patterns):
            records.append({
                "sample_id": f"{fam.template_group_id}_{p_idx:02d}",
                "instruction": text,
                "negative_kind": fam.negative_kind,
                "template_group_id": fam.template_group_id,
                "partition": fam.partition,
            })
    return records


def export_negative_dataset(
    output_dir: Path,
    *,
    repo_root: Path = REPO_ROOT,
    max_token_f1: float = 0.65,
) -> Dict[str, Any]:
    """Generate, validate, and write the grouped out-of-scope/ambiguous negative dataset."""
    records = generate_grouped_negative_records()
    groups_by_part: Dict[str, set[str]] = {"train": set(), "calibration": set(), "evaluation": set()}
    counts_by_part: Dict[str, int] = {"train": 0, "calibration": 0, "evaluation": 0}
    for rec in records:
        part = rec["partition"]
        groups_by_part[part].add(rec["template_group_id"])
        counts_by_part[part] += 1

    assert groups_by_part["train"].isdisjoint(groups_by_part["calibration"])
    assert groups_by_part["train"].isdisjoint(groups_by_part["evaluation"])
    assert groups_by_part["calibration"].isdisjoint(groups_by_part["evaluation"])

    leakage_report = check_gold_benchmark_leakage(
        records, repo_root=repo_root, max_token_f1=max_token_f1
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = output_dir / "domain_negatives.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    dataset_sha256 = hashlib.sha256(jsonl_path.read_bytes()).hexdigest().lower()
    try:
        rel_dataset_path = str(jsonl_path.relative_to(repo_root)).replace("\\", "/")
    except ValueError:
        rel_dataset_path = str(jsonl_path)

    manifest = {
        "dataset_path": rel_dataset_path,
        "dataset_sha256": dataset_sha256,
        "total_records": len(records),
        "partition_sample_counts": counts_by_part,
        "partition_template_group_counts": {k: len(v) for k, v in groups_by_part.items()},
        "disjoint_template_groups_verified": True,
        "leakage_audit": leakage_report,
    }
    (output_dir / "domain_negatives_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return manifest


if __name__ == "__main__":
    out = REPO_ROOT / "artifacts/evaluation/task_a_20261113/domain_templates"
    result = export_domain_dataset(out)
    print(json.dumps(result, indent=2, ensure_ascii=False))
