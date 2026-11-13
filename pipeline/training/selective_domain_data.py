"""Independent selective-coverage domain & negative dataset builder for Task A.

Authors brand-new positive (supported-12) and negative (off-domain,
underspecified/ambiguous, unsupported-retail) template families completely
disjoint from:
  1. All 9 frozen benchmark suites (`FROZEN_BENCHMARK_PATHS`), and
  2. Prior Task A dev templates (`pipeline/training/domain_templates.py`).

Template families are assigned atomically to `train`, `calibration`, or
`evaluation` BEFORE any variant generation, and a multi-metric semantic &
lexical overlap audit verifies zero duplicate, high-Jaccard, token-F1, or
TF-IDF semantic-family leakage across splits, prior dev data, and benchmarks.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from pipeline.training.domain_templates import (
    FROZEN_BENCHMARK_PATHS,
    REPO_ROOT,
    generate_grouped_domain_records,
    generate_grouped_negative_records,
)

# Re-export canonical 46-label / supported-12 / escalated-34 lists if needed.
SUPPORTED_12_INTENTS: Tuple[str, ...] = (
    "track_order",
    "cancel_order",
    "delivery_time",
    "delivery_issue",
    "shipping_costs",
    "return_policy",
    "return_product",
    "refund_policy",
    "request_refund",
    "refund_status",
    "payment_issue",
    "human_agent",
)


@dataclass(frozen=True)
class SelectivePositiveFamily:
    """Brand-new positive template family assigned atomically to one split."""

    template_group_id: str
    intent: str
    partition: str  # "train" | "calibration" | "evaluation"
    policy_source: str
    patterns: Tuple[str, ...]


@dataclass(frozen=True)
class SelectiveNegativeFamily:
    """Brand-new negative template family assigned atomically to one split."""

    template_group_id: str
    negative_kind: str  # "off_domain_unrelated" | "underspecified_ambiguous" | "unsupported_retail_policy"
    partition: str  # "train" | "calibration" | "evaluation"
    patterns: Tuple[str, ...]


def _normalize_text(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(text).lower()))


def _token_set(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", str(text).lower()))


def _token_f1(a: str, b: str) -> float:
    ta = re.findall(r"[a-z0-9]+", a.lower())
    tb = re.findall(r"[a-z0-9]+", b.lower())
    if not ta or not tb:
        return 0.0
    ca, cb = Counter(ta), Counter(tb)
    overlap = sum((ca & cb).values())
    if overlap == 0:
        return 0.0
    prec = overlap / len(ta)
    rec = overlap / len(tb)
    return 2 * prec * rec / (prec + rec)


def _jaccard(a: str, b: str) -> float:
    sa, sb = _token_set(a), _token_set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


# 72 brand-new positive template families (6 per supported-12 intent):
#   3 train / 1 calibration / 2 evaluation per intent -> 108 train / 36 cal / 72 eval
SELECTIVE_POSITIVE_FAMILIES: Tuple[SelectivePositiveFamily, ...] = (
    # ------------------------------------------------------------------
    # 1. track_order (POL-ORD-001)
    # ------------------------------------------------------------------
    SelectivePositiveFamily(
        template_group_id="sel_trk_waybill_link",
        intent="track_order",
        partition="train",
        policy_source="POL-ORD-001",
        patterns=(
            "Where can I open the courier waybill link emailed after dispatch to follow my parcel?",
            "Can I copy the carrier tracking code from my confirmation email onto the courier portal?",
            "How do I open the external logistics tracking URL attached to my purchase notice?",
        ),
    ),
    SelectivePositiveFamily(
        template_group_id="sel_trk_marked_delivered_check",
        intent="track_order",
        partition="train",
        policy_source="POL-ORD-001",
        patterns=(
            "How do I verify who signed for a delivery marked complete in my account timeline?",
            "Where can I see whether the receptionist or neighbor accepted my completed shipment?",
            "Does the delivery confirmation log show the recipient name or drop-off photo?",
        ),
    ),
    SelectivePositiveFamily(
        template_group_id="sel_trk_split_parcels",
        intent="track_order",
        partition="train",
        policy_source="POL-ORD-001",
        patterns=(
            "Why does my multi-item checkout show two separate tracking numbers for one order?",
            "How can I monitor both packages individually when a seller splits one order into two boxes?",
            "Where do I view tracking progress for the second box of a split shipment?",
        ),
    ),
    SelectivePositiveFamily(
        template_group_id="sel_trk_warehouse_handoff",
        intent="track_order",
        partition="calibration",
        policy_source="POL-ORD-001",
        patterns=(
            "How can I tell if my parcel finished warehouse packing and reached the outbound courier?",
            "What timestamps appear between seller packaging completion and first courier scan?",
            "Where does fulfillment handover time show up inside the shipment activity log?",
        ),
    ),
    SelectivePositiveFamily(
        template_group_id="sel_trk_driver_eta",
        intent="track_order",
        partition="evaluation",
        policy_source="POL-ORD-001",
        patterns=(
            "Can I check the last-mile driver contact number and arrival window on delivery morning?",
            "Where is the assigned rider ETA displayed once my package goes out for final drop-off?",
            "How do I confirm what time the local courier expects to reach my street today?",
        ),
    ),
    SelectivePositiveFamily(
        template_group_id="sel_trk_intercity_transit",
        intent="track_order",
        partition="evaluation",
        policy_source="POL-ORD-001",
        patterns=(
            "How do I track an intercity freight parcel moving between southern and northern depots?",
            "Where are regional transit leg updates shown for long-distance cross-province orders?",
            "Can I follow domestic air or truck linehaul milestones for my current purchase?",
        ),
    ),
    # ------------------------------------------------------------------
    # 2. cancel_order (POL-ORD-002)
    # ------------------------------------------------------------------
    SelectivePositiveFamily(
        template_group_id="sel_can_accidental_spec",
        intent="cancel_order",
        partition="train",
        policy_source="POL-ORD-002",
        patterns=(
            "I accidentally picked the wrong color during checkout; how can I stop the order right now?",
            "Please void my just-submitted purchase because I selected the wrong voltage variant.",
            "Can I abort an order placed five minutes ago before the merchant begins packing?",
        ),
    ),
    SelectivePositiveFamily(
        template_group_id="sel_can_disabled_button",
        intent="cancel_order",
        partition="train",
        policy_source="POL-ORD-002",
        patterns=(
            "Why is the cancellation option grayed out even though the courier has not arrived yet?",
            "What can I do when self-service cancel disappears right after packing starts?",
            "If an order is already loaded onto a delivery van, can I still ask to cancel or refuse it?",
        ),
    ),
    SelectivePositiveFamily(
        template_group_id="sel_can_partial_line",
        intent="cancel_order",
        partition="train",
        policy_source="POL-ORD-002",
        patterns=(
            "Can I cancel just one item out of a three-product checkout without voiding the other two?",
            "How do I drop a duplicate unit from an active unshipped basket?",
            "Is partial line-item cancellation allowed before the seller confirms stock?",
        ),
    ),
    SelectivePositiveFamily(
        template_group_id="sel_can_voucher_restore",
        intent="cancel_order",
        partition="calibration",
        policy_source="POL-ORD-002",
        patterns=(
            "If I cancel an order that used a discount voucher, will the promo code come back?",
            "What happens to applied loyalty coins when a buyer voids an unshipped purchase?",
            "Does cancelling a flash-sale checkout restore my single-use coupon immediately?",
        ),
    ),
    SelectivePositiveFamily(
        template_group_id="sel_can_cod_vs_prepaid",
        intent="cancel_order",
        partition="evaluation",
        policy_source="POL-ORD-002",
        patterns=(
            "Is stopping a cash-on-delivery checkout processed immediately compared with prepaid orders?",
            "How do cancellation approval steps differ between COD orders and card-paid orders?",
            "Do I need seller agreement to cancel an unconfirmed COD purchase?",
        ),
    ),
    SelectivePositiveFamily(
        template_group_id="sel_can_seller_delay_auto",
        intent="cancel_order",
        partition="evaluation",
        policy_source="POL-ORD-002",
        patterns=(
            "At what stage does the platform let me cancel freely if the merchant delays fulfillment?",
            "Can I cancel without penalty when a shop misses its confirmation deadline?",
            "Does an unconfirmed purchase auto-cancel after the seller timeout expires?",
        ),
    ),
    # ------------------------------------------------------------------
    # 3. delivery_time
    # ------------------------------------------------------------------
    SelectivePositiveFamily(
        template_group_id="sel_dtm_express_vs_standard",
        intent="delivery_time",
        partition="train",
        policy_source="Estimated Delivery Timelines",
        patterns=(
            "How fast does TikiNOW 2-hour shipping arrive compared with standard economy delivery?",
            "What is the typical transit duration difference between Express and Standard tiers?",
            "Does upgrading to priority dispatch guarantee same-day afternoon arrival?",
        ),
    ),
    SelectivePositiveFamily(
        template_group_id="sel_dtm_weekend_holiday",
        intent="delivery_time",
        partition="train",
        policy_source="Estimated Delivery Timelines",
        patterns=(
            "Do couriers count Sundays and public holidays toward estimated delivery business days?",
            "If I check out on Friday evening, when does shipping countdown officially begin?",
            "Are warehouse dispatches paused during national holiday periods?",
        ),
    ),
    SelectivePositiveFamily(
        template_group_id="sel_dtm_rural_island",
        intent="delivery_time",
        partition="train",
        policy_source="Estimated Delivery Timelines",
        patterns=(
            "How many extra days do deliveries take to coastal islands or remote mountain districts?",
            "What is the estimated arrival span for rural provinces outside major urban centers?",
            "Do outer suburban wards fall under two-day metro shipping or regional timelines?",
        ),
    ),
    SelectivePositiveFamily(
        template_group_id="sel_dtm_bulky_appliance",
        intent="delivery_time",
        partition="calibration",
        policy_source="Estimated Delivery Timelines",
        patterns=(
            "How long do bulky white-goods deliveries like washing machines take to schedule?",
            "Why do oversized furniture orders have a wider delivery appointment window than small parcels?",
            "What lead time applies to heavy appliances shipped by specialized freight teams?",
        ),
    ),
    SelectivePositiveFamily(
        template_group_id="sel_dtm_crossborder",
        intent="delivery_time",
        partition="evaluation",
        policy_source="Estimated Delivery Timelines",
        patterns=(
            "How many weeks should I allow for an international cross-border warehouse shipment?",
            "What estimated delivery timeframe applies to overseas imported goods clearing customs?",
            "How long do pre-order items shipped from foreign sellers normally take to reach buyers?",
        ),
    ),
    SelectivePositiveFamily(
        template_group_id="sel_dtm_cutoff_hour",
        intent="delivery_time",
        partition="evaluation",
        policy_source="Estimated Delivery Timelines",
        patterns=(
            "Before what afternoon cutoff hour must I pay to receive next-day urban delivery?",
            "Does completing checkout at 10 AM shave a full day off the estimated arrival date?",
            "How does daily warehouse dispatch cutoff affect the promised delivery calendar?",
        ),
    ),
    # ------------------------------------------------------------------
    # 4. delivery_issue
    # ------------------------------------------------------------------
    SelectivePositiveFamily(
        template_group_id="sel_dis_stalled_scan",
        intent="delivery_issue",
        partition="train",
        policy_source="Handling Delayed, Lost, or Discrepant Delivery Statuses",
        patterns=(
            "My parcel has stayed frozen at the regional depot with zero scan activity for five days.",
            "Why has shipment tracking stopped moving since Monday without any delay alert?",
            "What should I report when a package remains stuck in transit far beyond its SLA date?",
        ),
    ),
    SelectivePositiveFamily(
        template_group_id="sel_dis_wrong_drop_proof",
        intent="delivery_issue",
        partition="train",
        policy_source="Handling Delayed, Lost, or Discrepant Delivery Statuses",
        patterns=(
            "The app claims my package arrived, yet the photo proof shows an unfamiliar apartment lobby.",
            "A stranger signed for my parcel according to the courier record, and nobody at home received it.",
            "How do I report a false delivery completion when nothing was handed to me?",
        ),
    ),
    SelectivePositiveFamily(
        template_group_id="sel_dis_phantom_attempt",
        intent="delivery_issue",
        partition="train",
        policy_source="Handling Delayed, Lost, or Discrepant Delivery Statuses",
        patterns=(
            "The courier logged a failed delivery attempt even though I stayed home and never got a call.",
            "Why did the driver mark recipient unreachable without ringing my phone or doorbell?",
            "How can I challenge bogus unsuccessful delivery notes and get proper redelivery?",
        ),
    ),
    SelectivePositiveFamily(
        template_group_id="sel_dis_soaked_tampered",
        intent="delivery_issue",
        partition="calibration",
        policy_source="Handling Delayed, Lost, or Discrepant Delivery Statuses",
        patterns=(
            "The courier handed over a crushed carton with broken security tape and water stains inside.",
            "My package arrived torn open along the seam and looks tampered with during shipping.",
            "What steps apply when outer shipping packaging arrives drenched and damaged?",
        ),
    ),
    SelectivePositiveFamily(
        template_group_id="sel_dis_unexpected_rts",
        intent="delivery_issue",
        partition="evaluation",
        policy_source="Handling Delayed, Lost, or Discrepant Delivery Statuses",
        patterns=(
            "Why did my shipment suddenly reverse to Returning to Sender without any delivery attempt?",
            "My order flipped to return-to-merchant status mid-route; how do I fix this transit error?",
            "Can an incorrectly bounced parcel be intercepted before going back to the seller?",
        ),
    ),
    SelectivePositiveFamily(
        template_group_id="sel_dis_short_or_empty_box",
        intent="delivery_issue",
        partition="evaluation",
        policy_source="Handling Delayed, Lost, or Discrepant Delivery Statuses",
        patterns=(
            "I opened the sealed courier pouch on video and found only one unit instead of three ordered.",
            "My parcel arrived completely empty despite intact outer shipping tape; how do I file a dispute?",
            "Where do I report missing accessories inside a newly delivered shipment box?",
        ),
    ),
    # ------------------------------------------------------------------
    # 5. shipping_costs
    # ------------------------------------------------------------------
    SelectivePositiveFamily(
        template_group_id="sel_shp_freeship_min_spend",
        intent="shipping_costs",
        partition="train",
        policy_source="Shipping Fee Schedule",
        patterns=(
            "What minimum subtotal must my basket reach to unlock a Freeship discount coupon?",
            "Why did my free shipping voucher not waive the entire courier fee at checkout?",
            "Is there a maximum shipping subsidy cap per Freeship promo code?",
        ),
    ),
    SelectivePositiveFamily(
        template_group_id="sel_shp_volumetric_weight",
        intent="shipping_costs",
        partition="train",
        policy_source="Shipping Fee Schedule",
        patterns=(
            "How does dimensional volumetric weight increase the shipping rate for light but bulky boxes?",
            "Why am I charged extra freight surcharge for an item over five kilograms?",
            "Which weight rule determines courier fees for large low-density packages?",
        ),
    ),
    SelectivePositiveFamily(
        template_group_id="sel_shp_multi_seller_fee",
        intent="shipping_costs",
        partition="train",
        policy_source="Shipping Fee Schedule",
        patterns=(
            "Why does checking out items from three different merchants charge three separate delivery fees?",
            "Are shipping charges calculated per fulfillment warehouse when carts mix marketplace sellers?",
            "Can I combine products from two shops under one consolidated courier charge?",
        ),
    ),
    SelectivePositiveFamily(
        template_group_id="sel_shp_tikipro_benefit",
        intent="shipping_costs",
        partition="calibration",
        policy_source="Shipping Fee Schedule",
        patterns=(
            "How much shipping fee discount does a TikiPRO membership cover each month?",
            "Does TikiPRO waive standard delivery fees on eligible warehouse items automatically?",
            "Which shipping surcharges remain excluded from TikiPRO free-delivery perks?",
        ),
    ),
    SelectivePositiveFamily(
        template_group_id="sel_shp_remote_and_return_fee",
        intent="shipping_costs",
        partition="evaluation",
        policy_source="Shipping Fee Schedule",
        patterns=(
            "Do highland or island postal codes pay an extra regional surcharge on standard delivery?",
            "When a doorstep courier collects a valid return parcel, is return pickup free of charge?",
            "Are delivery fees higher for express scheduled delivery slots than regular daytime shipping?",
        ),
    ),
    SelectivePositiveFamily(
        template_group_id="sel_shp_checkout_preview",
        intent="shipping_costs",
        partition="evaluation",
        policy_source="Shipping Fee Schedule",
        patterns=(
            "Does the order summary screen display the final shipping fee prior to billing authorization?",
            "Why did the shipping cost update after I switched my ward and district address?",
            "How is the final delivery fee breakdown calculated on the order review page?",
        ),
    ),
    # ------------------------------------------------------------------
    # 6. return_policy
    # ------------------------------------------------------------------
    SelectivePositiveFamily(
        template_group_id="sel_rpo_window_by_tier",
        intent="return_policy",
        partition="train",
        policy_source="Tiki Standard Product Return Policy",
        patterns=(
            "How many days after delivery do buyers have to initiate a return on Tiki Trading items?",
            "Does the standard return window differ between official mall stores and marketplace sellers?",
            "From which date does the 7-day or 30-day return eligibility clock start counting?",
        ),
    ),
    SelectivePositiveFamily(
        template_group_id="sel_rpo_restricted_categories",
        intent="return_policy",
        partition="train",
        policy_source="Restricted Return Categories",
        patterns=(
            "Which product groups such as perishable groceries, swimwear, or opened cosmetics are non-returnable?",
            "Are digital e-vouchers and software activation keys excluded from change-of-mind returns?",
            "Why can personal hygiene items only be returned if factory seals remain unbroken?",
        ),
    ),
    SelectivePositiveFamily(
        template_group_id="sel_rpo_condition_accessories",
        intent="return_policy",
        partition="train",
        policy_source="Tiki Standard Product Return Policy",
        patterns=(
            "Must all retail boxes, price tags, warranty cards, and free promotional gifts be included in a return?",
            "Will missing user manuals or damaged manufacturer packaging disqualify a return claim?",
            "What physical condition rules apply to apparel and footwear sent back under standard policy?",
        ),
    ),
    SelectivePositiveFamily(
        template_group_id="sel_rpo_defect_vs_preference",
        intent="return_policy",
        partition="calibration",
        policy_source="Tiki Standard Product Return Policy",
        patterns=(
            "How do return eligibility criteria differ between a faulty item and simple change of mind?",
            "Can I send back a non-defective gadget just because I no longer want it?",
            "What reasons qualify for unconditional free returns versus buyer-fault exclusions?",
        ),
    ),
    SelectivePositiveFamily(
        template_group_id="sel_rpo_electronics_activation",
        intent="return_policy",
        partition="evaluation",
        policy_source="Tiki Standard Product Return Policy",
        patterns=(
            "If I already peeled the seal and activated a smartphone warranty, is return still permitted?",
            "What return conditions apply to unopened versus unsealed laptops and audio gear?",
            "Can defective electronics be returned directly to Tiki instead of visiting brand service centers?",
        ),
    ),
    SelectivePositiveFamily(
        template_group_id="sel_rpo_clearance_promo",
        intent="return_policy",
        partition="evaluation",
        policy_source="Restricted Return Categories",
        patterns=(
            "Are flash-deal bundles or clearance outlet purchases covered by standard return terms?",
            "If I return one item from a buy-two-get-one promotion, how does eligibility work?",
            "Do discounted warehouse-sale products carry the same return rights as full-price goods?",
        ),
    ),
    # ------------------------------------------------------------------
    # 7. return_product
    # ------------------------------------------------------------------
    SelectivePositiveFamily(
        template_group_id="sel_rpr_submit_evidence",
        intent="return_product",
        partition="train",
        policy_source="Return and Exchange Request Process",
        patterns=(
            "Where in the app do I upload my unboxing video and file a product return request?",
            "How many clear product photos are required when submitting an online return form?",
            "Walk me through opening a return ticket for a broken item I just unboxed.",
        ),
    ),
    SelectivePositiveFamily(
        template_group_id="sel_rpr_pickup_vs_dropoff",
        intent="return_product",
        partition="train",
        policy_source="Return and Exchange Request Process",
        patterns=(
            "How do I arrange a home courier pickup or drop off my return box at a postal counter?",
            "Can I switch from doorstep return collection to self drop-off at a partner branch?",
            "Where do I choose my preferred handover method during a return request?",
        ),
    ),
    SelectivePositiveFamily(
        template_group_id="sel_rpr_size_exchange",
        intent="return_product",
        partition="train",
        policy_source="Return and Exchange Request Process",
        patterns=(
            "I want to swap a medium jacket I received for a large size; how do I start an exchange?",
            "How do I request a replacement unit instead of a refund for a wrong-color delivery?",
            "Where can I select exchange for another variant on my delivered order?",
        ),
    ),
    SelectivePositiveFamily(
        template_group_id="sel_rpr_qc_inspection",
        intent="return_product",
        partition="calibration",
        policy_source="Return and Exchange Request Process",
        patterns=(
            "How many business days does warehouse quality inspection take after the return parcel arrives?",
            "What happens if the QC center rejects my returned product during condition verification?",
            "Where can I see whether the inspection team approved my returned item?",
        ),
    ),
    SelectivePositiveFamily(
        template_group_id="sel_rpr_label_packing",
        intent="return_product",
        partition="evaluation",
        policy_source="Return and Exchange Request Process",
        patterns=(
            "Do I need to print a return shipping label or write the ticket code on the box before pickup?",
            "How should I seal fragile glass items before handing a return parcel to the courier?",
            "What return reference number must be attached to the outer package for warehouse intake?",
        ),
    ),
    SelectivePositiveFamily(
        template_group_id="sel_rpr_modify_withdraw",
        intent="return_product",
        partition="evaluation",
        policy_source="Return and Exchange Request Process",
        patterns=(
            "How can I withdraw a return submission if I decided to keep the item after all?",
            "Can I reschedule the courier return pickup slot for tomorrow afternoon instead?",
            "How do I edit an incorrect return reason on an already submitted ticket?",
        ),
    ),
    # ------------------------------------------------------------------
    # 8. refund_policy
    # ------------------------------------------------------------------
    SelectivePositiveFamily(
        template_group_id="sel_rfp_coins_and_vouchers",
        intent="refund_policy",
        partition="train",
        policy_source="Safe Refund Reconciliation Rules",
        patterns=(
            "When an order is refunded, are redeemed TikiXU loyalty points credited back separately?",
            "Does refund reconciliation return only net cash paid or also expired promotional discounts?",
            "What is the rule for restoring single-use coupon value after a full order refund?",
        ),
    ),
    SelectivePositiveFamily(
        template_group_id="sel_rfp_original_method_cod",
        intent="refund_policy",
        partition="train",
        policy_source="Safe Refund Reconciliation Rules",
        patterns=(
            "Under reconciliation rules, do card payments always refund to the same original card?",
            "How are cash-on-delivery orders reimbursed since couriers cannot hand back cash?",
            "Can I ask for my refund to go to a different friend's bank account instead of my own?",
        ),
    ),
    SelectivePositiveFamily(
        template_group_id="sel_rfp_shipping_fee_rule",
        intent="refund_policy",
        partition="train",
        policy_source="Safe Refund Reconciliation Rules",
        patterns=(
            "Does the refund policy include original outbound shipping costs when an item is defective?",
            "Under what circumstances is the delivery fee excluded from my reimbursement total?",
            "Are restocking deductions ever applied to approved warranty returns?",
        ),
    ),
    SelectivePositiveFamily(
        template_group_id="sel_rfp_partial_itemized",
        intent="refund_policy",
        partition="calibration",
        policy_source="Safe Refund Reconciliation Rules",
        patterns=(
            "How is a pro-rated refund calculated when I return only one product from a multi-item bundle?",
            "What formula allocates cart-wide voucher discounts across a partial item refund?",
            "Can an order be partially refunded if one unit was missing while other items stayed intact?",
        ),
    ),
    SelectivePositiveFamily(
        template_group_id="sel_rfp_installment_escrow",
        intent="refund_policy",
        partition="evaluation",
        policy_source="Safe Refund Reconciliation Rules",
        patterns=(
            "What policy governs credit-limit release when a 0% installment order gets fully refunded?",
            "Are bank installment conversion fees waived or refunded after transaction cancellation?",
            "How do reconciliation guidelines protect buyers on escrow-held high-value purchases?",
        ),
    ),
    SelectivePositiveFamily(
        template_group_id="sel_rfp_instant_vs_review",
        intent="refund_policy",
        partition="evaluation",
        policy_source="Safe Refund Reconciliation Rules",
        patterns=(
            "Which criteria qualify a return for instant wallet reimbursement before warehouse check?",
            "Why do high-value electronics require full QC clearance before refund release?",
            "Under what rules is an automatic refund triggered immediately upon courier scan?",
        ),
    ),
    # ------------------------------------------------------------------
    # 9. request_refund
    # ------------------------------------------------------------------
    SelectivePositiveFamily(
        template_group_id="sel_req_cancelled_prepaid",
        intent="request_refund",
        partition="train",
        policy_source="Safe Refund Reconciliation Rules",
        patterns=(
            "My prepaid card order was cancelled before shipment; please process my money back now.",
            "I want to claim a full refund for a cancelled bank-transfer purchase that has not returned yet.",
            "Please trigger reimbursement for my cancelled order paid via credit card yesterday.",
        ),
    ),
    SelectivePositiveFamily(
        template_group_id="sel_req_cod_bank_payout",
        intent="request_refund",
        partition="train",
        policy_source="Safe Refund Reconciliation Rules",
        patterns=(
            "Where can I submit my bank account number to request a refund for my returned COD purchase?",
            "I paid cash on delivery and sent the faulty item back; please send my refund payout.",
            "How do I file my bank details to claim reimbursement on a cash-paid order?",
        ),
    ),
    SelectivePositiveFamily(
        template_group_id="sel_req_lost_parcel",
        intent="request_refund",
        partition="train",
        policy_source="Safe Refund Reconciliation Rules",
        patterns=(
            "The courier confirmed my parcel is lost in transit, so I want to request a full refund.",
            "Please reimburse my payment immediately since the undelivered shipment was declared missing.",
            "I do not want a replacement for my lost box; issue my money back instead.",
        ),
    ),
    SelectivePositiveFamily(
        template_group_id="sel_req_qc_approved_payout",
        intent="request_refund",
        partition="calibration",
        policy_source="Refund Receipt Timeline",
        patterns=(
            "Your return center approved my item inspection yesterday; please release my refund payout.",
            "My returned package passed quality verification, so I am requesting the promised reimbursement.",
            "Can you initiate the credit card refund now that warehouse intake marked my return accepted?",
        ),
    ),
    SelectivePositiveFamily(
        template_group_id="sel_req_defective_refund",
        intent="request_refund",
        partition="evaluation",
        policy_source="Tiki Standard Product Return Policy",
        patterns=(
            "The blender arrived dead on arrival; I would like to claim a refund rather than exchange.",
            "Please refund my purchase because the delivered headphones have a cracked left speaker.",
            "I received a broken ceramic mug and want my money back right away.",
        ),
    ),
    SelectivePositiveFamily(
        template_group_id="sel_req_unshipped_timeout",
        intent="request_refund",
        partition="evaluation",
        policy_source="Order Cancellation Rules",
        patterns=(
            "The merchant missed the shipping deadline completely; please refund the amount I prepaid.",
            "I am claiming a refund because the seller never dispatched my paid order on schedule.",
            "Since stock ran out and my order auto-voided, please send back my upfront payment.",
        ),
    ),
    # ------------------------------------------------------------------
    # 10. refund_status
    # ------------------------------------------------------------------
    SelectivePositiveFamily(
        template_group_id="sel_rfs_card_atm_sla",
        intent="refund_status",
        partition="train",
        policy_source="Refund Receipt Timeline by Payment Method",
        patterns=(
            "How many working days do domestic ATM cards versus Visa credit cards take to show a refund?",
            "Why does my credit card statement still lack the refund issued six business days ago?",
            "What is the normal bank settlement SLA for international debit card reimbursements?",
        ),
    ),
    SelectivePositiveFamily(
        template_group_id="sel_rfs_wallet_history",
        intent="refund_status",
        partition="train",
        policy_source="Checking Refund History and Order Status",
        patterns=(
            "Where inside Transaction History can I verify whether my refund moved from pending to sent?",
            "How do I inspect the exact payout timestamp inside my order refund ledger?",
            "Does my Tiki account show a separate status tracker for pending bank transfers?",
        ),
    ),
    SelectivePositiveFamily(
        template_group_id="sel_rfs_ewallet_sync",
        intent="refund_status",
        partition="train",
        policy_source="Refund Receipt Timeline by Payment Method",
        patterns=(
            "My app marks the MoMo refund as completed, yet my e-wallet balance has not increased yet.",
            "How long after app confirmation does a ZaloPay or ShopeePay wallet refund actually appear?",
            "Why is my e-wallet refund showing completed in order details while my wallet app looks empty?",
        ),
    ),
    SelectivePositiveFamily(
        template_group_id="sel_rfs_arn_trace",
        intent="refund_status",
        partition="calibration",
        policy_source="Checking Refund History and Order Status",
        patterns=(
            "Can I get the Acquirer Reference Number ARN to let my card issuer trace a pending refund?",
            "Where do I locate the bank transaction reference ID for an approved reimbursement?",
            "My bank asked for a payout trace code to locate the incoming card reversal; where is it?",
        ),
    ),
    SelectivePositiveFamily(
        template_group_id="sel_rfs_installment_statement",
        intent="refund_status",
        partition="evaluation",
        policy_source="Refund Receipt Timeline by Payment Method",
        patterns=(
            "How can I check if a cancelled 6-month installment refund adjusted my upcoming card bill?",
            "Will an approved installment reimbursement show up in the current or next billing cycle?",
            "Why does my monthly installment plan still look active after a refund was approved?",
        ),
    ),
    SelectivePositiveFamily(
        template_group_id="sel_rfs_overdue_escalation",
        intent="refund_status",
        partition="evaluation",
        policy_source="Refund Receipt Timeline by Payment Method",
        patterns=(
            "Fifteen business days have passed since refund approval and my bank balance still shows nothing.",
            "How do I check on an overdue refund whose expected posting deadline expired yesterday?",
            "My refund transfer has stayed stuck in processing past the quoted SLA; what is the current status?",
        ),
    ),
    # ------------------------------------------------------------------
    # 11. payment_issue
    # ------------------------------------------------------------------
    SelectivePositiveFamily(
        template_group_id="sel_pay_double_charge",
        intent="payment_issue",
        partition="train",
        policy_source="Handling Double Deductions on Credit Cards or E-Wallets",
        patterns=(
            "My Visa card was billed twice within ten seconds for one single checkout cart.",
            "I see two identical MoMo deductions on my bank alert for the same order reference.",
            "Why did your payment gateway charge my debit card twice when I clicked Pay once?",
        ),
    ),
    SelectivePositiveFamily(
        template_group_id="sel_pay_debited_unpaid",
        intent="payment_issue",
        partition="train",
        policy_source="Handling Payment Incidents",
        patterns=(
            "Money left my checking account already, yet the order page still says Awaiting Payment.",
            "My banking app confirmed the transfer succeeded, but checkout timed out without confirming.",
            "Why is my paid transaction stuck in pending payment even though funds were deducted?",
        ),
    ),
    SelectivePositiveFamily(
        template_group_id="sel_pay_3ds_otp_fail",
        intent="payment_issue",
        partition="train",
        policy_source="Handling Payment Incidents",
        patterns=(
            "The 3D Secure verification page keeps rejecting valid OTP codes during card checkout.",
            "Why does my active debit card fail authorization with a gateway error every time I pay?",
            "Every attempt to pay with Mastercard shows an unexpected payment declined popup.",
        ),
    ),
    SelectivePositiveFamily(
        template_group_id="sel_pay_qr_timeout",
        intent="payment_issue",
        partition="calibration",
        policy_source="Handling Payment Incidents",
        patterns=(
            "The VNPay QR code expired mid-transfer and my e-wallet hung on processing.",
            "What happens if the QR session times out right as I approve payment in my banking app?",
            "My QR scan deducted funds after the checkout countdown hit zero; how do I resolve this error?",
        ),
    ),
    SelectivePositiveFamily(
        template_group_id="sel_pay_amount_mismatch",
        intent="payment_issue",
        partition="evaluation",
        policy_source="Handling Payment Incidents",
        patterns=(
            "My card statement reflects a higher charge than the discounted checkout total shown on screen.",
            "Why was an unexpected installment surcharge billed on my card transaction?",
            "The bank receipt amount does not match the promo-applied total in my order summary.",
        ),
    ),
    SelectivePositiveFamily(
        template_group_id="sel_pay_pending_auth_hold",
        intent="payment_issue",
        partition="evaluation",
        policy_source="Handling Payment Incidents",
        patterns=(
            "A pending authorization hold is still locking funds on my debit card after payment failed.",
            "Why has my bank card not released the reserved hold from an aborted checkout attempt?",
            "Checkout crashed at confirmation and left a frozen balance hold on my card.",
        ),
    ),
    # ------------------------------------------------------------------
    # 12. human_agent
    # ------------------------------------------------------------------
    SelectivePositiveFamily(
        template_group_id="sel_hum_live_representative",
        intent="human_agent",
        partition="train",
        policy_source="policy_v2:human_agent",
        patterns=(
            "I want a direct handoff to a trained live advisor rather than self-service articles.",
            "I want to chat with an actual human support advisor instead of reading FAQs.",
            "Transfer my ticket to a real person on your customer service team.",
        ),
    ),
    SelectivePositiveFamily(
        template_group_id="sel_hum_bypass_bot",
        intent="human_agent",
        partition="train",
        policy_source="policy_v2:human_agent",
        patterns=(
            "Skip the automated assistant and hand this conversation over to human staff.",
            "Automated replies are not answering my case; put a live specialist in this chat.",
            "Stop routing me through scripted menus and escalate to a human agent.",
        ),
    ),
    SelectivePositiveFamily(
        template_group_id="sel_hum_supervisor_callback",
        intent="human_agent",
        partition="train",
        policy_source="policy_v2:human_agent",
        patterns=(
            "Have a senior support specialist or team lead reach out to me personally.",
            "I need an escalation supervisor to review my case directly by phone or live chat.",
            "Please assign a manager or human reviewer to take over this conversation.",
        ),
    ),
    SelectivePositiveFamily(
        template_group_id="sel_hum_operator_desk",
        intent="human_agent",
        partition="calibration",
        policy_source="policy_v2:human_agent",
        patterns=(
            "Can you route me to a live support desk operator who can speak with me directly?",
            "I prefer dealing with a live agent on your helpdesk right away.",
            "Connect this session to an available customer support person.",
        ),
    ),
    SelectivePositiveFamily(
        template_group_id="sel_hum_reject_automation",
        intent="human_agent",
        partition="evaluation",
        policy_source="policy_v2:human_agent",
        patterns=(
            "Do not send another bot response; let me speak with a human representative.",
            "I need direct help from a person in customer care rather than automated answers.",
            "Please transfer me immediately to an actual staff member.",
        ),
    ),
    SelectivePositiveFamily(
        template_group_id="sel_hum_manual_staff",
        intent="human_agent",
        partition="evaluation",
        policy_source="policy_v2:human_agent",
        patterns=(
            "Could a real support agent step into this thread and assist me personally?",
            "I am requesting live assistance from a human service advisor.",
            "Put me through to a member of your support staff now.",
        ),
    ),
)


# 32 brand-new negative template families (14 train / 9 calibration / 9 evaluation = 96 records)
SELECTIVE_NEGATIVE_FAMILIES: Tuple[SelectiveNegativeFamily, ...] = (
    # ---- TRAIN NEGATIVES (14 families = 42 records) ----
    SelectiveNegativeFamily(
        template_group_id="sel_neg_trn_cooking",
        negative_kind="off_domain_unrelated",
        partition="train",
        patterns=(
            "What yeast hydration ratio works best for crusty overnight artisan sourdough loaves?",
            "At what internal temperature should braised beef short ribs rest before slicing?",
            "How do I stop homemade hollandaise sauce from splitting on a double boiler?",
        ),
    ),
    SelectiveNegativeFamily(
        template_group_id="sel_neg_trn_automotive",
        negative_kind="off_domain_unrelated",
        partition="train",
        patterns=(
            "Why does my sedan steering wheel vibrate noticeably above ninety kilometers per hour?",
            "How often should synthetic transmission fluid be flushed on a front-wheel-drive hatchback?",
            "What OBD-II trouble code triggers when an upstream oxygen sensor heater fails?",
        ),
    ),
    SelectiveNegativeFamily(
        template_group_id="sel_neg_trn_python_devops",
        negative_kind="off_domain_unrelated",
        partition="train",
        patterns=(
            "Why does asyncio.gather raise CancelledError when one coroutine exits early?",
            "How do I configure multi-stage Docker builds to strip C compiler toolchains from Alpine images?",
            "What PostgreSQL index type speeds up JSONB containment queries over nested arrays?",
        ),
    ),
    SelectiveNegativeFamily(
        template_group_id="sel_neg_trn_horticulture",
        negative_kind="off_domain_unrelated",
        partition="train",
        patterns=(
            "Which soil pH range helps outdoor blueberry bushes absorb iron without leaf chlorosis?",
            "How should I prune dormant apple branches in late winter to encourage fruit spurs?",
            "Why are indoor monstera leaves curling inward even though potting bark stays damp?",
        ),
    ),
    SelectiveNegativeFamily(
        template_group_id="sel_neg_trn_music_theory",
        negative_kind="off_domain_unrelated",
        partition="train",
        patterns=(
            "How does a tritone substitution resolve smoothly into a tonic major seventh chord?",
            "Which fret positions let an acoustic guitarist play a clean F-sharp minor barre chord?",
            "Why do brass players transpose B-flat trumpet sheet music up a major second?",
        ),
    ),
    SelectiveNegativeFamily(
        template_group_id="sel_neg_trn_astronomy",
        negative_kind="off_domain_unrelated",
        partition="train",
        patterns=(
            "What orbital resonance keeps Jupiter's Galilean moons Io and Europa locked in period?",
            "How does a Newtonian reflector telescope collimate its secondary mirror at night?",
            "Why do white dwarf stars explode as Type Ia supernovae near the Chandrasekhar mass?",
        ),
    ),
    SelectiveNegativeFamily(
        template_group_id="sel_neg_trn_vague_help",
        negative_kind="underspecified_ambiguous",
        partition="train",
        patterns=(
            "Hello, I ran into a confusing situation earlier today and need someone to check it.",
            "There seems to be something off on my end, could you inspect what happened?",
            "Can you look at the message I sent earlier because nothing moved forward yet?",
        ),
    ),
    SelectiveNegativeFamily(
        template_group_id="sel_neg_trn_vague_recent",
        negative_kind="underspecified_ambiguous",
        partition="train",
        patterns=(
            "Quick follow-up about yesterday's matter—any update available right now?",
            "I still have not seen any progress on that recent thing we talked about.",
            "Something felt strange during my last visit here and I need guidance on what next.",
        ),
    ),
    SelectiveNegativeFamily(
        template_group_id="sel_neg_trn_vague_unclear",
        negative_kind="underspecified_ambiguous",
        partition="train",
        patterns=(
            "Could you review this record and advise what step makes sense from here?",
            "I clicked through a screen just now and got stuck without seeing any clear explanation.",
            "Everything looked normal until ten minutes ago, now I am unsure what went wrong.",
        ),
    ),
    SelectiveNegativeFamily(
        template_group_id="sel_neg_trn_vague_single_line",
        negative_kind="underspecified_ambiguous",
        partition="train",
        patterns=(
            "Need clarification on my recent activity please.",
            "Hi there, please assist with my unresolved case.",
            "Not sure which department handles this, kindly check.",
        ),
    ),
    SelectiveNegativeFamily(
        template_group_id="sel_neg_trn_wholesale_b2b",
        negative_kind="unsupported_retail_policy",
        partition="train",
        patterns=(
            "Do you quote bulk container pricing for five thousand units shipped to regional wholesalers?",
            "How can an enterprise reseller apply for quarterly distributor rebate contracts?",
            "Where do corporate procurement buyers negotiate custom OEM branding on bulk hardware?",
        ),
    ),
    SelectiveNegativeFamily(
        template_group_id="sel_neg_trn_seller_commission",
        negative_kind="unsupported_retail_policy",
        partition="train",
        patterns=(
            "What marketplace commission percentage applies to third-party merchants selling kitchenware?",
            "How can a new vendor upload wholesale SKU catalogs to the seller onboarding portal?",
            "Where do storefront merchants download monthly payout reconciliation statements for tax filing?",
        ),
    ),
    SelectiveNegativeFamily(
        template_group_id="sel_neg_trn_extended_warranty",
        negative_kind="unsupported_retail_policy",
        partition="train",
        patterns=(
            "Does your store cover accidental liquid spills on a laptop bought three years ago?",
            "How do I register a third-party extended protection plan for screen crack replacement?",
            "Can I mail out-of-warranty camera lenses to your team for paid sensor calibration?",
        ),
    ),
    SelectiveNegativeFamily(
        template_group_id="sel_neg_trn_affiliate_program",
        negative_kind="unsupported_retail_policy",
        partition="train",
        patterns=(
            "What cookie attribution window applies to creator affiliate referral links?",
            "How do social media publishers verify W-8 tax residency forms in the partner dashboard?",
            "When are influencer commission payouts thresholded for monthly wire transfers?",
        ),
    ),
    # ---- CALIBRATION NEGATIVES (9 families = 27 records) ----
    SelectiveNegativeFamily(
        template_group_id="sel_neg_cal_pet_care",
        negative_kind="off_domain_unrelated",
        partition="calibration",
        patterns=(
            "Which daily calorie count suits a neutered indoor tabby cat weighing four kilograms?",
            "How do veterinarians test freshwater aquarium ammonia spikes during nitrogen cycling?",
            "Why do golden retriever puppies shed baby premolars around four months old?",
        ),
    ),
    SelectiveNegativeFamily(
        template_group_id="sel_neg_cal_woodworking",
        negative_kind="off_domain_unrelated",
        partition="calibration",
        patterns=(
            "What chisel bevel angle cuts clean mortise-and-tenon joints in kiln-dried white oak?",
            "How long should tung oil polymerize between coats on a walnut dining tabletop?",
            "Why does hand-planing against wild grain cause tearout without a tight chipbreaker?",
        ),
    ),
    SelectiveNegativeFamily(
        template_group_id="sel_neg_cal_meteorology",
        negative_kind="off_domain_unrelated",
        partition="calibration",
        patterns=(
            "How do barometric pressure drops ahead of a cold front trigger squall-line thunderstorms?",
            "What atmospheric temperature inversion traps winter smog across mountain basins?",
            "Why does the Coriolis deflection curve tropical cyclones counterclockwise north of the equator?",
        ),
    ),
    SelectiveNegativeFamily(
        template_group_id="sel_neg_cal_vague_issue",
        negative_kind="underspecified_ambiguous",
        partition="calibration",
        patterns=(
            "I tried doing it twice today and keep hitting an unexpected wall.",
            "Could someone look at my latest action and tell me why it looks odd?",
            "Nothing matched what I thought would happen when I opened my dashboard.",
        ),
    ),
    SelectiveNegativeFamily(
        template_group_id="sel_neg_cal_vague_pending",
        negative_kind="underspecified_ambiguous",
        partition="calibration",
        patterns=(
            "Still waiting on resolution here—can you tell me what is going on?",
            "Just checking back in because nothing changed since my previous inquiry.",
            "Please take a look at this because I cannot figure out the status.",
        ),
    ),
    SelectiveNegativeFamily(
        template_group_id="sel_neg_cal_vague_ambig_ref",
        negative_kind="underspecified_ambiguous",
        partition="calibration",
        patterns=(
            "I have a quick concern about the record under my profile from last week.",
            "Could you double-check whether everything went through properly on my submission?",
            "Why does this still look incomplete after I followed the prompt?",
        ),
    ),
    SelectiveNegativeFamily(
        template_group_id="sel_neg_cal_loyalty_donation",
        negative_kind="unsupported_retail_policy",
        partition="calibration",
        patterns=(
            "Can I convert unused reward points into frequent-flyer airline miles or charity grants?",
            "Does your platform allow transferring membership tier status between family accounts?",
            "How do I redeem expired corporate gift certificates from five years ago?",
        ),
    ),
    SelectiveNegativeFamily(
        template_group_id="sel_neg_cal_price_match",
        negative_kind="unsupported_retail_policy",
        partition="calibration",
        patterns=(
            "Will you retroactively match a lower price advertised by a competing retailer last week?",
            "If an item drops in price twenty days after I bought it, do you credit the difference?",
            "Where can I submit competitor flyer screenshots for a price-adjustment claim?",
        ),
    ),
    SelectiveNegativeFamily(
        template_group_id="sel_neg_cal_franchise_rental",
        negative_kind="unsupported_retail_policy",
        partition="calibration",
        patterns=(
            "How do local landlords lease wall space for automated parcel-locker kiosks?",
            "Where do logistics startups apply to become contracted last-mile franchise hubs?",
            "Does your company rent photography studio booths to independent catalog sellers?",
        ),
    ),
    # ---- EVALUATION NEGATIVES (9 families = 27 records) ----
    SelectiveNegativeFamily(
        template_group_id="sel_neg_evl_fitness",
        negative_kind="off_domain_unrelated",
        partition="evaluation",
        patterns=(
            "How does progressive overload across weekly mesocycles stimulate skeletal muscle hypertrophy?",
            "What lactate threshold pace helps marathoners pace half-distance tempo runs sustainably?",
            "Why should thoracic spine mobility drills precede heavy overhead barbell presses?",
        ),
    ),
    SelectiveNegativeFamily(
        template_group_id="sel_neg_evl_oceanography",
        negative_kind="off_domain_unrelated",
        partition="evaluation",
        patterns=(
            "How do thermohaline density gradients drive deep-ocean Atlantic meridional overturning circulation?",
            "What bioluminescent luciferin reaction lights up mesopelagic lanternfish below five hundred meters?",
            "Why do El Nino sea-surface warming events suppress nutrient upwelling off Peru?",
        ),
    ),
    SelectiveNegativeFamily(
        template_group_id="sel_neg_evl_chess",
        negative_kind="off_domain_unrelated",
        partition="evaluation",
        patterns=(
            "Why does the Ruy Lopez Berlin Endgame often hinge on queenside pawn majorities?",
            "When does sacrificing an exchange on c3 justify open dark-square diagonals against castling?",
            "How should White handle the Najdorf Sicilian poisoned-pawn variation in blitz games?",
        ),
    ),
    SelectiveNegativeFamily(
        template_group_id="sel_neg_evl_vague_followup",
        negative_kind="underspecified_ambiguous",
        partition="evaluation",
        patterns=(
            "Hello, any news on the problem I flagged earlier this week?",
            "It still is not behaving normally when I check back on my page.",
            "Can someone walk me through why nothing updated on my request?",
        ),
    ),
    SelectiveNegativeFamily(
        template_group_id="sel_neg_evl_vague_uncertain",
        negative_kind="underspecified_ambiguous",
        partition="evaluation",
        patterns=(
            "Something appears mismatched on my account screen and I need assistance.",
            "Could you inspect what happened right after I tapped confirm just now?",
            "I keep getting confused by the message shown on this step—please clarify.",
        ),
    ),
    SelectiveNegativeFamily(
        template_group_id="sel_neg_evl_vague_generic",
        negative_kind="underspecified_ambiguous",
        partition="evaluation",
        patterns=(
            "Hi team, I need a quick sanity check on my latest ticket please.",
            "Unsure whether my earlier action registered properly—kindly verify.",
            "Would appreciate someone taking another look at what I submitted.",
        ),
    ),
    SelectiveNegativeFamily(
        template_group_id="sel_neg_evl_trade_in",
        negative_kind="unsupported_retail_policy",
        partition="evaluation",
        patterns=(
            "How much trade-in credit do you appraise for a scratched four-year-old smartwatch?",
            "Can buyers swap old DSLR camera bodies toward store gift balances at drop-off desks?",
            "What battery-health threshold disqualifies used tablets from buyback valuation?",
        ),
    ),
    SelectiveNegativeFamily(
        template_group_id="sel_neg_evl_custom_engraving",
        negative_kind="unsupported_retail_policy",
        partition="evaluation",
        patterns=(
            "Can your warehouse laser-engrave custom monograms onto stainless flasks before wrapping?",
            "Do you offer bespoke corporate ribbon printing for holiday gift hampers?",
            "How can buyers attach handwritten calligraphy notes inside gift boxes?",
        ),
    ),
    SelectiveNegativeFamily(
        template_group_id="sel_neg_evl_recalls_disposal",
        negative_kind="unsupported_retail_policy",
        partition="evaluation",
        patterns=(
            "Where can consumers drop off swollen lithium batteries for municipal hazardous recycling?",
            "Do you issue official customs export clearance certificates for commercial reshipments?",
            "How do hospitals apply for medical-device VAT exemption registration before ordering?",
        ),
    ),
)


def generate_selective_positive_records() -> List[Dict[str, Any]]:
    """Expand `SELECTIVE_POSITIVE_FAMILIES` into group-isolated records."""
    records: List[Dict[str, Any]] = []
    seen_groups: set[str] = set()
    for fam in SELECTIVE_POSITIVE_FAMILIES:
        if fam.template_group_id in seen_groups:
            raise ValueError(f"Duplicate selective positive group: {fam.template_group_id}")
        if fam.intent not in SUPPORTED_12_INTENTS:
            raise ValueError(f"Unexpected intent {fam.intent} in {fam.template_group_id}")
        if fam.partition not in ("train", "calibration", "evaluation"):
            raise ValueError(f"Invalid partition {fam.partition} in {fam.template_group_id}")
        seen_groups.add(fam.template_group_id)
        for idx, text in enumerate(fam.patterns):
            records.append(
                {
                    "sample_id": f"{fam.template_group_id}_{idx:02d}",
                    "instruction": text,
                    "intent": fam.intent,
                    "is_negative": False,
                    "negative_kind": None,
                    "template_group_id": fam.template_group_id,
                    "partition": fam.partition,
                    "policy_source": fam.policy_source,
                    "source_family_origin": "task_a_selective_20261113",
                }
            )
    return records


def generate_selective_negative_records() -> List[Dict[str, Any]]:
    """Expand `SELECTIVE_NEGATIVE_FAMILIES` into group-isolated records."""
    records: List[Dict[str, Any]] = []
    seen_groups: set[str] = set()
    for fam in SELECTIVE_NEGATIVE_FAMILIES:
        if fam.template_group_id in seen_groups:
            raise ValueError(f"Duplicate selective negative group: {fam.template_group_id}")
        if fam.partition not in ("train", "calibration", "evaluation"):
            raise ValueError(f"Invalid partition {fam.partition} in {fam.template_group_id}")
        seen_groups.add(fam.template_group_id)
        for idx, text in enumerate(fam.patterns):
            records.append(
                {
                    "sample_id": f"{fam.template_group_id}_{idx:02d}",
                    "instruction": text,
                    "intent": "out_of_scope",
                    "is_negative": True,
                    "negative_kind": fam.negative_kind,
                    "template_group_id": fam.template_group_id,
                    "partition": fam.partition,
                    "source_family_origin": "task_a_selective_20261113",
                }
            )
    return records


def _load_frozen_benchmark_texts(repo_root: Path) -> List[Tuple[str, str]]:
    """Return `(benchmark_relpath:case_id, text)` across all 9 frozen benchmarks."""
    items: List[Tuple[str, str]] = []
    for rel in FROZEN_BENCHMARK_PATHS:
        p = repo_root / rel
        if not p.exists():
            continue
        if rel.endswith(".json"):
            payload = json.loads(p.read_text(encoding="utf-8"))
            rows = payload if isinstance(payload, list) else payload.get("cases", [])
            for idx, r in enumerate(rows):
                txt = str(r.get("query") or r.get("text") or r.get("message") or "").strip()
                if txt:
                    items.append((f"{rel}:{r.get('id', idx)}", txt))
        else:
            for idx, line in enumerate(p.read_text(encoding="utf-8").splitlines()):
                if not line.strip():
                    continue
                r = json.loads(line)
                txt = str(r.get("text") or r.get("query") or r.get("message") or "").strip()
                if txt:
                    items.append((f"{rel}:{r.get('id', idx)}", txt))
    return items


def _pairwise_max_overlap(
    left_rows: Sequence[Tuple[str, str]],
    right_rows: Sequence[Tuple[str, str]],
    *,
    word_cos_threshold: float = 0.65,
    token_f1_threshold: float = 0.65,
    jaccard_threshold: float = 0.60,
) -> Dict[str, Any]:
    """Compute lexical (exact, token-F1, Jaccard) and TF-IDF semantic cosine overlap."""
    if not left_rows or not right_rows:
        return {
            "exact_matches": [],
            "max_token_f1": 0.0,
            "max_jaccard": 0.0,
            "max_word_tfidf_cosine": 0.0,
            "max_char_tfidf_cosine": 0.0,
            "flagged_pairs": [],
        }

    right_norm: Dict[str, str] = {_normalize_text(t): rid for rid, t in right_rows}
    exact_matches: List[Dict[str, str]] = []
    for lid, lt in left_rows:
        ln = _normalize_text(lt)
        if ln in right_norm:
            exact_matches.append({"left_id": lid, "right_id": right_norm[ln], "text": lt})

    all_texts = [t for _, t in left_rows] + [t for _, t in right_rows]
    word_vec = TfidfVectorizer(ngram_range=(1, 2), lowercase=True, min_df=1)
    word_mat = word_vec.fit_transform(all_texts)
    word_cos = cosine_similarity(word_mat[: len(left_rows)], word_mat[len(left_rows) :])

    char_vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), lowercase=True, min_df=1)
    char_mat = char_vec.fit_transform(all_texts)
    char_cos = cosine_similarity(char_mat[: len(left_rows)], char_mat[len(left_rows) :])

    max_f1 = 0.0
    max_jac = 0.0
    max_wcos = float(word_cos.max()) if word_cos.size else 0.0
    max_ccos = float(char_cos.max()) if char_cos.size else 0.0
    flagged: List[Dict[str, Any]] = []

    for i, (lid, lt) in enumerate(left_rows):
        for j, (rid, rt) in enumerate(right_rows):
            f1 = _token_f1(lt, rt)
            jac = _jaccard(lt, rt)
            wcos = float(word_cos[i, j])
            ccos = float(char_cos[i, j])
            if f1 > max_f1:
                max_f1 = f1
            if jac > max_jac:
                max_jac = jac
            if (
                f1 >= token_f1_threshold
                or jac >= jaccard_threshold
                or wcos >= word_cos_threshold
            ):
                flagged.append(
                    {
                        "left_id": lid,
                        "right_id": rid,
                        "token_f1": round(f1, 4),
                        "jaccard": round(jac, 4),
                        "word_tfidf_cosine": round(wcos, 4),
                        "char_tfidf_cosine": round(ccos, 4),
                        "left_text": lt,
                        "right_text": rt,
                    }
                )

    flagged.sort(
        key=lambda x: max(x["token_f1"], x["jaccard"], x["word_tfidf_cosine"]),
        reverse=True,
    )
    return {
        "exact_matches": exact_matches,
        "max_token_f1": round(max_f1, 4),
        "max_jaccard": round(max_jac, 4),
        "max_word_tfidf_cosine": round(max_wcos, 4),
        "max_char_tfidf_cosine": round(max_ccos, 4),
        "flagged_count": len(flagged),
        "flagged_pairs": flagged[:25],
    }


def audit_selective_datasets(
    pos_records: Sequence[Dict[str, Any]],
    neg_records: Sequence[Dict[str, Any]],
    *,
    repo_root: Path = REPO_ROOT,
    max_token_f1: float = 0.65,
    max_jaccard: float = 0.60,
    max_word_tfidf_cosine: float = 0.65,
) -> Dict[str, Any]:
    """Run exhaustive split-isolation, prior-dev, and benchmark overlap audits."""
    all_new = list(pos_records) + list(neg_records)
    by_part: Dict[str, List[Tuple[str, str]]] = {"train": [], "calibration": [], "evaluation": []}
    groups_by_part: Dict[str, set[str]] = {"train": set(), "calibration": set(), "evaluation": set()}
    seen_norm_texts: Dict[str, str] = {}
    internal_exact_dups: List[Dict[str, str]] = []

    for rec in all_new:
        part = rec["partition"]
        by_part[part].append((rec["sample_id"], rec["instruction"]))
        groups_by_part[part].add(rec["template_group_id"])
        norm = _normalize_text(rec["instruction"])
        if norm in seen_norm_texts:
            internal_exact_dups.append(
                {"first_id": seen_norm_texts[norm], "dup_id": rec["sample_id"], "text": rec["instruction"]}
            )
        else:
            seen_norm_texts[norm] = rec["sample_id"]

    prior_pos = generate_grouped_domain_records()
    prior_neg = generate_grouped_negative_records()
    prior_groups = {r["template_group_id"] for r in prior_pos + prior_neg}
    new_groups = set().union(*groups_by_part.values())

    group_disjoint_splits = (
        groups_by_part["train"].isdisjoint(groups_by_part["calibration"])
        and groups_by_part["train"].isdisjoint(groups_by_part["evaluation"])
        and groups_by_part["calibration"].isdisjoint(groups_by_part["evaluation"])
    )
    group_disjoint_prior = new_groups.isdisjoint(prior_groups)

    prior_rows = [(r["sample_id"], r["instruction"]) for r in prior_pos + prior_neg]
    bench_rows = _load_frozen_benchmark_texts(repo_root)
    all_new_rows = [(r["sample_id"], r["instruction"]) for r in all_new]

    checks = {
        "train_vs_calibration": _pairwise_max_overlap(
            by_part["train"],
            by_part["calibration"],
            word_cos_threshold=max_word_tfidf_cosine,
            token_f1_threshold=max_token_f1,
            jaccard_threshold=max_jaccard,
        ),
        "train_vs_evaluation": _pairwise_max_overlap(
            by_part["train"],
            by_part["evaluation"],
            word_cos_threshold=max_word_tfidf_cosine,
            token_f1_threshold=max_token_f1,
            jaccard_threshold=max_jaccard,
        ),
        "calibration_vs_evaluation": _pairwise_max_overlap(
            by_part["calibration"],
            by_part["evaluation"],
            word_cos_threshold=max_word_tfidf_cosine,
            token_f1_threshold=max_token_f1,
            jaccard_threshold=max_jaccard,
        ),
        "new_vs_prior_dev_templates": _pairwise_max_overlap(
            all_new_rows,
            prior_rows,
            word_cos_threshold=max_word_tfidf_cosine,
            token_f1_threshold=max_token_f1,
            jaccard_threshold=max_jaccard,
        ),
        "new_vs_frozen_benchmarks_9": _pairwise_max_overlap(
            all_new_rows,
            bench_rows,
            word_cos_threshold=max_word_tfidf_cosine,
            token_f1_threshold=max_token_f1,
            jaccard_threshold=max_jaccard,
        ),
    }

    failures: List[str] = []
    if not group_disjoint_splits:
        failures.append("template_group_overlap_across_splits")
    if not group_disjoint_prior:
        failures.append("template_group_overlap_with_prior_dev")
    if internal_exact_dups:
        failures.append("internal_exact_duplicates")
    for cname, res in checks.items():
        if res["exact_matches"]:
            failures.append(f"{cname}:exact_match")
        if res["flagged_count"] > 0:
            failures.append(f"{cname}:flagged_similarity({res['flagged_count']})")

    return {
        "passed": len(failures) == 0,
        "failure_reasons": failures,
        "group_disjoint_across_splits": group_disjoint_splits,
        "group_disjoint_with_prior_dev": group_disjoint_prior,
        "internal_exact_duplicates": internal_exact_dups,
        "thresholds": {
            "max_token_f1": max_token_f1,
            "max_jaccard": max_jaccard,
            "max_word_tfidf_cosine": max_word_tfidf_cosine,
        },
        "pairwise_audits": checks,
    }


def export_selective_datasets(
    output_dir: Path,
    *,
    repo_root: Path = REPO_ROOT,
    fail_on_audit: bool = True,
) -> Dict[str, Any]:
    """Generate, audit, and write selective train/calibration/evaluation datasets."""
    pos = generate_selective_positive_records()
    neg = generate_selective_negative_records()
    audit = audit_selective_datasets(pos, neg, repo_root=repo_root)
    if fail_on_audit and not audit["passed"]:
        raise ValueError(
            "Selective dataset overlap audit failed:\n"
            + json.dumps(audit, indent=2, ensure_ascii=False)
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    file_hashes: Dict[str, Dict[str, Any]] = {}

    def _write_jsonl(filename: str, rows: Sequence[Dict[str, Any]]) -> None:
        p = output_dir / filename
        with p.open("w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        try:
            rel = str(p.relative_to(repo_root)).replace("\\", "/")
        except ValueError:
            rel = str(p)
        file_hashes[filename] = {
            "path": rel,
            "count": len(rows),
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest().lower(),
        }

    for part in ("train", "calibration", "evaluation"):
        p_rows = [r for r in pos if r["partition"] == part]
        n_rows = [r for r in neg if r["partition"] == part]
        _write_jsonl(f"positive_{part}.jsonl", p_rows)
        _write_jsonl(f"negative_{part}.jsonl", n_rows)
        _write_jsonl(f"combined_{part}.jsonl", p_rows + n_rows)

    _write_jsonl("selective_positives_all.jsonl", pos)
    _write_jsonl("selective_negatives_all.jsonl", neg)

    manifest = {
        "schema_version": "selective_datasets.v1",
        "origin": "task_a_selective_20261113",
        "positive_counts": {
            part: sum(1 for r in pos if r["partition"] == part)
            for part in ("train", "calibration", "evaluation")
        },
        "negative_counts": {
            part: sum(1 for r in neg if r["partition"] == part)
            for part in ("train", "calibration", "evaluation")
        },
        "positive_template_family_count": len(SELECTIVE_POSITIVE_FAMILIES),
        "negative_template_family_count": len(SELECTIVE_NEGATIVE_FAMILIES),
        "files": file_hashes,
        "isolation_and_semantic_audit": audit,
    }
    (output_dir / "selective_dataset_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return manifest


if __name__ == "__main__":
    out_dir = REPO_ROOT / "artifacts/evaluation/task_a_selective_20261113/datasets"
    result = export_selective_datasets(out_dir, fail_on_audit=True)
    print(json.dumps(result, indent=2, ensure_ascii=False))
