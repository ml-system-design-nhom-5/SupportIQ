"""Brand-new disjoint closure dataset for Task A selective-intent training, calibration & holdout.

Addresses the specific safety gap observed in `task_a_selective_20261113`:
1. Compound multi-intent queries combining 2+ distinct customer intents inside one message
   (`compound_multi_intent`), which previously slipped inside the `[CLS]` positive manifold.
2. Unsupported retail / merchant / catalog inquiries outside KB-backed SUPPORTED_11 rules
   (`unsupported_product_or_merchant`).
3. Fresh underspecified/ambiguous stubs (`underspecified_ambiguous`) and unrelated
   off-domain queries (`off_domain_unrelated`).
4. Fresh positive domain families across ALL 12 SUPPORTED_12 intents AND 10 key retail
   ESCALATED_34 intents (including `product_information`, `availability`, `exchange_product`,
   `damaged_delivery`, `missing_item`, `wrong_item`, `request_invoice`, `payment_methods`,
   `change_order`) so modern marketplace style never biases predictions away from ESCALATED_34.

Every template family is strictly disjoint across `train`, `calibration`, and `evaluation`
and audited against all 9 frozen benchmarks AND both prior Task A datasets (`domain_templates.py`
and `selective_domain_data.py`).
"""

from __future__ import annotations

import datetime
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

from pipeline.preparation.utils import CORE_PRODUCT_INTENTS, compute_sha256
from pipeline.training.domain_templates import (
    generate_grouped_domain_records,
    generate_grouped_negative_records,
)
from pipeline.training.selective_domain_data import (
    _load_frozen_benchmark_texts,
    _normalize_text,
    _pairwise_max_overlap,
    generate_selective_negative_records,
    generate_selective_positive_records,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class ClosurePositiveFamily:
    template_group_id: str
    intent: str
    partition: str  # "train" | "calibration" | "evaluation"
    policy_source: str
    patterns: Tuple[str, ...]


@dataclass(frozen=True)
class ClosureNegativeFamily:
    template_group_id: str
    category: str  # compound_multi_intent | unsupported_product_or_merchant | underspecified_ambiguous | off_domain_unrelated
    partition: str  # "train" | "calibration" | "evaluation"
    patterns: Tuple[str, ...]


# ==============================================================================
# POSITIVE FAMILIES: 72 SUPPORTED_12 (6/intent) + 30 ESCALATED_34 (3/intent)
# ==============================================================================
CLOSURE_POSITIVE_FAMILIES: Tuple[ClosurePositiveFamily, ...] = (
    # ------------------------------------------------------------------
    # 1. track_order
    # ------------------------------------------------------------------
    ClosurePositiveFamily(
        template_group_id="cls_trk_live_gps",
        intent="track_order",
        partition="train",
        policy_source="POL-ORD-001",
        patterns=(
            "Can I follow the live courier route for order TK-4821 on a map right now?",
            "How do I view the current hub scan timestamp for my active shipment?",
            "Where can buyers inspect real-time parcel movement once a rider departs the depot?",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_trk_partner_portal",
        intent="track_order",
        partition="train",
        policy_source="POL-ORD-001",
        patterns=(
            "Is there a way to copy my air waybill number into the logistics partner website?",
            "Where do I locate the courier tracking link for an express parcel dispatched this morning?",
            "How can I check whether TikiNOW handed my package to the neighborhood driver?",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_trk_no_scan",
        intent="track_order",
        partition="train",
        policy_source="POL-ORD-001",
        patterns=(
            "My parcel barcode still shows label created without movement—where do I check the latest update?",
            "How frequently do sorting center checkpoints refresh in the shipment timeline?",
            "Can I see which regional transit warehouse currently holds my box?",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_trk_sms_alerts",
        intent="track_order",
        partition="calibration",
        policy_source="POL-ORD-001",
        patterns=(
            "Will push alerts notify me the moment my parcel reaches out-for-delivery status?",
            "How can I verify whether a courier already attempted delivery to my apartment lobby?",
            "Where inside the order timeline are rider check-in timestamps recorded?",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_trk_multi_box",
        intent="track_order",
        partition="evaluation",
        policy_source="POL-ORD-001",
        patterns=(
            "If two sellers fulfilled my checkout separately, how do I follow each parcel independently?",
            "Where are split-shipment courier codes displayed inside a multi-item purchase?",
            "How do I check the transit milestone of the second box in my order?",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_trk_customs_step",
        intent="track_order",
        partition="evaluation",
        policy_source="POL-ORD-001",
        patterns=(
            "For an overseas mall purchase, how do I track when customs clearance completes?",
            "Where can I inspect the arrival scan after an imported item lands in Vietnam?",
            "Does cross-border shipment tracking distinguish foreign dispatch from domestic sorting?",
        ),
    ),
    # ------------------------------------------------------------------
    # 2. cancel_order
    # ------------------------------------------------------------------
    ClosurePositiveFamily(
        template_group_id="cls_can_before_pack",
        intent="cancel_order",
        partition="train",
        policy_source="POL-ORD-002",
        patterns=(
            "I accidentally picked the wrong color—how do I abort this purchase before warehouse packing?",
            "Please help me stop order TK-3190 while it is still sitting in awaiting confirmation.",
            "Can a buyer void an unshipped transaction right after checkout?",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_can_cutoff_rule",
        intent="cancel_order",
        partition="train",
        policy_source="POL-ORD-002",
        patterns=(
            "Once the courier scans my parcel, why does self-service order cancellation vanish?",
            "At what exact fulfillment milestone does the app lock the cancel button?",
            "Can I refuse delivery at the door instead if the seller already shipped my cancellation request?",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_can_one_sku",
        intent="cancel_order",
        partition="train",
        policy_source="POL-ORD-002",
        patterns=(
            "If I bought three items together, must I cancel the entire basket or just one SKU?",
            "How can I remove one unconfirmed product from a multi-seller order without redoing checkout?",
            "When cancelling a voucher-applied basket, does self-cancel require cancelling every piece?",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_can_reason_menu",
        intent="cancel_order",
        partition="calibration",
        policy_source="POL-ORD-002",
        patterns=(
            "Why does the cancellation screen ask me to pick a reason before submitting?",
            "Which button cancels a pending COD checkout inside purchase history?",
            "Does self-cancelling an unpacked order apply immediately without waiting for seller approval?",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_can_auto_timeout",
        intent="cancel_order",
        partition="evaluation",
        policy_source="POL-ORD-002",
        patterns=(
            "How many days of seller inaction pass before an unshipped purchase auto-cancels?",
            "Will the marketplace automatically void my order if a merchant misses the dispatch deadline?",
            "What happens to an unpaid bank-transfer order when the payment countdown runs out?",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_can_bundle_promo",
        intent="cancel_order",
        partition="evaluation",
        policy_source="POL-ORD-002",
        patterns=(
            "I forgot to apply my promo code—can I cancel the order immediately and reorder cleanly?",
            "Help me terminate this freshly placed purchase before fulfillment starts.",
            "How quickly can I void an order placed five minutes ago because the shipping address is old?",
        ),
    ),
    # ------------------------------------------------------------------
    # 3. delivery_time
    # ------------------------------------------------------------------
    ClosurePositiveFamily(
        template_group_id="cls_dtm_city_tiers",
        intent="delivery_time",
        partition="train",
        policy_source="POL-SHP-001",
        patterns=(
            "How many business days does regular courier shipping usually require to reach Da Nang or Can Tho?",
            "Do inner-district Ho Chi Minh City deliveries arrive sooner than suburban districts?",
            "What is the typical transit duration between Hanoi hubs and northern provincial towns?",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_dtm_tikinow_window",
        intent="delivery_time",
        partition="train",
        policy_source="POL-SHP-001",
        patterns=(
            "If I select two-hour TikiNOW at 10 AM, will it reach my office before lunch?",
            "What is the daily order cutoff for same-afternoon express delivery in major metros?",
            "Does TikiNOW operate on Sundays or cut off late in the evening?",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_dtm_bulky_appliance",
        intent="delivery_time",
        partition="train",
        policy_source="POL-SHP-001",
        patterns=(
            "How much extra lead time do large refrigerators or furniture items add to normal transit estimates?",
            "When ordering heavy household appliances, how long does scheduled freight delivery take?",
            "Why does a washing machine show a five-day delivery range instead of standard parcel speed?",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_dtm_pre_order_eta",
        intent="delivery_time",
        partition="calibration",
        policy_source="POL-SHP-001",
        patterns=(
            "For imported mall electronics, how many days should I budget from purchase to doorstep?",
            "Do national holidays or mega-sale peaks extend the estimated arrival window?",
            "When does the estimated delivery range shown at checkout start counting?",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_dtm_saturday_ops",
        intent="delivery_time",
        partition="evaluation",
        policy_source="POL-SHP-001",
        patterns=(
            "Do domestic parcel couriers drop off regular shipments on Saturday afternoons?",
            "If I choose scheduled evening delivery, which exact arrival hours are available?",
            "Will a Friday night checkout ship out over the weekend or wait until Monday morning?",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_dtm_island_route",
        intent="delivery_time",
        partition="evaluation",
        policy_source="POL-SHP-001",
        patterns=(
            "How many extra days are typically required for standard delivery to island districts like Phu Quoc?",
            "Why does my mountain-commune address show a wider arrival window at checkout?",
            "What arrival timeframe applies when a parcel travels from southern depots to remote provinces?",
        ),
    ),
    # ------------------------------------------------------------------
    # 4. delivery_issue
    # ------------------------------------------------------------------
    ClosurePositiveFamily(
        template_group_id="cls_dis_fake_attempt",
        intent="delivery_issue",
        partition="train",
        policy_source="POL-SHP-003",
        patterns=(
            "The app claims the driver could not reach me, yet nobody called or rang my doorbell.",
            "Why was my parcel marked recipient unavailable while I waited home all afternoon?",
            "A rider logged a failed delivery attempt without ever contacting my phone number.",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_dis_marked_delivered",
        intent="delivery_issue",
        partition="train",
        policy_source="POL-SHP-003",
        patterns=(
            "My order status switched to delivered this morning, yet nothing arrived at reception or my porch.",
            "Courier marked my shipment completed three hours ago and I have not received any parcel.",
            "How do I report a package shown as signed for that never reached my hands?",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_dis_stuck_depot",
        intent="delivery_issue",
        partition="train",
        policy_source="POL-SHP-003",
        patterns=(
            "My shipment has remained frozen at the local transit station for six straight days without movement.",
            "Why is my package overdue past its promised arrival date with zero hub scans since Tuesday?",
            "What steps should I take when a parcel appears lost inside the courier sorting facility?",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_dis_wet_box",
        intent="delivery_issue",
        partition="calibration",
        policy_source="POL-SHP-003",
        patterns=(
            "The outer carton arrived soaked and crushed during courier transit—how do I file a delivery complaint?",
            "Can I report rough carrier handling that tore open my parcel before handover?",
            "What evidence helps investigate a shipment delayed well past its delivery commitment?",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_dis_wrong_drop",
        intent="delivery_issue",
        partition="evaluation",
        policy_source="POL-SHP-003",
        patterns=(
            "The courier dropped my parcel at the wrong building block across the street.",
            "My package was handed to an unknown neighbor without calling me to confirm.",
            "How do I flag a misdelivered shipment so logistics retrieves it immediately?",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_dis_redelivery_fail",
        intent="delivery_issue",
        partition="evaluation",
        policy_source="POL-SHP-003",
        patterns=(
            "After three failed courier runs, my parcel is being sent back to sender without notice.",
            "The driver refuses to call before arriving and keeps delaying my delivery day after day.",
            "Why did my package enter return-to-origin status when the rider never telephoned me?",
        ),
    ),
    # ------------------------------------------------------------------
    # 5. shipping_costs
    # ------------------------------------------------------------------
    ClosurePositiveFamily(
        template_group_id="cls_shp_freeship_cap",
        intent="shipping_costs",
        partition="train",
        policy_source="POL-SHP-002",
        patterns=(
            "What minimum cart total unlocks a Freeship+ shipping fee reduction on eligible goods?",
            "Why did my shipping voucher cover only part of the courier charge instead of the whole amount?",
            "Is there a maximum dong cap per order on marketplace free-shipping coupons?",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_shp_heavy_tier",
        intent="shipping_costs",
        partition="train",
        policy_source="POL-SHP-002",
        patterns=(
            "How do weight brackets and box dimensions increase the freight fee at checkout?",
            "Why did adding a dense kettlebell double my delivery surcharge?",
            "Are oversized home appliances billed a special volumetric shipping rate?",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_shp_multi_vendor",
        intent="shipping_costs",
        partition="train",
        policy_source="POL-SHP-002",
        patterns=(
            "Why does buying from two separate marketplace shops generate two distinct delivery fees?",
            "Are Tiki Trading items bundled under one combined shipping charge per checkout?",
            "Do different warehouses calculate independent courier fees inside the same basket?",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_shp_return_courier",
        intent="shipping_costs",
        partition="calibration",
        policy_source="POL-SHP-002",
        patterns=(
            "Who pays the postage when returning a broken item versus returning one for buyer preference?",
            "Is doorstep return pickup free if the seller shipped an incorrect item?",
            "When will shipping vouchers fail to offset two-hour express delivery surcharges?",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_shp_tikicard_perk",
        intent="shipping_costs",
        partition="evaluation",
        policy_source="POL-SHP-002",
        patterns=(
            "How many monthly shipping waivers come bundled with an active TikiNOW subscription?",
            "Can I stack a seller free-shipping promo together with a platform shipping coupon?",
            "Does rural zone distance add extra dong per kilometer to the base courier fee?",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_shp_cod_surcharge",
        intent="shipping_costs",
        partition="evaluation",
        policy_source="POL-SHP-002",
        patterns=(
            "Is there any extra cash-on-delivery collection surcharge added on top of postage?",
            "Why is standard shipping cheaper than scheduling a fixed two-hour delivery window?",
            "How can buyers preview exact delivery charges before tapping confirm order?",
        ),
    ),
    # ------------------------------------------------------------------
    # 6. return_policy
    # ------------------------------------------------------------------
    ClosurePositiveFamily(
        template_group_id="cls_rpo_window_tier",
        intent="return_policy",
        partition="train",
        policy_source="POL-RET-001",
        patterns=(
            "Under current policy, how many days are allowed for returning Tiki Trading versus third-party items?",
            "Does the 30-day change-of-mind policy cover official mall electronics after delivery?",
            "When does the marketplace return eligibility timer begin—on dispatch or doorstep receipt?",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_rpo_nonreturn_list",
        intent="return_policy",
        partition="train",
        policy_source="POL-RET-001",
        patterns=(
            "Which everyday categories such as fresh produce, undergarments, or digital top-ups are ineligible for returns?",
            "Are unsealed perfumes and skincare bottles barred from non-defect returns?",
            "Why do software download keys not qualify under the standard product return rule?",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_rpo_packaging_rule",
        intent="return_policy",
        partition="train",
        policy_source="POL-RET-001",
        patterns=(
            "What packaging items—such as hangtags, warranty leaflets, and bonus gifts—must stay intact for returns?",
            "Can a torn retail carton invalidate an otherwise valid return claim?",
            "Does sending back an outfit without original labels violate return policy rules?",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_rpo_defect_vs_mind",
        intent="return_policy",
        partition="calibration",
        policy_source="POL-RET-001",
        patterns=(
            "What separates a defective-item return from a voluntary unwanted-item return?",
            "Are marketplace buyers permitted to return non-faulty accessories simply because they dislike the fit?",
            "Which qualifying return grounds give guaranteed approval regardless of category?",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_rpo_seal_opened",
        intent="return_policy",
        partition="evaluation",
        policy_source="POL-RET-001",
        patterns=(
            "If an authorized tablet seal was peeled and registered, does it still qualify for return?",
            "How do return rules treat open-box laptops that turn out defective on first boot?",
            "Are sealed earbuds eligible for buyer-remorse return as long as the shrink-wrap stays unbroken?",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_rpo_flash_bundle",
        intent="return_policy",
        partition="evaluation",
        policy_source="POL-RET-001",
        patterns=(
            "Do flash-sale bundles allow returning just one single piece or require sending back the whole set?",
            "Are heavily discounted clearance items subject to shorter return deadlines?",
            "Under combo-deal policy rules, must any free bonus item accompany a returned main product?",
        ),
    ),
    # ------------------------------------------------------------------
    # 7. return_product
    # ------------------------------------------------------------------
    ClosurePositiveFamily(
        template_group_id="cls_rpr_submit_flow",
        intent="return_product",
        partition="train",
        policy_source="POL-RET-002",
        patterns=(
            "Walk me through submitting a return request in Purchase History after my item arrived.",
            "Which menu option lets me start sending back a product I bought three days ago?",
            "Where do I upload unboxing pictures when registering a parcel return?",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_rpr_video_evidence",
        intent="return_product",
        partition="train",
        policy_source="POL-RET-002",
        patterns=(
            "What photo and unboxing-video proof should I attach before confirming a product return form?",
            "How should I pack accessories and bubble-wrap a fragile item for return collection?",
            "Do I have to print an adhesive barcode tag, or is scribbling the claim reference on cardboard sufficient?",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_rpr_pickup_dropoff",
        intent="return_product",
        partition="train",
        policy_source="POL-RET-002",
        patterns=(
            "How do I book a doorstep courier pickup once my return claim gets approved?",
            "Is handing a return parcel over at a local convenience-store locker supported if I work late?",
            "How many days do I have to hand over the return parcel after approval arrives?",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_rpr_qc_inspection",
        intent="return_product",
        partition="calibration",
        policy_source="POL-RET-002",
        patterns=(
            "What happens during Tiki warehouse quality inspection after the return box lands back there?",
            "How long does return verification usually take once the courier scans my drop-off?",
            "Why might warehouse quality control reject a returned package on arrival?",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_rpr_reschedule_courier",
        intent="return_product",
        partition="evaluation",
        policy_source="POL-RET-002",
        patterns=(
            "The return pickup rider never showed up today—how do I arrange a new collection slot?",
            "Can I modify the pickup address on an already-approved return ticket?",
            "Where can I view the return parcel tracking code while it travels back to the warehouse?",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_rpr_partial_qty",
        intent="return_product",
        partition="evaluation",
        policy_source="POL-RET-002",
        patterns=(
            "I ordered four shirts and only one fits poorly—how do I send back just that one piece?",
            "How do I start a return on a single faulty SKU inside a multi-item shipment?",
            "Let me initiate a partial item return while keeping the rest of the delivered goods.",
        ),
    ),
    # ------------------------------------------------------------------
    # 8. refund_policy
    # ------------------------------------------------------------------
    ClosurePositiveFamily(
        template_group_id="cls_rfp_timeline_method",
        intent="refund_policy",
        partition="train",
        policy_source="POL-PAY-001",
        patterns=(
            "What are the official reimbursement lead times for ATM cards versus credit cards versus e-wallets?",
            "Why do domestic debit refunds take longer to settle than TikiXU wallet credits?",
            "Under refund policy, how many working days after approval does Visa reversal take?",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_rfp_cod_payout",
        intent="refund_policy",
        partition="train",
        policy_source="POL-PAY-001",
        patterns=(
            "When a buyer paid cash on delivery, how does the marketplace reimburse the purchase amount?",
            "Does refund policy let COD orders be credited to a linked bank account or Astra/TikiXU?",
            "Are there transfer charges deducted when refunding a COD payment via domestic bank wire?",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_rfp_voucher_split",
        intent="refund_policy",
        partition="train",
        policy_source="POL-PAY-001",
        patterns=(
            "When I paid with a promo voucher plus TikiXU coins, how is a partial refund prorated?",
            "Do expired single-use discount coupons get restored after a seller cancels my order?",
            "Under policy rules, are shipping fees refunded alongside item cost when the fault is seller-side?",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_rfp_card_statement",
        intent="refund_policy",
        partition="calibration",
        policy_source="POL-PAY-001",
        patterns=(
            "After a credit-card reversal posts, can it appear on next month's billing cycle instead of today?",
            "Are zero-percent installment charges fully reversed under marketplace refund policy?",
            "Does Tiki refund directly back to the original funding source by default?",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_rfp_reject_deduction",
        intent="refund_policy",
        partition="evaluation",
        policy_source="POL-PAY-001",
        patterns=(
            "Can the marketplace withhold part of a refund if a returned product comes back with missing parts?",
            "When is a buyer ineligible for cash payout and offered store credit instead?",
            "What refund rules apply to orders canceled during mega-sale flash events?",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_rfp_wallet_vs_bank",
        intent="refund_policy",
        partition="evaluation",
        policy_source="POL-PAY-001",
        patterns=(
            "Do MoMo and ZaloPay wallet reversals process within minutes or several banking days?",
            "What is the official difference between instant platform wallet credit and bank settlement rules?",
            "Can a refunded buyer insist on cash payout when payment was originally completed by e-wallet?",
        ),
    ),
    # ------------------------------------------------------------------
    # 9. request_refund
    # ------------------------------------------------------------------
    ClosurePositiveFamily(
        template_group_id="cls_rqr_submit_claim",
        intent="request_refund",
        partition="train",
        policy_source="POL-PAY-002",
        patterns=(
            "My prepaid package got auto-canceled—how do I submit a formal money-back request now?",
            "I never got the item I paid for by QR transfer; please open a reimbursement claim for me.",
            "Where can a customer file a refund request when an order was aborted prior to delivery?",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_rqr_bank_details",
        intent="request_refund",
        partition="train",
        policy_source="POL-PAY-002",
        patterns=(
            "Which account holder name and IBAN/bank fields must I fill out to claim a COD refund?",
            "Can I request my reimbursement be paid out as instant TikiXU points instead of waiting for a wire?",
            "How do I update my receiving bank account before confirming a refund claim?",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_rqr_duplicate_charge",
        intent="request_refund",
        partition="train",
        policy_source="POL-PAY-002",
        patterns=(
            "Please help me claim a refund for the extra duplicate charge that hit my debit card.",
            "I paid twice during an app timeout and want one of those payments reimbursed right away.",
            "How do I formally claim back a double charge from my checkout attempt?",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_rqr_voucher_item",
        intent="request_refund",
        partition="calibration",
        policy_source="POL-PAY-002",
        patterns=(
            "I want a full refund of the purchase amount rather than a replacement unit.",
            "Where do I press Request Refund after the merchant ran out of stock?",
            "How should I submit a refund application for an undelivered prepaid parcel?",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_rqr_partial_missing",
        intent="request_refund",
        partition="evaluation",
        policy_source="POL-PAY-002",
        patterns=(
            "One out of three paid goods did not ship—how do I claim a partial refund for that piece?",
            "Help me initiate a partial money-back claim since one item in my bundle was omitted.",
            "Can I request reimbursement for just the unshipped SKU while keeping the delivered items?",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_rqr_post_qc",
        intent="request_refund",
        partition="evaluation",
        policy_source="POL-PAY-002",
        patterns=(
            "Warehouse inspection approved my return yesterday—do I need to click anything else to claim payout?",
            "I would like to trigger my cash reimbursement now that the cancelled order is closed.",
            "Please process a refund to my original card for this aborted shipment.",
        ),
    ),
    # ------------------------------------------------------------------
    # 10. refund_status
    # ------------------------------------------------------------------
    ClosurePositiveFamily(
        template_group_id="cls_rfs_progress_bar",
        intent="refund_status",
        partition="train",
        policy_source="POL-PAY-003",
        patterns=(
            "Where can I inspect what stage my pending refund request is currently sitting in?",
            "My reimbursement ticket has stayed on processing for four days—how do I view its progress?",
            "Is there a status tracker inside my account showing whether the bank payout was sent?",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_rfs_arn_code",
        intent="refund_status",
        partition="train",
        policy_source="POL-PAY-003",
        patterns=(
            "Tiki marked my refund completed three days ago, yet nothing landed in my card statement.",
            "How do I obtain the bank ARN or transaction reference number to trace my missing refund?",
            "My status reads refunded to ZaloPay, but my wallet balance hasn't risen yet—what now?",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_rfs_overdue_delay",
        intent="refund_status",
        partition="train",
        policy_source="POL-PAY-003",
        patterns=(
            "Twelve working days have passed since cancellation and my Visa credit still has not cleared.",
            "Why is my approved refund taking longer than the quoted seven-business-day SLA?",
            "Can you verify whether a bank-account typo bounced my pending reimbursement transfer?",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_rfs_split_check",
        intent="refund_status",
        partition="calibration",
        policy_source="POL-PAY-003",
        patterns=(
            "My TikiXU portion returned immediately, so why is the bank card portion still awaiting payout?",
            "Where can I confirm whether my refunded voucher and cash portions finished settling?",
            "How do I see the expected settlement date on an active reimbursement request?",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_rfs_weekend_lag",
        intent="refund_status",
        partition="evaluation",
        policy_source="POL-PAY-003",
        patterns=(
            "If my reimbursement was authorized on Friday afternoon, why hasn't my bank posted it yet?",
            "Does an approved-not-settled status mean Tiki already released the funds to Visa?",
            "How can I verify that my return payout left Tiki's payment gateway cleanly?",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_rfs_bounced_wire",
        intent="refund_status",
        partition="evaluation",
        policy_source="POL-PAY-003",
        patterns=(
            "My reimbursement status suddenly switched to payout failed—how do I check why the transfer bounced?",
            "Can I track when a re-issued refund transfer will reach my domestic checking account?",
            "Where does an active refund show up after a cancelled order closes in the app?",
        ),
    ),
    # ------------------------------------------------------------------
    # 11. payment_issue
    # ------------------------------------------------------------------
    ClosurePositiveFamily(
        template_group_id="cls_pay_card_declined",
        intent="payment_issue",
        partition="train",
        policy_source="POL-PAY-004",
        patterns=(
            "My Visa checkout keeps returning an authorization declined message despite sufficient credit limit.",
            "Why did 3D-Secure OTP verification time out and fail my checkout payment?",
            "Payment gateway threw error code 402 right after I confirmed my card CVV.",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_pay_debited_unconfirmed",
        intent="payment_issue",
        partition="train",
        policy_source="POL-PAY-004",
        patterns=(
            "My bank app deducted 850,000 VND for checkout, yet Tiki still shows awaiting payment.",
            "QR VietQR transfer succeeded from my phone, but the order page never recognized payment.",
            "Why did MoMo deduct money while the order status remained unpaid and later canceled?",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_pay_double_bill",
        intent="payment_issue",
        partition="train",
        policy_source="POL-PAY-004",
        patterns=(
            "My credit statement displays two identical pending charges for a single purchase attempt.",
            "After tapping pay again during slow Wi-Fi, my card got billed twice for one basket.",
            "Why did my account show two separate authorizations for the same invoice total?",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_pay_ewallet_timeout",
        intent="payment_issue",
        partition="calibration",
        policy_source="POL-PAY-004",
        patterns=(
            "ZaloPay hung on the spinning loader and disconnected before finalizing my checkout.",
            "My bank OTP SMS never arrived in time and now the payment link expired.",
            "Can I fix a failed e-wallet link at checkout without recreating my cart?",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_pay_installment_err",
        intent="payment_issue",
        partition="evaluation",
        policy_source="POL-PAY-004",
        patterns=(
            "Zero-interest installment conversion failed at the issuing-bank verification step.",
            "Why was my transaction rejected when selecting 12-month credit-card installment billing?",
            "How do I resolve a billing gateway error on an installment-eligible electronics cart?",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_pay_cod_limit",
        intent="payment_issue",
        partition="evaluation",
        policy_source="POL-PAY-004",
        patterns=(
            "Why is the cash-on-delivery radio button greyed out for this checkout total?",
            "My international Mastercard gets blocked by anti-fraud screening every time I place an order.",
            "Payment confirmation crashed mid-checkout and now I do not know if funds cleared.",
        ),
    ),
    # ------------------------------------------------------------------
    # 12. human_agent (always escalates via Gate 2b!)
    # ------------------------------------------------------------------
    ClosurePositiveFamily(
        template_group_id="cls_hum_live_advisor",
        intent="human_agent",
        partition="train",
        policy_source="POL-ESC-001",
        patterns=(
            "Stop automated replies—connect me immediately to a real customer-care specialist.",
            "Please hand this chat over to a live human operator right away.",
            "I want to talk directly with a real support representative rather than a virtual bot.",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_hum_supervisor_req",
        intent="human_agent",
        partition="train",
        policy_source="POL-ESC-001",
        patterns=(
            "Kindly escalate my ticket to a team lead or senior account manager now.",
            "Could a human supervisor review my case personally instead of automated scripts?",
            "Transfer my conversation directly to a customer-service agent who can handle exceptions.",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_hum_callback_line",
        intent="human_agent",
        partition="train",
        policy_source="POL-ESC-001",
        patterns=(
            "May I get patched through to a telephone helpline advisor or live chat staff member?",
            "Put a real agent on the line to assist me personally, please.",
            "How do I bypass the chatbot queue and speak directly to live support staff?",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_hum_escalate_now",
        intent="human_agent",
        partition="calibration",
        policy_source="POL-ESC-001",
        patterns=(
            "Do not send canned help links—route this conversation straight to a live rep.",
            "Can someone from your human care team join this thread right now?",
            "Please connect me with an actual employee who has full account visibility.",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_hum_person_chat",
        intent="human_agent",
        partition="evaluation",
        policy_source="POL-ESC-001",
        patterns=(
            "I have tried self-service steps; let me message a live human representative now.",
            "Escalate me straight to an available support specialist immediately.",
            "Please arrange a callback from a customer service officer today.",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_hum_agent_handoff",
        intent="human_agent",
        partition="evaluation",
        policy_source="POL-ESC-001",
        patterns=(
            "This needs human judgment—transfer me to a support staff member now.",
            "I prefer speaking with an actual person in customer care rather than automated answers.",
            "Hand my case over to a live service consultant without further bot prompts.",
        ),
    ),
    # ------------------------------------------------------------------
    # KEY RETAIL ESCALATED_34 INTENTS (3 disjoint splits per intent)
    # Ensures modern marketplace style never biases predictions to SUP11
    # ------------------------------------------------------------------
    # product_information (crucial boundary with policy/shipping!)
    ClosurePositiveFamily(
        template_group_id="cls_e34_pinfo_trn",
        intent="product_information",
        partition="train",
        policy_source="ESCALATED_34:product_information",
        patterns=(
            "What exact dimensions, weight, and battery capacity are listed on this Tiki laptop SKU?",
            "Does this skincare serum contain fragrance or alcohol according to the manufacturer label?",
            "Could you confirm whether the warranty card covers global voltage on this espresso machine?",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_e34_pinfo_cal",
        intent="product_information",
        partition="calibration",
        policy_source="ESCALATED_34:product_information",
        patterns=(
            "Are genuine replacement filter cartridges included inside the box of this air purifier?",
            "Can you tell me the fabric blend and washing rating for this waterproof jacket listing?",
            "What hardware ports and RAM speed does this specific notebook model ship with?",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_e34_pinfo_evl",
        intent="product_information",
        partition="evaluation",
        policy_source="ESCALATED_34:product_information",
        patterns=(
            "Is this Bluetooth speaker certified IP67 waterproof and compatible with USB-C fast charging?",
            "What materials make up the non-stick coating on this ceramic cookware pan?",
            "Does this official brand listing come with an authenticated importer seal and user guide?",
        ),
    ),
    # availability
    ClosurePositiveFamily(
        template_group_id="cls_e34_avail_trn",
        intent="availability",
        partition="train",
        policy_source="ESCALATED_34:availability",
        patterns=(
            "When will the matte black 256GB edition restock in the marketplace warehouse?",
            "This running shoe shows sold out in size 42—are more units arriving soon?",
            "Could you check whether the official store still holds inventory of this monitor stand?",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_e34_avail_cal",
        intent="availability",
        partition="calibration",
        policy_source="ESCALATED_34:availability",
        patterns=(
            "Is this limited-edition ceramic mug still in stock for immediate fulfillment?",
            "Do you have any remaining stock left in the Hanoi hub for this desk lamp?",
            "Let me know whether the navy medium variant is back in stock yet.",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_e34_avail_evl",
        intent="availability",
        partition="evaluation",
        policy_source="ESCALATED_34:availability",
        patterns=(
            "How many units of this wireless router are left available to order right now?",
            "Can you verify inventory availability for the silver XL version before I check out?",
            "Has this out-of-stock book title been scheduled for reprint replenishment?",
        ),
    ),
    # availability_online
    ClosurePositiveFamily(
        template_group_id="cls_e34_avonl_trn",
        intent="availability_online",
        partition="train",
        policy_source="ESCALATED_34:availability_online",
        patterns=(
            "Can I purchase this kitchen blender directly online on the Tiki website right now?",
            "Is the e-commerce storefront still selling this tablet sleeve online?",
            "Check if this seasonal gift box is purchasable on the mobile shopping app.",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_e34_avonl_cal",
        intent="availability_online",
        partition="calibration",
        policy_source="ESCALATED_34:availability_online",
        patterns=(
            "Are buyers able to order that exclusive vinyl album through the online catalog today?",
            "Is this cosmetic bundle sold online via web checkout as well as in retail booths?",
            "Please check online catalog availability for this mechanical keyboard model.",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_e34_avonl_evl",
        intent="availability_online",
        partition="evaluation",
        policy_source="ESCALATED_34:availability_online",
        patterns=(
            "Is the green edition available to order online directly from the web catalog?",
            "Can online shoppers still add this portable SSD listing to their digital cart today?",
            "Verify whether that electronics item remains purchasable via the online marketplace.",
        ),
    ),
    # exchange_product
    ClosurePositiveFamily(
        template_group_id="cls_e34_exch_trn",
        intent="exchange_product",
        partition="train",
        policy_source="ESCALATED_34:exchange_product",
        patterns=(
            "I ordered size M sneakers by mistake—how can I swap them for size L instead?",
            "Could I exchange this blue backpack for the grey colorway of identical value?",
            "Do you support direct size replacement if an apparel fit feels too tight?",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_e34_exch_cal",
        intent="exchange_product",
        partition="calibration",
        policy_source="ESCALATED_34:exchange_product",
        patterns=(
            "I received a working toaster in silver, and I would like to swap it for the black model.",
            "How does an even item-for-item exchange work if I prefer another voltage variant?",
            "Can the seller trade my unopened medium hoodie for a large one without rebuying?",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_e34_exch_evl",
        intent="exchange_product",
        partition="evaluation",
        policy_source="ESCALATED_34:exchange_product",
        patterns=(
            "Please arrange a product swap so I get the USB-C keyboard version instead of Lightning.",
            "Is direct product replacement supported when I bought the wrong phone case size?",
            "Help me swap this unwanted green sweater for the burgundy variant from the same store.",
        ),
    ),
    # damaged_delivery
    ClosurePositiveFamily(
        template_group_id="cls_e34_dmg_trn",
        intent="damaged_delivery",
        partition="train",
        policy_source="ESCALATED_34:damaged_delivery",
        patterns=(
            "When I opened the shipping box, the glass carafe inside was shattered into pieces.",
            "My new monitor arrived with a cracked screen corner and dented bezel.",
            "The parcel reached me crushed and the ceramic bowl inside was broken in transit.",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_e34_dmg_cal",
        intent="damaged_delivery",
        partition="calibration",
        policy_source="ESCALATED_34:damaged_delivery",
        patterns=(
            "Liquid leaked all over the detergent bottle and ruined the box during transit.",
            "I just unboxed my desk chair and the armrest frame arrived snapped in half.",
            "This delivered book spine arrived torn and soaked—someone damaged it before arrival.",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_e34_dmg_evl",
        intent="damaged_delivery",
        partition="evaluation",
        policy_source="ESCALATED_34:damaged_delivery",
        patterns=(
            "My porcelain dinnerware set arrived chipped and fractured inside the carton.",
            "The courier delivered a smashed package whose contents are visibly bent.",
            "I received an electric kettle with a cracked lid straight out of the shipping box.",
        ),
    ),
    # missing_item
    ClosurePositiveFamily(
        template_group_id="cls_e34_miss_trn",
        intent="missing_item",
        partition="train",
        policy_source="ESCALATED_34:missing_item",
        patterns=(
            "I paid for three bottles of shampoo, yet the sealed parcel only contained two.",
            "One accessory pouch listed on the packing slip is completely absent from my delivery.",
            "My combo box arrived short by one cable that should have been packed inside.",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_e34_miss_cal",
        intent="missing_item",
        partition="calibration",
        policy_source="ESCALATED_34:missing_item",
        patterns=(
            "Out of four ordered notebooks, only three arrived inside the courier bag.",
            "The charging dock promised inside this kit is missing from the delivered box.",
            "I opened the sealed carton and noticed an ordered item was left out at packing.",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_e34_miss_evl",
        intent="missing_item",
        partition="evaluation",
        policy_source="ESCALATED_34:missing_item",
        patterns=(
            "There were five snack packs on my receipt, but only four arrived in the package.",
            "The wireless mouse from my two-piece bundle was omitted from the box.",
            "I checked the shipping carton carefully and one paid item was never included.",
        ),
    ),
    # wrong_item
    ClosurePositiveFamily(
        template_group_id="cls_e34_wrng_trn",
        intent="wrong_item",
        partition="train",
        policy_source="ESCALATED_34:wrong_item",
        patterns=(
            "I ordered a mechanical keyboard and the warehouse packed a completely different webcam.",
            "The package contained dog food even though my invoice clearly says coffee beans.",
            "Someone mixed up the labels and sent me someone else's unrelated merchandise.",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_e34_wrng_cal",
        intent="wrong_item",
        partition="calibration",
        policy_source="ESCALATED_34:wrong_item",
        patterns=(
            "I bought an induction pan, yet a non-induction saucepan arrived in the mail.",
            "The seller shipped an android cable rather than the HDMI adapter I purchased.",
            "What I pulled out of the sealed box does not match the product I bought at all.",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_e34_wrng_evl",
        intent="wrong_item",
        partition="evaluation",
        policy_source="ESCALATED_34:wrong_item",
        patterns=(
            "My parcel came with white earbuds inside, whereas I ordered over-ear headphones.",
            "Wrong merchandise arrived—the packing slip has my name, but the SKU is incorrect.",
            "They sent a completely unrelated kitchen knife instead of the hairdryer I ordered.",
        ),
    ),
    # request_invoice
    ClosurePositiveFamily(
        template_group_id="cls_e34_inv_trn",
        intent="request_invoice",
        partition="train",
        policy_source="ESCALATED_34:request_invoice",
        patterns=(
            "Could you issue an official VAT red invoice under my company tax code for order TK-5510?",
            "Where do I download the stamped e-invoice PDF for my recent business purchase?",
            "Please send a formal tax receipt reflecting my corporate registration number.",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_e34_inv_cal",
        intent="request_invoice",
        partition="calibration",
        policy_source="ESCALATED_34:request_invoice",
        patterns=(
            "I need an updated VAT billing invoice for accounting—how can I obtain a copy?",
            "Can Tiki generate an electronic company tax invoice after checkout completes?",
            "Please email me the downloadable invoice PDF matching my delivered order.",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_e34_inv_evl",
        intent="request_invoice",
        partition="evaluation",
        policy_source="ESCALATED_34:request_invoice",
        patterns=(
            "My finance team requires a formal tax invoice for last week's office supplies order.",
            "How do I retrieve the XML and PDF VAT invoice file for a fulfilled purchase?",
            "Kindly provide a corporate billing receipt with our tax ID listed.",
        ),
    ),
    # payment_methods
    ClosurePositiveFamily(
        template_group_id="cls_e34_pmth_trn",
        intent="payment_methods",
        partition="train",
        policy_source="ESCALATED_34:payment_methods",
        patterns=(
            "Which digital wallets, domestic ATM cards, and cash options can buyers use at checkout?",
            "Does the marketplace accept Apple Pay, MoMo, or international American Express cards?",
            "What installment banking partners are currently supported for online purchases?",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_e34_pmth_cal",
        intent="payment_methods",
        partition="calibration",
        policy_source="ESCALATED_34:payment_methods",
        patterns=(
            "Can shoppers pay with VietQR bank transfers as well as ZaloPay at checkout?",
            "Which payment cards and e-wallets are accepted on Tiki right now?",
            "Do you take cash on delivery alongside Visa and Mastercard debit payments?",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_e34_pmth_evl",
        intent="payment_methods",
        partition="evaluation",
        policy_source="ESCALATED_34:payment_methods",
        patterns=(
            "List the supported payment channels available when paying for electronics online.",
            "Are ShopeePay or foreign JCB cards accepted at platform checkout?",
            "How many different ways can a customer settle a basket—e-wallets, COD, or wire?",
        ),
    ),
    # change_order
    ClosurePositiveFamily(
        template_group_id="cls_e34_chg_trn",
        intent="change_order",
        partition="train",
        policy_source="ESCALATED_34:change_order",
        patterns=(
            "Can I modify the shipping street address on an order before it ships out?",
            "Help me switch the quantity from one to two units on my active checkout.",
            "Is it possible to edit the recipient phone number inside a freshly confirmed order?",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_e34_chg_cal",
        intent="change_order",
        partition="calibration",
        policy_source="ESCALATED_34:change_order",
        patterns=(
            "I picked express delivery by accident—can I switch this pending order to standard shipping?",
            "Please alter the delivery note and receiver name on my unshipped parcel.",
            "How do I add another item into an order I placed ten minutes ago?",
        ),
    ),
    ClosurePositiveFamily(
        template_group_id="cls_e34_chg_evl",
        intent="change_order",
        partition="evaluation",
        policy_source="ESCALATED_34:change_order",
        patterns=(
            "Before warehouse handover, can I amend the product variant inside my existing purchase?",
            "I typed the wrong ward name—help me edit the destination on order TK-8842.",
            "Could I swap the payment mode on a confirmed checkout from COD to bank card?",
        ),
    ),
)


# ==============================================================================
# NEGATIVE FAMILIES (strictly NOT single-intent KB-draftable queries)
# ==============================================================================
CLOSURE_NEGATIVE_FAMILIES: Tuple[ClosureNegativeFamily, ...] = (
    # ------------------------------------------------------------------
    # 1. COMPOUND MULTI-INTENT (18 families: 9 train, 5 calibration, 4 evaluation)
    # Deliberately mixes 2+ unrelated requests inside a single message.
    # ------------------------------------------------------------------
    ClosureNegativeFamily(
        template_group_id="cls_neg_cmi_trn_track_cancel",
        category="compound_multi_intent",
        partition="train",
        patterns=(
            "First tell me where my shipment currently sits, and if it hasn't left the hub yet cancel the whole thing.",
            "Can you look up live courier tracking for order TK-104 and simultaneously stop delivery if it is delayed?",
            "I want two things: trace my active parcel right now, and abort it immediately if warehouse packing is still pending.",
        ),
    ),
    ClosureNegativeFamily(
        template_group_id="cls_neg_cmi_trn_ret_rfs",
        category="compound_multi_intent",
        partition="train",
        patterns=(
            "Explain your seven-day electronics return rule and also check why my previous refund hasn't hit Visa yet.",
            "Before I send back these headphones, walk me through return eligibility plus tell me where my old reimbursement is.",
            "Two separate questions: are opened headphones returnable, and when will last month's pending refund finish settling?",
        ),
    ),
    ClosureNegativeFamily(
        template_group_id="cls_neg_cmi_trn_dis_pay",
        category="compound_multi_intent",
        partition="train",
        patterns=(
            "My parcel says delivered when nothing showed up, AND my credit card was billed twice during checkout.",
            "Fix both problems on my account: courier lost the package at reception and MoMo deducted double money.",
            "I need help with two failures—shipping rider faked an attempt plus bank card threw duplicate billing.",
        ),
    ),
    ClosureNegativeFamily(
        template_group_id="cls_neg_cmi_trn_shp_dtm_can",
        category="compound_multi_intent",
        partition="train",
        patterns=(
            "How much is regional express postage, how many days does Da Nang transit take, and how do I void an order if too slow?",
            "Tell me province shipping fees alongside delivery days, plus show me where to abort checkout before dispatch.",
            "Compare standard courier charges and arrival windows, and let me cancel my pending cart right after.",
        ),
    ),
    ClosureNegativeFamily(
        template_group_id="cls_neg_cmi_trn_chg_rqr",
        category="compound_multi_intent",
        partition="train",
        patterns=(
            "Update my delivery phone number on order A and file a money-back claim for cancelled order B.",
            "While changing the street address on my upcoming parcel, also trigger reimbursement for last week's failed order.",
            "I need you to amend the shipping details on one purchase while submitting a refund request for a separate checkout.",
        ),
    ),
    ClosureNegativeFamily(
        template_group_id="cls_neg_cmi_trn_pinfo_shp",
        category="compound_multi_intent",
        partition="train",
        patterns=(
            "Does this blender include a glass jar, and how much does Freeship+ knock off bulky shipping rates?",
            "Confirm the wattage on that appliance listing and also calculate whether oversized delivery costs extra.",
            "Tell me the battery capacity of this speaker while explaining how regional courier fees apply.",
        ),
    ),
    ClosureNegativeFamily(
        template_group_id="cls_neg_cmi_trn_hum_inv_rpr",
        category="compound_multi_intent",
        partition="train",
        patterns=(
            "Connect me to a human advisor, email my corporate VAT invoice, and schedule a return courier pickup.",
            "Put a supervisor on chat so they can reissue our tax invoice and register a return for two broken bowls.",
            "I want a live representative immediately to handle both my missing VAT receipt and a damaged-goods return.",
        ),
    ),
    ClosureNegativeFamily(
        template_group_id="cls_neg_cmi_trn_wrng_miss_pay",
        category="compound_multi_intent",
        partition="train",
        patterns=(
            "You shipped the wrong keyboard color, omitted the mouse pad, and blocked my debit card on my next cart.",
            "Three issues in one ticket: missing bonus item, incorrect SKU packed, and payment gateway decline today.",
            "Resolve my mis-picked parcel, send the omitted charger cable, and unblock my credit-card OTP failure.",
        ),
    ),
    ClosureNegativeFamily(
        template_group_id="cls_neg_cmi_trn_avail_chg_rfp",
        category="compound_multi_intent",
        partition="train",
        patterns=(
            "Check if size XL restocked online, switch my pending order to that variant, and verify your bank refund policy.",
            "Let me know online inventory status, edit my active order quantity, plus clarify how e-wallet reversals work.",
            "Is the navy coat back in stock? Also amend my checkout variant and explain COD reimbursement rules.",
        ),
    ),
    ClosureNegativeFamily(
        template_group_id="cls_neg_cmi_cal_can_rqr_pmth",
        category="compound_multi_intent",
        partition="calibration",
        patterns=(
            "Void order TK-912 immediately, claim a refund back to my debit card, and list supported installment banks.",
            "Please abort my unpacked purchase, file the money-back request, and tell me which e-wallets you accept.",
            "Cancel this duplicate cart right now, initiate reimbursement for both charges, and check ZaloPay compatibility.",
        ),
    ),
    ClosureNegativeFamily(
        template_group_id="cls_neg_cmi_cal_trk_dis_exch",
        category="compound_multi_intent",
        partition="calibration",
        patterns=(
            "Trace where my overdue box stopped moving, complain about driver no-call, and arrange a size exchange.",
            "Look up the courier scan for parcel 1, report a crushed carton on parcel 2, and swap shoes on parcel 3.",
            "I want tracking progress checked, a stuck shipment investigated, plus a direct color swap arranged.",
        ),
    ),
    ClosureNegativeFamily(
        template_group_id="cls_neg_cmi_cal_rpo_shp_hum",
        category="compound_multi_intent",
        partition="calibration",
        patterns=(
            "Do unsealed cosmetics qualify for returns, who pays return postage, and transfer me to a senior agent anyway?",
            "Outline restricted return rules alongside return pickup costs, then hand this thread over to a live manager.",
            "Answer both my return-window and courier-fee questions before escalating directly to human support.",
        ),
    ),
    ClosureNegativeFamily(
        template_group_id="cls_neg_cmi_cal_pay_inv_pinfo",
        category="compound_multi_intent",
        partition="calibration",
        patterns=(
            "Fix my failed QR checkout, reissue the VAT PDF for business accounting, and check this laptop's RAM specs.",
            "My bank card was charged without order confirmation—also generate our company tax invoice and check wattage details.",
            "Resolve this declined card payment while emailing my missing red invoice and confirming ingredient details.",
        ),
    ),
    ClosureNegativeFamily(
        template_group_id="cls_neg_cmi_cal_dtm_avail_rfs",
        category="compound_multi_intent",
        partition="calibration",
        patterns=(
            "How fast does TikiNOW deliver to District 7, is the black kettle in stock, and where is last week's refund?",
            "Check stock availability on the desk lamp, estimate weekend courier speed, and trace my bank ARN payout.",
            "Confirm same-day delivery cutoffs, verify remaining units online, plus check why my wallet refund is overdue.",
        ),
    ),
    ClosureNegativeFamily(
        template_group_id="cls_neg_cmi_evl_can_trk_rfp",
        category="compound_multi_intent",
        partition="evaluation",
        patterns=(
            "Check live parcel status for shipment one, cancel shipment two cleanly, and clarify Visa refund timing.",
            "Two requests together: locate my courier transit checkpoint on A, void order B, and state ATM reversal SLA.",
            "Before aborting my second purchase, verify where the first package stands and how many days refunds take.",
        ),
    ),
    ClosureNegativeFamily(
        template_group_id="cls_neg_cmi_evl_rpr_dis_pay",
        category="compound_multi_intent",
        partition="evaluation",
        patterns=(
            "Report a misdelivered box to the wrong floor, submit a return for a torn sweater, and fix my OTP timeout.",
            "Handle both the neighbor-delivered package complaint and return pickup scheduling, plus my blocked Mastercard.",
            "I need an overdue parcel investigated alongside starting a partial return and resolving a double billing error.",
        ),
    ),
    ClosureNegativeFamily(
        template_group_id="cls_neg_cmi_evl_miss_rqr_inv",
        category="compound_multi_intent",
        partition="evaluation",
        patterns=(
            "One coffee bag was missing from my box, so issue a partial refund and send a corrected VAT receipt.",
            "File reimbursement for the unshipped cable, update the corporate tax invoice PDF, and check return postage.",
            "Claim back funds for an omitted item while regenerating my company invoice without waiting.",
        ),
    ),
    ClosureNegativeFamily(
        template_group_id="cls_neg_cmi_evl_hum_chg_pinfo",
        category="compound_multi_intent",
        partition="evaluation",
        patterns=(
            "Get a live agent here to edit my shipping ward, check product dimensions, and verify TikiPRO fee caps.",
            "Pass me to human care immediately because I must alter my delivery recipient and ask about allergen specs.",
            "Escalate to a specialist who can switch my checkout variant and explain regional shipping surcharges together.",
        ),
    ),
    # ------------------------------------------------------------------
    # 2. UNSUPPORTED PRODUCT OR MERCHANT (12 families: 6 train, 3 cal, 3 eval)
    # Out-of-taxonomy retail/B2B/seller/loyalty programs outside KB & 46 intents.
    # ------------------------------------------------------------------
    ClosureNegativeFamily(
        template_group_id="cls_neg_upm_trn_b2b",
        category="unsupported_product_or_merchant",
        partition="train",
        patterns=(
            "How do wholesale distributors apply for bulk net-60 corporate purchasing contracts?",
            "Can procurement teams negotiate tiered volume rebates for 500 office monitors?",
            "What vendor vetting documents are required to open a wholesale B2B buyer account?",
        ),
    ),
    ClosureNegativeFamily(
        template_group_id="cls_neg_upm_trn_seller_fees",
        category="unsupported_product_or_merchant",
        partition="train",
        patterns=(
            "What commission percentage does the marketplace deduct from electronics third-party storefronts?",
            "How do independent merchants appeal a storefront suspension due to late dispatch penalties?",
            "Where can a seller configure automated flash-deal campaign bids in Seller Center?",
        ),
    ),
    ClosureNegativeFamily(
        template_group_id="cls_neg_upm_trn_price_match",
        category="unsupported_product_or_merchant",
        partition="train",
        patterns=(
            "Will your platform match a lower weekend price advertised by a competing retail chain?",
            "If an identical blender drops on a rival site tomorrow, can I claim the price difference?",
            "Do you offer retroactive price-drop protection rebates within seven days of purchase?",
        ),
    ),
    ClosureNegativeFamily(
        template_group_id="cls_neg_upm_trn_loyalty_tiers",
        category="unsupported_product_or_merchant",
        partition="train",
        patterns=(
            "How many annual points are required to unlock Platinum VIP birthday bonus perks?",
            "Can unused reward points be gifted directly to a family member's account?",
            "Why did my accumulated member coins expire prior to the calendar year end?",
        ),
    ),
    ClosureNegativeFamily(
        template_group_id="cls_neg_upm_trn_giftcard_corp",
        category="unsupported_product_or_merchant",
        partition="train",
        patterns=(
            "How do HR teams purchase 200 branded digital gift cards for employee holiday bonuses?",
            "Can expired promotional physical gift vouchers be reactivated manually by billing?",
            "Where do recipients redeem third-party corporate reward codes for store balance?",
        ),
    ),
    ClosureNegativeFamily(
        template_group_id="cls_neg_upm_trn_ext_warranty",
        category="unsupported_product_or_merchant",
        partition="train",
        patterns=(
            "How can I transfer a purchased third-party accidental-damage insurance plan to a new owner?",
            "Does extended screen-cracking coverage cover water immersion at coastal beaches?",
            "Who underwrites the optional two-year appliance breakdown protection plan?",
        ),
    ),
    ClosureNegativeFamily(
        template_group_id="cls_neg_upm_cal_franchise",
        category="unsupported_product_or_merchant",
        partition="calibration",
        patterns=(
            "How do regional logistics operators bid to become a contracted parcel pickup franchise?",
            "What warehouse lease criteria apply when partnering with your fulfillment network?",
            "Who oversees merchant onboarding compliance for imported dietary supplements?",
        ),
    ),
    ClosureNegativeFamily(
        template_group_id="cls_neg_upm_cal_affiliate",
        category="unsupported_product_or_merchant",
        partition="calibration",
        patterns=(
            "When do affiliate creators receive monthly payout commissions from tagged video links?",
            "How can influencers register a custom referral storefront under your creator program?",
            "Why were three affiliate tracking clicks disqualified from last month's revenue report?",
        ),
    ),
    ClosureNegativeFamily(
        template_group_id="cls_neg_upm_cal_custom_craft",
        category="unsupported_product_or_merchant",
        partition="calibration",
        patterns=(
            "Can your engraving studio laser-etch our company emblem onto 80 stainless tumblers?",
            "Does the marketplace offer bespoke gift-boxing and handwritten calligraphy cards per parcel?",
            "How far ahead should event planners request custom embroidered merch runs?",
        ),
    ),
    ClosureNegativeFamily(
        template_group_id="cls_neg_upm_evl_tradein",
        category="unsupported_product_or_merchant",
        partition="evaluation",
        patterns=(
            "How much trade-in credit valuation does an older scratched smartphone receive toward a new flagship?",
            "Does your device buyback inspector accept tablets with minor battery swelling?",
            "Can buyers mail in two old laptops toward a single trade-up voucher?",
        ),
    ),
    ClosureNegativeFamily(
        template_group_id="cls_neg_upm_evl_install_svc",
        category="unsupported_product_or_merchant",
        partition="evaluation",
        patterns=(
            "Does split air-conditioner mounting include copper piping beyond the first three meters?",
            "How do homeowners book wall-drilling TV bracket technicians separately from delivery?",
            "What hourly labor fee applies for dismantling an old built-in dishwasher during installation?",
        ),
    ),
    ClosureNegativeFamily(
        template_group_id="cls_neg_upm_evl_tax_exempt",
        category="unsupported_product_or_merchant",
        partition="evaluation",
        patterns=(
            "How do diplomatic missions register diplomatic VAT tax-exemption certificates before ordering?",
            "Can registered charities upload tax-exempt status certificates to remove VAT at checkout?",
            "What export-zone customs paperwork exempts foreign diplomatic staff from domestic retail tax?",
        ),
    ),
    # ------------------------------------------------------------------
    # 3. UNDERSPECIFIED / AMBIGUOUS (10 families: 5 train, 3 cal, 2 eval)
    # ------------------------------------------------------------------
    ClosureNegativeFamily(
        template_group_id="cls_neg_und_trn_1",
        category="underspecified_ambiguous",
        partition="train",
        patterns=(
            "Can somebody check that thing I asked about yesterday afternoon?",
            "Please take another look because nothing changed since Tuesday.",
            "Still waiting over here—any progress yet on my side?",
        ),
    ),
    ClosureNegativeFamily(
        template_group_id="cls_neg_und_trn_2",
        category="underspecified_ambiguous",
        partition="train",
        patterns=(
            "Something looks wrong with the numbers showing up on screen.",
            "That option turned gray earlier and I do not know why.",
            "Why did it suddenly change like that without warning?",
        ),
    ),
    ClosureNegativeFamily(
        template_group_id="cls_neg_und_trn_3",
        category="underspecified_ambiguous",
        partition="train",
        patterns=(
            "Fix this for me quickly before tonight if possible.",
            "Hello, I need assistance with my situation right now.",
            "Can you sort out what went wrong a few minutes ago?",
        ),
    ),
    ClosureNegativeFamily(
        template_group_id="cls_neg_und_trn_4",
        category="underspecified_ambiguous",
        partition="train",
        patterns=(
            "Wait, did that actually go through properly or not?",
            "I got an unclear alert just now—what am I supposed to do next?",
            "Could someone verify whether everything looks right on there?",
        ),
    ),
    ClosureNegativeFamily(
        template_group_id="cls_neg_und_trn_5",
        category="underspecified_ambiguous",
        partition="train",
        patterns=(
            "Check the previous message I left and follow up soon.",
            "Never mind the earlier detail, just handle the main issue.",
            "Everything feels stuck today—help me move forward somehow.",
        ),
    ),
    ClosureNegativeFamily(
        template_group_id="cls_neg_und_cal_1",
        category="underspecified_ambiguous",
        partition="calibration",
        patterns=(
            "Hey, it still isn't sorted on my profile after trying twice.",
            "Do you happen to see the same prompt showing on your end?",
            "Please check whatever popped up under my latest notification.",
        ),
    ),
    ClosureNegativeFamily(
        template_group_id="cls_neg_und_cal_2",
        category="underspecified_ambiguous",
        partition="calibration",
        patterns=(
            "I tapped continue and now the screen just stopped responding cleanly.",
            "Wait—should I try again tomorrow or wait for an email first?",
            "Any update on that matter we touched on last week?",
        ),
    ),
    ClosureNegativeFamily(
        template_group_id="cls_neg_und_cal_3",
        category="underspecified_ambiguous",
        partition="calibration",
        patterns=(
            "Looks incomplete from here—can you clarify what happens now?",
            "Someone told me to check back later, so here I am.",
            "Can we undo what just occurred on my view a second ago?",
        ),
    ),
    ClosureNegativeFamily(
        template_group_id="cls_neg_und_evl_1",
        category="underspecified_ambiguous",
        partition="evaluation",
        patterns=(
            "Is this normal or did something fail quietly behind the scenes?",
            "Could you take a quick glance at my recent activity and advise?",
            "Still unclear what caused that odd popup earlier today.",
        ),
    ),
    ClosureNegativeFamily(
        template_group_id="cls_neg_und_evl_2",
        category="underspecified_ambiguous",
        partition="evaluation",
        patterns=(
            "Any clue why my page displays that notice right now?",
            "Please help resolve the snag from my last attempt cleanly.",
            "Not sure which step I missed, can you guide me through it?",
        ),
    ),
    # ------------------------------------------------------------------
    # 4. OFF-DOMAIN UNRELATED (10 families: 5 train, 3 cal, 2 eval)
    # ------------------------------------------------------------------
    ClosureNegativeFamily(
        template_group_id="cls_neg_off_trn_code",
        category="off_domain_unrelated",
        partition="train",
        patterns=(
            "How do I debug a circular import deadlock between two FastAPI routers in Python?",
            "Write a PostgreSQL window query that ranks monthly sales per region without subqueries.",
            "Why does Docker Desktop consume high RAM when mounting large WSL2 bind volumes?",
        ),
    ),
    ClosureNegativeFamily(
        template_group_id="cls_neg_off_trn_cook",
        category="off_domain_unrelated",
        partition="train",
        patterns=(
            "What internal roast temperature keeps smoked pork shoulder tender without drying out?",
            "How long should sourdough starter ferment before shaping rustic loaves at room heat?",
            "Substitute ingredients for buttermilk when baking fluffy blueberry pancakes at home?",
        ),
    ),
    ClosureNegativeFamily(
        template_group_id="cls_neg_off_trn_travel",
        category="off_domain_unrelated",
        partition="train",
        patterns=(
            "Which scenic train route crosses the Swiss Alps between Zermatt and St. Moritz?",
            "How many days before departure do Schengen tourist visas typically get stamped?",
            "Suggest a four-day coastal driving itinerary along central Vietnam during April.",
        ),
    ),
    ClosureNegativeFamily(
        template_group_id="cls_neg_off_trn_health",
        category="off_domain_unrelated",
        partition="train",
        patterns=(
            "Design a beginner half-marathon interval running schedule across twelve weeks.",
            "What stretching routine relieves lower-back stiffness after eight hours at a desk?",
            "Compare daily magnesium glycinate versus citrate absorption in sports nutrition.",
        ),
    ),
    ClosureNegativeFamily(
        template_group_id="cls_neg_off_trn_science",
        category="off_domain_unrelated",
        partition="train",
        patterns=(
            "Explain why Bayesian ridge regression shrinks correlated predictors smoothly.",
            "How do tidal forces gradually lengthen Earth's rotational day over geological eons?",
            "Summarize the treaty differences between the Kyoto Protocol and the Paris Agreement.",
        ),
    ),
    ClosureNegativeFamily(
        template_group_id="cls_neg_off_cal_weather",
        category="off_domain_unrelated",
        partition="calibration",
        patterns=(
            "Forecast humidity and thunderstorm risk in Singapore for tomorrow evening.",
            "Why do Pacific El Nino phases often trigger drier monsoons across Southeast Asia?",
            "What barometric pressure drop usually signals an approaching tropical depression?",
        ),
    ),
    ClosureNegativeFamily(
        template_group_id="cls_neg_off_cal_music",
        category="off_domain_unrelated",
        partition="calibration",
        patterns=(
            "Explain the chord progression trick behind a tritone substitution in jazz piano.",
            "Which microphone polar pattern minimizes room echo for solo acoustic guitar?",
            "How do luthiers adjust truss-rod neck relief on steel-string guitars?",
        ),
    ),
    ClosureNegativeFamily(
        template_group_id="cls_neg_off_cal_finance",
        category="off_domain_unrelated",
        partition="calibration",
        patterns=(
            "Compare dividend reinvestment compounding against municipal bond yield after inflation.",
            "How are unrealized capital gains treated under standard IFRS accounting rules?",
            "What separates a covered call option strategy from a cash-secured put?",
        ),
    ),
    ClosureNegativeFamily(
        template_group_id="cls_neg_off_evl_astro",
        category="off_domain_unrelated",
        partition="evaluation",
        patterns=(
            "How do gravitational microlensing surveys detect rogue exoplanets drifting outside stars?",
            "Why does Jupiter's Great Red Spot persist as an anticyclonic storm for centuries?",
            "Which telescope focal ratio captures wide-field emission nebulae cleanly?",
        ),
    ),
    ClosureNegativeFamily(
        template_group_id="cls_neg_off_evl_lang",
        category="off_domain_unrelated",
        partition="evaluation",
        patterns=(
            "How do pitch-accent rules shift between Tokyo and Kansai Japanese dialects?",
            "Explain the grammatical difference between Spanish preterite and imperfect past tense.",
            "What mnemonic systems help memorize Cyrillic cursive letter pairs quickly?",
        ),
    ),
)


def generate_closure_positive_records() -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for fam in CLOSURE_POSITIVE_FAMILIES:
        intent_bucket = "supported_12" if fam.intent in CORE_PRODUCT_INTENTS else "escalated_34"
        for idx, text in enumerate(fam.patterns):
            digest = hashlib.sha256(f"{fam.template_group_id}:{idx}:{text}".encode("utf-8")).hexdigest()[:12]
            records.append(
                {
                    "sample_id": f"{fam.template_group_id}_{idx}_{digest}",
                    "instruction": text,
                    "intent": fam.intent,
                    "intent_bucket": intent_bucket,
                    "template_group_id": fam.template_group_id,
                    "partition": fam.partition,
                    "policy_source": fam.policy_source,
                    "source": "closure_positive_20261113",
                    "selective_label": 1,
                }
            )
    return records


def generate_closure_negative_records() -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for fam in CLOSURE_NEGATIVE_FAMILIES:
        for idx, text in enumerate(fam.patterns):
            digest = hashlib.sha256(f"{fam.template_group_id}:{idx}:{text}".encode("utf-8")).hexdigest()[:12]
            records.append(
                {
                    "sample_id": f"{fam.template_group_id}_{idx}_{digest}",
                    "instruction": text,
                    "intent": "out_of_scope",
                    "category": fam.category,
                    "template_group_id": fam.template_group_id,
                    "partition": fam.partition,
                    "source": "closure_negative_20261113",
                    "selective_label": 0,
                }
            )
    return records


def audit_closure_datasets(
    pos_records: Sequence[Dict[str, Any]],
    neg_records: Sequence[Dict[str, Any]],
    *,
    repo_root: Path = REPO_ROOT,
    max_token_f1: float = 0.65,
    max_jaccard: float = 0.60,
    max_word_tfidf_cosine: float = 0.65,
) -> Dict[str, Any]:
    """Run split-isolation, prior-experiment, and 9-frozen-benchmark overlap audits."""
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

    prior_domain = generate_grouped_domain_records() + generate_grouped_negative_records()
    prior_selective = generate_selective_positive_records() + generate_selective_negative_records()
    prior_all = prior_domain + prior_selective
    prior_groups = {r["template_group_id"] for r in prior_all}
    new_groups = set().union(*groups_by_part.values())

    group_disjoint_splits = (
        groups_by_part["train"].isdisjoint(groups_by_part["calibration"])
        and groups_by_part["train"].isdisjoint(groups_by_part["evaluation"])
        and groups_by_part["calibration"].isdisjoint(groups_by_part["evaluation"])
    )
    group_disjoint_prior = new_groups.isdisjoint(prior_groups)

    prior_rows = [(r["sample_id"], r["instruction"]) for r in prior_all]
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
        "new_vs_prior_experiments": _pairwise_max_overlap(
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
        failures.append("template_group_overlap_with_prior_experiments")
    if internal_exact_dups:
        failures.append("internal_exact_duplicates")
    for cname, res in checks.items():
        if res["exact_matches"]:
            failures.append(f"{cname}:exact_match")
        if res["flagged_count"] > 0:
            failures.append(f"{cname}:high_similarity({res['flagged_count']})")

    return {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "audit_passed": len(failures) == 0,
        "failure_reasons": failures,
        "counts": {
            "positive_total": len(pos_records),
            "positive_supported_12": sum(1 for r in pos_records if r["intent_bucket"] == "supported_12"),
            "positive_escalated_34": sum(1 for r in pos_records if r["intent_bucket"] == "escalated_34"),
            "negative_total": len(neg_records),
            "by_partition": {
                part: {
                    "positive": sum(1 for r in pos_records if r["partition"] == part),
                    "positive_supported_12": sum(
                        1 for r in pos_records if r["partition"] == part and r["intent_bucket"] == "supported_12"
                    ),
                    "positive_escalated_34": sum(
                        1 for r in pos_records if r["partition"] == part and r["intent_bucket"] == "escalated_34"
                    ),
                    "negative": sum(1 for r in neg_records if r["partition"] == part),
                    "unique_groups": len(groups_by_part[part]),
                }
                for part in ("train", "calibration", "evaluation")
            },
            "negative_by_category": {
                cat: {
                    part: sum(
                        1 for r in neg_records if r["category"] == cat and r["partition"] == part
                    )
                    for part in ("train", "calibration", "evaluation")
                }
                for cat in (
                    "compound_multi_intent",
                    "unsupported_product_or_merchant",
                    "underspecified_ambiguous",
                    "off_domain_unrelated",
                )
            },
        },
        "group_disjoint_across_splits": group_disjoint_splits,
        "group_disjoint_against_prior_experiments": group_disjoint_prior,
        "internal_exact_duplicates_count": len(internal_exact_dups),
        "internal_exact_duplicates": internal_exact_dups[:10],
        "prior_experiments_row_count": len(prior_rows),
        "frozen_benchmarks_row_count": len(bench_rows),
        "pairwise_checks": checks,
    }


def _write_jsonl(path: Path, rows: Sequence[Dict[str, Any]]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return compute_sha256(path)


def export_closure_datasets(
    output_dir: Path,
    *,
    repo_root: Path = REPO_ROOT,
) -> Dict[str, Any]:
    """Generate, audit, and persist closure datasets + audit manifest."""
    pos = generate_closure_positive_records()
    neg = generate_closure_negative_records()
    audit = audit_closure_datasets(pos, neg, repo_root=repo_root)
    if not audit["audit_passed"]:
        raise RuntimeError(
            f"Closure dataset audit failed: {audit['failure_reasons']}\n"
            + json.dumps(audit["pairwise_checks"], indent=2)
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    files: Dict[str, Dict[str, Any]] = {}
    for split_name in ("train", "calibration", "evaluation"):
        p_split = [r for r in pos if r["partition"] == split_name]
        n_split = [r for r in neg if r["partition"] == split_name]
        p_path = output_dir / f"closure_positive_{split_name}.jsonl"
        n_path = output_dir / f"closure_negative_{split_name}.jsonl"
        files[f"closure_positive_{split_name}"] = {
            "path": str(p_path),
            "count": len(p_split),
            "sha256": _write_jsonl(p_path, p_split),
        }
        files[f"closure_negative_{split_name}"] = {
            "path": str(n_path),
            "count": len(n_split),
            "sha256": _write_jsonl(n_path, n_split),
        }
    for split_name in ("train", "calibration"):
        comb_rows = [r for r in pos if r["partition"] == split_name] + [r for r in neg if r["partition"] == split_name]
        c_path = output_dir / f"closure_combined_{split_name}.jsonl"
        files[f"closure_combined_{split_name}"] = {
            "path": str(c_path),
            "count": len(comb_rows),
            "sha256": _write_jsonl(c_path, comb_rows),
        }

    manifest = {
        "dataset_version": "task_a_closure_datasets_20261113",
        "files": files,
        "audit": audit,
    }
    manifest_path = output_dir / "closure_dataset_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    manifest["manifest_path"] = str(manifest_path)
    return manifest


if __name__ == "__main__":
    out_dir = REPO_ROOT / "artifacts/evaluation/task_a_closure_20261113/datasets"
    res = export_closure_datasets(out_dir, repo_root=REPO_ROOT)
    print(
        json.dumps(
            {
                "audit_passed": res["audit"]["audit_passed"],
                "counts": res["audit"]["counts"],
                "pairwise_summary": {
                    k: {
                        "exact_count": len(v["exact_matches"]),
                        "max_token_f1": v["max_token_f1"],
                        "max_jaccard": v["max_jaccard"],
                        "max_word_tfidf_cosine": v["max_word_tfidf_cosine"],
                        "flagged_count": v["flagged_count"],
                    }
                    for k, v in res["audit"]["pairwise_checks"].items()
                },
            },
            indent=2,
        )
    )
