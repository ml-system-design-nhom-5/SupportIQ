"""Group-isolated Bitext TRAIN + taxonomy-clean contrast & non-retail OOD splits.

Routes ALL single-intent STANDARD_INTENTS_46 rows (ESCALATED_34 + SUPPORTED_12) to positive
46-class CE + SupCon splits, keeps negative splits (Uniform-KL + sup12 ceiling + energy)
strictly for genuine non-46 OOD / multi_intent / other_domain rows, enforces active-KB semantic
boundaries (ordinary order status vs live vehicle/driver tracking; return eligibility vs
physical store channel), and balances supported contrast exposures (~8-12 rows/class).
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

from apps.core_backend.intent.routing import ESCALATED_34_INTENTS, STANDARD_INTENTS_46, SUPPORTED_12_INTENTS
from pipeline.evaluation.classifier_acceptance_gate import check_split_isolation_and_gold_contamination
from pipeline.training.boundary_curriculum_data import _load_frozen_benchmark_texts, _normalize_text
from pipeline.training.train_boundary_candidate import (
    _has_gold_conflict,
    _read_jsonl,
    _token_set,
    _write_jsonl,
    prepare_and_lock_splits,
    resolve_neg_repeat,
    validate_boundary_split_taxonomy,
)
from pipeline.training.train_domain_candidate import verify_original_46_label_lineage

# Semantic boundary guards aligned with active KB (POL-ORD-001 vs track_delivery; POL-RET-001 vs return_product_in_store).
_VEHICLE_GPS_TELEMETRY_RE = re.compile(
    r"\b(truck|delivery van|courier van|gps|driver|rider|stops away|gate photo|doorstep telemetry|"
    r"live courier route|attempted delivery)\b",
    re.IGNORECASE,
)
_INSTORE_CHANNEL_RE = re.compile(
    r"\b(brick-and-mortar|physical store|physical shop|retail branch|retail store|storefront|"
    r"store counter|walk-in|cashier|in person at (?:a|your|the) (?:store|shop|branch))\b",
    re.IGNORECASE,
)

# Balanced authored contrast families: (split, group_id, intent, text)
# Train supported contrast classes are balanced to 10 rows each (~8-12 target):
#   order_history=10, track_order=10, track_delivery=10,
#   return_product_in_store=12, return_policy=10, return_product=10.
AUTHORED_CONTRAST_FAMILIES: List[Tuple[str, str, str, str]] = [
    # --- TRAIN: order_history (ESCALATED_34) vs track_order (SUPPORTED_12, ordinary order status) ---
    ("train", "oh_to_trn_01", "order_history", "Can you pull up my past orders from earlier this year?"),
    ("train", "oh_to_trn_01", "order_history", "I want to view the full list of orders I previously placed on my account."),
    ("train", "oh_to_trn_01", "track_order", "What is the current status of my active order in My Orders?"),
    ("train", "oh_to_trn_02", "order_history", "Show me every purchase I have made with this account over the last six months."),
    ("train", "oh_to_trn_02", "order_history", "How do I see my old order records and receipts from last month?"),
    ("train", "oh_to_trn_02", "track_order", "Can I check the carrier tracking link for the shipment that left yesterday?"),
    ("train", "oh_to_trn_03", "order_history", "I need a summary of all completed orders tied to my profile."),
    ("train", "oh_to_trn_03", "order_history", "Where can I browse my prior order history and past invoices?"),
    ("train", "oh_to_trn_03", "track_order", "Has my recent order moved from awaiting packing to shipping yet?"),
    ("train", "oh_to_trn_04", "order_history", "Can I look back at items I bought two months ago in my order log?"),
    ("train", "oh_to_trn_04", "order_history", "List all previous transactions and archived orders under my email."),
    ("train", "oh_to_trn_04", "track_order", "Why is my tracking number not updating since Tuesday?"),
    ("train", "oh_to_trn_05", "order_history", "Retrieve my previous order log so I can verify what I bought before."),
    ("train", "oh_to_trn_05", "order_history", "How do I view my complete buying history on this store?"),
    ("train", "oh_to_trn_05", "track_order", "Please check the order tracking status and estimated arrival date for my purchase."),

    # --- TRAIN: track_delivery (ESCALATED_34, live vehicle/driver GPS) vs track_order (SUPPORTED_12) ---
    ("train", "td_to_trn_01", "track_delivery", "Share the driver's live GPS delivery status for my street drop-off."),
    ("train", "td_to_trn_01", "track_delivery", "Where is the delivery van carrying my box on the local route right now?"),
    ("train", "td_to_trn_01", "track_order", "Look up whether order #4910 is still pending confirmation or has shipped."),
    ("train", "td_to_trn_02", "track_delivery", "How many stops away is the courier truck delivering my parcel today?"),
    ("train", "td_to_trn_02", "track_delivery", "Show real-time map tracking for the local driver assigned to my drop-off."),
    ("train", "td_to_trn_02", "track_order", "Has my order number 5519 moved past warehouse processing yet?"),
    ("train", "td_to_trn_03", "track_delivery", "Why does the courier delivery alert say attempted drop-off at my gate?"),
    ("train", "td_to_trn_03", "track_delivery", "Is the parcel truck in my neighborhood for delivery this afternoon?"),
    ("train", "td_to_trn_03", "track_order", "Where can I view the order tracking summary for the order I placed on Monday?"),
    ("train", "td_to_trn_04", "track_delivery", "Check the courier's exact delivery progress and handoff proof."),
    ("train", "td_to_trn_04", "track_delivery", "When will the delivery driver reach my apartment building today?"),
    ("train", "td_to_trn_04", "track_order", "I want to look up my order status using my confirmation reference."),
    ("train", "td_to_trn_05", "track_delivery", "Show live doorstep delivery telemetry for my incoming parcel."),
    ("train", "td_to_trn_05", "track_delivery", "Did the delivery carrier leave a gate photo or signature at the front desk?"),
    ("train", "td_to_trn_05", "track_order", "Can you pull up the shipping stage and tracking number for order #8821?"),

    # --- TRAIN: return_product_in_store (ESCALATED_34) vs return_policy / return_product (SUPPORTED_12) ---
    ("train", "rp_trn_01", "return_product_in_store", "Can I bring this item back to a local brick-and-mortar store instead of mailing it?"),
    ("train", "rp_trn_01", "return_product_in_store", "Which retail store locations accept walk-in product returns?"),
    ("train", "rp_trn_01", "return_policy", "What are your general eligibility rules and time window for returning an item?"),
    ("train", "rp_trn_01", "return_policy", "How many days after delivery do buyers have to qualify for a return?"),
    ("train", "rp_trn_01", "return_product", "How do I start a standard mail-in return for an item I received?"),
    ("train", "rp_trn_01", "return_product", "Where in Order Management do I tap Request Return to send my item back?"),
    ("train", "rp_trn_02", "return_product_in_store", "If I bought something online, can I drop it off at your physical shop counter?"),
    ("train", "rp_trn_02", "return_product_in_store", "Do your retail branches take back defective goods in person?"),
    ("train", "rp_trn_02", "return_policy", "Are opened items eligible under your return guidelines?"),
    ("train", "rp_trn_02", "return_policy", "What condition must products be in according to your return terms?"),
    ("train", "rp_trn_02", "return_product", "I need a prepaid return shipping label to send this product back."),
    ("train", "rp_trn_02", "return_product", "Walk me through submitting a return request for my damaged item."),
    ("train", "rp_trn_03", "return_product_in_store", "Is in-store drop-off available for returning shoes I ordered online?"),
    ("train", "rp_trn_03", "return_product_in_store", "Can a store associate process my product return at the register?"),
    ("train", "rp_trn_03", "return_policy", "Do you charge a restocking fee under your return policy?"),
    ("train", "rp_trn_03", "return_policy", "What items are marked final sale and excluded from returns?"),
    ("train", "rp_trn_03", "return_product", "Please help me generate a return authorization for my order."),
    ("train", "rp_trn_03", "return_product", "I want to send back an unwanted item from my recent delivery."),
    ("train", "rp_trn_04", "return_product_in_store", "Can I hand my return package directly to a cashier at the nearest branch?"),
    ("train", "rp_trn_04", "return_product_in_store", "Do I need a receipt to return merchandise at a physical storefront?"),
    ("train", "rp_trn_04", "return_policy", "Could you explain your return window for marketplace versus direct orders?"),
    ("train", "rp_trn_04", "return_policy", "Are unsealed cosmetics or swimwear excluded from change-of-mind returns?"),
    ("train", "rp_trn_04", "return_product", "How do I package and ship back a product I no longer want?"),
    ("train", "rp_trn_04", "return_product", "I received the wrong size and want to initiate a product return."),
    ("train", "rp_trn_05", "return_product_in_store", "Where is the closest retail store where I can return this product face to face?"),
    ("train", "rp_trn_05", "return_product_in_store", "Are online purchases accepted for return at your local retail outlets?"),
    ("train", "rp_trn_05", "return_policy", "Do clearance items qualify for returns if original seals are intact?"),
    ("train", "rp_trn_05", "return_policy", "What restricted product categories cannot be returned for change of mind?"),
    ("train", "rp_trn_05", "return_product", "Can you guide me through scheduling a courier pickup for my return?"),
    ("train", "rp_trn_05", "return_product", "How do I lodge an online return claim for an item from my order?"),
    ("train", "rp_trn_06", "return_product_in_store", "Will a physical branch accept my returned item without mailing it?"),
    ("train", "rp_trn_06", "return_product_in_store", "Can I drop off a return in person at a retail shop today?"),

    # --- CAL FAMILIES (strictly isolated group_ids) ---
    ("cal", "oh_to_cal_01", "order_history", "Can I inspect my archived orders from previous years on my account?"),
    ("cal", "oh_to_cal_01", "order_history", "Where do I see a list of every past purchase I completed?"),
    ("cal", "oh_to_cal_01", "track_order", "Where can I view the current status of my order in My Orders?"),
    ("cal", "oh_to_cal_02", "order_history", "How do I look up my older order logs and past receipts?"),
    ("cal", "oh_to_cal_02", "order_history", "Show me all previous orders placed under my customer profile."),
    ("cal", "oh_to_cal_02", "track_order", "Has my order been dispatched from the warehouse yet?"),
    ("cal", "oh_to_cal_03", "order_history", "I want to browse my historical purchases from last quarter."),
    ("cal", "oh_to_cal_03", "order_history", "Is there a record of all my prior transactions on the site?"),
    ("cal", "oh_to_cal_03", "track_order", "What is the latest carrier scan and tracking stage for my order?"),
    ("cal", "rp_cal_01", "return_product_in_store", "Can I bring my online order to a physical store branch to return it?"),
    ("cal", "rp_cal_01", "return_product_in_store", "Do your brick-and-mortar shops accept walk-in returns?"),
    ("cal", "rp_cal_01", "return_policy", "How many days do I have under your return policy to send something back?"),
    ("cal", "rp_cal_01", "return_product", "How do I request a return label to mail back my item?"),
    ("cal", "rp_cal_02", "return_product_in_store", "Will a retail store clerk take back an item I bought online?"),
    ("cal", "rp_cal_02", "return_product_in_store", "Can I drop off returned merchandise at a nearby storefront?"),
    ("cal", "rp_cal_02", "return_policy", "What are the eligibility requirements in your return policy?"),
    ("cal", "rp_cal_02", "return_product", "Please initiate a return for the product I received yesterday."),
    ("cal", "rp_cal_03", "return_product_in_store", "Is in-person store return supported for items ordered on the web?"),
    ("cal", "rp_cal_03", "return_product_in_store", "Which physical store counters handle product returns?"),
    ("cal", "rp_cal_03", "return_policy", "Are sale items covered by your standard return policy?"),
    ("cal", "rp_cal_03", "return_product", "I need to return a defective item by mail; how do I start?"),
    ("cal", "td_to_cal_01", "track_delivery", "Where is the delivery driver carrying my package on the local route?"),
    ("cal", "td_to_cal_01", "track_delivery", "Check if the courier van is close to my home for doorstep delivery."),
    ("cal", "td_to_cal_01", "track_order", "Can you verify the shipping status of my open order?"),
    ("cal", "td_to_cal_02", "track_delivery", "How can I see final-mile courier delivery updates for my street?"),
    ("cal", "td_to_cal_02", "track_delivery", "Did the delivery driver mark my drop-off with a gate photo?"),
    ("cal", "td_to_cal_02", "track_order", "What is the current dispatch stage of my order?"),

    # --- EVAL FAMILIES (strictly isolated group_ids) ---
    ("eval", "oh_to_evl_01", "order_history", "Where can I check my past order archive from previous months?"),
    ("eval", "oh_to_evl_01", "order_history", "Show all historical orders I have ever placed with my login."),
    ("eval", "oh_to_evl_01", "track_order", "Can you check the current shipping stage of my active order?"),
    ("eval", "oh_to_evl_02", "order_history", "How do I review my earlier purchases and past order summaries?"),
    ("eval", "oh_to_evl_02", "order_history", "Pull up the history of all completed orders on my account."),
    ("eval", "oh_to_evl_02", "track_order", "What is the latest order tracking update on the purchase I placed yesterday?"),
    ("eval", "oh_to_evl_03", "order_history", "I need to look through my old order records from earlier this year."),
    ("eval", "oh_to_evl_03", "order_history", "Can I view every previous transaction in my order history?"),
    ("eval", "oh_to_evl_03", "track_order", "Where can I check the status and tracking code for my pending order?"),
    ("eval", "rp_evl_01", "return_product_in_store", "Can I take an online purchase into a physical retail shop to return it?"),
    ("eval", "rp_evl_01", "return_product_in_store", "Do your local storefronts accept in-person product returns?"),
    ("eval", "rp_evl_01", "return_policy", "What is the deadline for returns under your store return policy?"),
    ("eval", "rp_evl_01", "return_product", "How can I open a mail-in return for an unwanted product?"),
    ("eval", "rp_evl_02", "return_product_in_store", "Is returning an item at a brick-and-mortar branch allowed?"),
    ("eval", "rp_evl_02", "return_product_in_store", "Can a cashier at your store take back an item I ordered online?"),
    ("eval", "rp_evl_02", "return_policy", "Do your return rules allow returning opened electronics?"),
    ("eval", "rp_evl_02", "return_product", "Send me instructions to ship back a damaged product for return."),
    ("eval", "rp_evl_03", "return_product_in_store", "Where can I drop off a return in person at a retail location?"),
    ("eval", "rp_evl_03", "return_product_in_store", "Does your physical shop counter accept returns from web orders?"),
    ("eval", "rp_evl_03", "return_policy", "What are the conditions in your return policy?"),
    ("eval", "rp_evl_03", "return_product", "I want to start a return for the item that arrived broken."),
    ("eval", "td_to_evl_01", "track_delivery", "Can I see live GPS tracking of the delivery van approaching my block?"),
    ("eval", "td_to_evl_01", "track_delivery", "Track the courier's local doorstep delivery attempt for today."),
    ("eval", "td_to_evl_01", "track_order", "Look up the order status and carrier link for purchase #C902."),
    ("eval", "td_to_evl_01", "track_order", "Check whether my order is still packing or has already shipped."),
    ("eval", "td_to_evl_02", "track_delivery", "How many stops away is the local driver delivering my box today?"),
    ("eval", "td_to_evl_02", "track_delivery", "Verify the driver's final-mile delivery proof at my apartment."),
    ("eval", "td_to_evl_02", "track_order", "Please share the shipment stage and tracking link for my open order."),
    ("eval", "td_to_evl_02", "track_order", "Where can I see the fulfillment status of my recent purchase?"),
]

# Genuine non-46 compound (multi_intent) negative families combining SUPPORTED_12 + ESCALATED_34.
# Routed strictly to neg_train/neg_cal/neg_eval (Uniform-KL + sup12 ceil + energy).
AUTHORED_COMPOUND_FAMILIES: List[Tuple[str, str, str]] = [
    # --- TRAIN (16 rows, 8 isolated groups) ---
    ("train", "cmp_trn_01", "Cancel my pending order now and also show me my past order history from last year."),
    ("train", "cmp_trn_01", "Please check where my active order stands and tell me why my previous refund failed to post."),
    ("train", "cmp_trn_02", "What are your refund eligibility timelines and can I also exchange a jacket at a retail branch?"),
    ("train", "cmp_trn_02", "I want to request a refund for my broken item and update the delivery address on my other order."),
    ("train", "cmp_trn_03", "How do I start a mail-in return and also dispute a duplicate charge on my credit card?"),
    ("train", "cmp_trn_03", "Check the shipping status of my package and help me change the shipping method on an older order."),
    ("train", "cmp_trn_04", "Tell me when express shipping arrives and also review my previous purchases under this account."),
    ("train", "cmp_trn_04", "I need to cancel an unshipped order and ask a billing agent about an unrecognized fee."),
    ("train", "cmp_trn_05", "Explain your 30-day return rules and also let me exchange an item at a local retail branch."),
    ("train", "cmp_trn_05", "Can you track my active order status and also reset my locked account password?"),
    ("train", "cmp_trn_06", "Start a return for my wrong-size shoes and also check my loyalty points balance."),
    ("train", "cmp_trn_06", "What does standard shipping cost and can you also merge two separate past invoices?"),
    ("train", "cmp_trn_07", "I want to cancel my order before dispatch and also report a missing item from last month's box."),
    ("train", "cmp_trn_07", "How do I request a refund and also change the payment card on my recurring subscription?"),
    ("train", "cmp_trn_08", "Check my return policy eligibility and also tell me which retail store opens earliest tomorrow."),
    ("train", "cmp_trn_08", "Look up my current order status and also pull up my archived order receipts from winter."),
    # --- CAL (6 rows, 3 isolated groups) ---
    ("cal", "cmp_cal_01", "Check my open order status and also list all previous orders I placed last quarter."),
    ("cal", "cmp_cal_01", "What is your return policy window and can I also update the shipping address on my second order?"),
    ("cal", "cmp_cal_02", "Cancel my recent order right away and also fix a billing overcharge on my statement."),
    ("cal", "cmp_cal_02", "I need a refund for a defective product and want to modify the items in my second order."),
    ("cal", "cmp_cal_03", "How do I mail back a product for return and also escalate a complaint about courier damage?"),
    ("cal", "cmp_cal_03", "Check whether my order has shipped and also help me recover access to my old account."),
    # --- EVAL (6 rows, 3 isolated groups) ---
    ("eval", "cmp_evl_01", "Where is my order in transit and can you also show my complete past order history?"),
    ("eval", "cmp_evl_01", "Explain your standard return rules and tell me if a downtown store exchanges gifts in person."),
    ("eval", "cmp_evl_02", "Please cancel my unshipped order and also investigate a double charge on my card."),
    ("eval", "cmp_evl_02", "Request a refund for my broken item and also change the delivery address for another shipment."),
    ("eval", "cmp_evl_03", "Start a product return online and also ask support to verify an old invoice from last spring."),
    ("eval", "cmp_evl_03", "Check my order tracking number and also unlock my suspended customer profile."),
]

# Small, group-isolated general non-retail OOD families (telecom, municipal utility, SaaS billing, non-retail homonyms).
# Independently authored; routed strictly to neg_train/neg_cal/neg_eval as other_domain.
AUTHORED_NONRETAIL_OOD_FAMILIES: List[Tuple[str, str, str]] = [
    # --- TRAIN (12 rows, 4 isolated groups) ---
    ("train", "ood_tel_trn_01", "How do I upgrade my monthly fiber internet bandwidth tier at home?"),
    ("train", "ood_tel_trn_01", "Can I transfer an eSIM profile when activating a new cellular line?"),
    ("train", "ood_tel_trn_01", "Why did my prepaid mobile plan drop to slower data after the cycle reset?"),
    ("train", "ood_util_trn_01", "How do I submit a residential electric meter reading before the monthly due date?"),
    ("train", "ood_util_trn_01", "Why was a late reconnection fee added to my apartment water bill?"),
    ("train", "ood_util_trn_01", "Where can tenants set up automatic bank draft for municipal gas utilities?"),
    ("train", "ood_saas_trn_01", "How do I pause an annual cloud backup subscription before auto-renewal?"),
    ("train", "ood_saas_trn_01", "Can I switch my workspace billing cycle from monthly seats to annual invoicing?"),
    ("train", "ood_saas_trn_01", "Where do I update the tax ID on my software licensing invoice?"),
    ("train", "ood_hom_trn_01", "How do I file a state tax return extension before the April deadline?"),
    ("train", "ood_hom_trn_01", "Can passengers cancel a non-refundable domestic flight ticket for travel credit?"),
    ("train", "ood_hom_trn_01", "Where can patients track lab test turnaround results from an outpatient clinic?"),
    # --- CAL (6 rows, 3 isolated groups) ---
    ("cal", "ood_tel_cal_01", "How do I port my landline telephone number to a VoIP business trunk?"),
    ("cal", "ood_tel_cal_01", "Why does my cellular hotspot throttle speeds after 50 gigabytes per month?"),
    ("cal", "ood_util_cal_01", "How can homeowners dispute an estimated quarterly sewage utility charge?"),
    ("cal", "ood_util_cal_01", "Where do I report a streetlight outage and request municipal electrical repair?"),
    ("cal", "ood_hom_cal_01", "Can policyholders cancel a dental insurance rider mid-year without penalty?"),
    ("cal", "ood_hom_cal_01", "How do startups track patent application review status at the trademark office?"),
    # --- EVAL (6 rows, 3 isolated groups) ---
    ("eval", "ood_tel_evl_01", "Can I suspend my cellular voice service temporarily while working abroad?"),
    ("eval", "ood_tel_evl_01", "How do I check remaining international long-distance minutes on my phone plan?"),
    ("eval", "ood_util_evl_01", "What documents transfer residential electricity billing to a new apartment tenant?"),
    ("eval", "ood_util_evl_01", "Why did my monthly municipal water statement double compared to last winter?"),
    ("eval", "ood_hom_evl_01", "How do travelers claim a hotel reservation cancellation waiver during severe weather?"),
    ("eval", "ood_hom_evl_01", "Where can taxpayers track the status of an amended federal tax return?"),
]

SUPPORTED_CONTRAST_TRAIN_BOUNDS: Tuple[int, int] = (8, 12)


def _is_contradictory_base_row(row: Dict[str, Any]) -> bool:
    """Detect base domain rows that conflict with active-KB intent boundaries."""
    intent = str(row.get("intent", ""))
    txt = str(row.get("text") or row.get("instruction") or "")
    if intent == "track_order" and _VEHICLE_GPS_TELEMETRY_RE.search(txt):
        return True
    if intent == "return_policy" and _INSTORE_CHANNEL_RE.search(txt):
        return True
    return False


def validate_contrast_semantic_consistency(
    pos_rows: Sequence[Dict[str, Any]],
    neg_rows: Sequence[Dict[str, Any]],
    split_name: str = "split",
    *,
    check_train_balance: bool = False,
) -> Dict[str, int]:
    """Fail closed on KB semantic contradictions or unbalanced supported contrast exposures."""
    esc34 = set(ESCALATED_34_INTENTS)
    sup12 = set(SUPPORTED_12_INTENTS)
    for row in pos_rows:
        intent = str(row.get("intent", ""))
        txt = str(row.get("text") or row.get("instruction") or "")
        if intent == "track_order" and _VEHICLE_GPS_TELEMETRY_RE.search(txt):
            raise ValueError(f"Semantic contradiction in {split_name} track_order row {row.get('sample_id')}: {txt!r}")
        if intent == "return_policy" and _INSTORE_CHANNEL_RE.search(txt):
            raise ValueError(f"Semantic contradiction in {split_name} return_policy row {row.get('sample_id')}: {txt!r}")
        if intent in ("track_delivery", "return_product_in_store", "order_history") and intent not in esc34:
            raise ValueError(f"Expected ESCALATED_34 intent for {intent}")

    authored_pos_counts = Counter(
        str(r.get("intent"))
        for r in pos_rows
        if str(r.get("source", "")).startswith("authored_contrast_pos_")
    )
    if check_train_balance:
        lo, hi = SUPPORTED_CONTRAST_TRAIN_BOUNDS
        for intent in ("track_order", "return_policy", "return_product"):
            if intent not in sup12:
                continue
            cnt = authored_pos_counts.get(intent, 0)
            if cnt < lo or cnt > hi:
                raise ValueError(
                    f"Unbalanced authored supported contrast exposure for {intent} in {split_name}: {cnt} not in [{lo}, {hi}]"
                )

    for row in neg_rows:
        if int(row.get("selective_label", 0)) != 0:
            raise ValueError(f"Negative row must have selective_label=0: {row.get('sample_id')}")
    return dict(authored_pos_counts)


def prepare_and_lock_contrast_splits(
    *,
    worktree_root: Path,
    data_repo_root: Path,
    init_model_dir: Path,
    artifact_root: Path,
    bitext_contrast_per_intent: Tuple[int, int, int] = (20, 8, 8),
    seed: int = 20261114,
) -> Dict[str, Any]:
    """Build base d7ddaf2 splits, clean semantic contradictions, add balanced contrasts + non-retail OOD, and lock."""
    base_lock = prepare_and_lock_splits(
        worktree_root=worktree_root,
        data_repo_root=data_repo_root,
        init_model_dir=init_model_dir,
        artifact_root=artifact_root,
    )
    datasets_dir = artifact_root / "datasets"
    lock_path = datasets_dir / "dataset_lock_manifest.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))

    pos_train_raw = _read_jsonl(datasets_dir / "boundary_pos_train.jsonl")
    neg_train = _read_jsonl(datasets_dir / "boundary_neg_train.jsonl")
    pos_cal_raw = _read_jsonl(datasets_dir / "boundary_pos_calibration.jsonl")
    neg_cal = _read_jsonl(datasets_dir / "boundary_neg_calibration.jsonl")
    pos_eval_raw = _read_jsonl(datasets_dir / "boundary_pos_evaluation.jsonl")
    neg_eval = _read_jsonl(datasets_dir / "boundary_neg_evaluation.jsonl")
    bitext_clean = _read_jsonl(datasets_dir / "bitext_train_clean.jsonl")
    bitext_noisy = _read_jsonl(datasets_dir / "bitext_train_noisy.jsonl")
    bitext_cal = _read_jsonl(datasets_dir / "bitext_cal.jsonl")
    bitext_test = _read_jsonl(datasets_dir / "bitext_test_6690.jsonl")

    validate_boundary_split_taxonomy(pos_train_raw, neg_train, "base_train")
    validate_boundary_split_taxonomy(pos_cal_raw, neg_cal, "base_cal")
    validate_boundary_split_taxonomy(pos_eval_raw, neg_eval, "base_eval")

    removed_base_ids: List[str] = []
    pos_train = [r for r in pos_train_raw if not (_is_contradictory_base_row(r) and (removed_base_ids.append(str(r.get("sample_id"))) or True))]
    pos_cal = [r for r in pos_cal_raw if not (_is_contradictory_base_row(r) and (removed_base_ids.append(str(r.get("sample_id"))) or True))]
    pos_eval = [r for r in pos_eval_raw if not (_is_contradictory_base_row(r) and (removed_base_ids.append(str(r.get("sample_id"))) or True))]

    used_parent_ids = {
        str(r.get("parent_sample_id"))
        for r in (bitext_clean + bitext_noisy + bitext_cal)
        if r.get("parent_sample_id")
    }
    lineage = verify_original_46_label_lineage(repo_root=worktree_root)
    test_ids = set(lineage.test_df["sample_id"].astype(str).tolist())

    gold_bench = _load_frozen_benchmark_texts(data_repo_root)
    gold_norms = {_normalize_text(t) for _, t in gold_bench if _normalize_text(t)}
    gold_toks = [_token_set(t) for _, t in gold_bench if len(_token_set(t)) >= 4]
    existing_norms = {
        _normalize_text(r["text"])
        for r in (
            pos_train + neg_train + pos_cal + neg_cal + pos_eval + neg_eval + bitext_clean + bitext_noisy + bitext_cal + bitext_test
        )
    }

    s46 = set(STANDARD_INTENTS_46)
    n_trn, n_cal, n_evl = bitext_contrast_per_intent
    added_bitext_parent_ids: List[str] = []

    # 1. Canonical Bitext TRAIN rows for ESCALATED_34 confusable intents -> POSITIVE splits
    for intent in ("order_history", "return_product_in_store", "track_delivery"):
        if intent not in s46 or intent not in ESCALATED_34_INTENTS:
            raise ValueError(f"Expected ESCALATED_34 intent in STANDARD_INTENTS_46, got {intent}")
        sub = lineage.train_df[lineage.train_df["intent"] == intent].sample(
            frac=1.0, random_state=seed + len(intent) + sum(ord(c) for c in intent)
        )
        picks: List[Tuple[str, str]] = []
        for row in sub.itertuples(index=False):
            sid = str(row.sample_id)
            txt = str(row.instruction)
            norm = _normalize_text(txt)
            if (
                not norm
                or sid in used_parent_ids
                or sid in test_ids
                or norm in existing_norms
                or _has_gold_conflict(txt, gold_norms, gold_toks)
            ):
                continue
            existing_norms.add(norm)
            used_parent_ids.add(sid)
            picks.append((sid, txt))
            if len(picks) >= n_trn + n_cal + n_evl:
                break
        if len(picks) < n_trn + n_cal + n_evl:
            raise RuntimeError(f"Insufficient disjoint Bitext TRAIN rows for {intent}: got {len(picks)}")

        for split_name, slice_rows, target_list in (
            ("train", picks[:n_trn], pos_train),
            ("cal", picks[n_trn : n_trn + n_cal], pos_cal),
            ("eval", picks[n_trn + n_cal : n_trn + n_cal + n_evl], pos_eval),
        ):
            for sid, txt in slice_rows:
                added_bitext_parent_ids.append(sid)
                target_list.append(
                    {
                        "sample_id": f"contrast_bitext_pos_{split_name}_{sid}",
                        "parent_sample_id": sid,
                        "text": txt,
                        "instruction": txt,
                        "intent": intent,
                        "true_intent": intent,
                        "group_id": f"contrast_bitext_pos_{split_name}_{sid}",
                        "source": f"bitext_train_esc34_pos_{split_name}",
                        "category": "escalated_34_contrast",
                        "selective_label": 1,
                    }
                )

    # 2. Balanced authored single-intent contrast pairs (STANDARD_INTENTS_46) -> POSITIVE splits
    for idx, (split_name, gid, intent, txt) in enumerate(AUTHORED_CONTRAST_FAMILIES):
        if intent not in s46:
            raise ValueError(f"Authored contrast intent must be in STANDARD_INTENTS_46: {intent}")
        norm = _normalize_text(txt)
        if norm in existing_norms or _has_gold_conflict(txt, gold_norms, gold_toks):
            raise RuntimeError(f"Authored contrast row conflicts with existing/gold text: {txt!r}")
        existing_norms.add(norm)
        row = {
            "sample_id": f"contrast_auth_pos_{split_name}_{idx:03d}",
            "text": txt,
            "instruction": txt,
            "intent": intent,
            "true_intent": intent,
            "group_id": gid,
            "source": f"authored_contrast_pos_{split_name}",
            "category": "escalated_34_contrast" if intent in ESCALATED_34_INTENTS else "supported_12_domain",
            "selective_label": 1,
        }
        if split_name == "train":
            pos_train.append(row)
        elif split_name == "cal":
            pos_cal.append(row)
        else:
            pos_eval.append(row)

    # 3. Genuine non-46 compound (multi_intent) negatives -> NEGATIVE splits
    for idx, (split_name, gid, txt) in enumerate(AUTHORED_COMPOUND_FAMILIES):
        norm = _normalize_text(txt)
        if norm in existing_norms or _has_gold_conflict(txt, gold_norms, gold_toks):
            raise RuntimeError(f"Authored compound row conflicts with existing/gold text: {txt!r}")
        existing_norms.add(norm)
        row: Dict[str, Any] = {
            "sample_id": f"compound_auth_{split_name}_{idx:03d}",
            "text": txt,
            "instruction": txt,
            "intent": "multi_intent",
            "true_intent": "multi_intent",
            "group_id": gid,
            "source": f"authored_compound_{split_name}",
            "category": "compound_multi_intent",
            "selective_label": 0,
        }
        if split_name == "train":
            row["neg_repeat"] = 12
            neg_train.append(row)
        elif split_name == "cal":
            neg_cal.append(row)
        else:
            neg_eval.append(row)

    # 4. Small group-isolated non-retail OOD domains (other_domain) -> NEGATIVE splits
    for idx, (split_name, gid, txt) in enumerate(AUTHORED_NONRETAIL_OOD_FAMILIES):
        norm = _normalize_text(txt)
        if norm in existing_norms or _has_gold_conflict(txt, gold_norms, gold_toks):
            raise RuntimeError(f"Authored non-retail OOD row conflicts with existing/gold text: {txt!r}")
        existing_norms.add(norm)
        row = {
            "sample_id": f"nonretail_ood_{split_name}_{idx:03d}",
            "text": txt,
            "instruction": txt,
            "intent": "other_domain",
            "true_intent": "other_domain",
            "group_id": gid,
            "source": f"authored_nonretail_ood_{split_name}",
            "category": "non_retail_domain",
            "selective_label": 0,
        }
        if split_name == "train":
            row["neg_repeat"] = 12
            neg_train.append(row)
        elif split_name == "cal":
            neg_cal.append(row)
        else:
            neg_eval.append(row)

    # Strict taxonomy and semantic boundary verification across all splits
    validate_boundary_split_taxonomy(pos_train, neg_train, "train")
    validate_boundary_split_taxonomy(pos_cal, neg_cal, "cal")
    validate_boundary_split_taxonomy(pos_eval, neg_eval, "eval")
    authored_trn_counts = validate_contrast_semantic_consistency(pos_train, neg_train, "train", check_train_balance=True)
    validate_contrast_semantic_consistency(pos_cal, neg_cal, "cal")
    validate_contrast_semantic_consistency(pos_eval, neg_eval, "eval")

    full_train_all = pos_train + neg_train + bitext_clean + bitext_noisy
    full_cal_all = pos_cal + neg_cal + bitext_cal
    full_eval_all = pos_eval + neg_eval
    full_eval_with_test = full_eval_all + bitext_test

    trn_parents = {str(r["parent_sample_id"]) for r in full_train_all if r.get("parent_sample_id")}
    cal_parents = {str(r["parent_sample_id"]) for r in full_cal_all if r.get("parent_sample_id")}
    evl_parents = {str(r.get("parent_sample_id") or r.get("sample_id")) for r in bitext_test} | {
        str(r["parent_sample_id"]) for r in full_eval_all if r.get("parent_sample_id")
    }
    if (trn_parents & cal_parents) or (trn_parents & evl_parents) or (cal_parents & evl_parents):
        raise RuntimeError("Contrast parent_sample_id overlap across train/cal/eval+test")

    gold_tuples = [(f"gold_{i}", f"gold_{i}", t) for i, (_, t) in enumerate(gold_bench)]
    isolation = check_split_isolation_and_gold_contamination(
        train_rows=full_train_all,
        calibration_rows=full_cal_all,
        eval_rows=full_eval_with_test,
        gold_texts=gold_tuples,
    )
    if not isolation["passed"]:
        raise RuntimeError(f"Contrast split isolation failed: {isolation['failure_reasons']}")

    # Re-write updated JSONLs & refresh lock manifest hashes
    updated_files = {
        "boundary_pos_train": (datasets_dir / "boundary_pos_train.jsonl", pos_train),
        "boundary_neg_train": (datasets_dir / "boundary_neg_train.jsonl", neg_train),
        "boundary_pos_calibration": (datasets_dir / "boundary_pos_calibration.jsonl", pos_cal),
        "boundary_neg_calibration": (datasets_dir / "boundary_neg_calibration.jsonl", neg_cal),
        "boundary_pos_evaluation": (datasets_dir / "boundary_pos_evaluation.jsonl", pos_eval),
        "boundary_neg_evaluation": (datasets_dir / "boundary_neg_evaluation.jsonl", neg_eval),
        "full_train_split": (datasets_dir / "full_train_split.jsonl", full_train_all),
        "full_cal_split": (datasets_dir / "full_cal_split.jsonl", full_cal_all),
    }
    lock.setdefault("files", {})
    for key, (path, rows) in updated_files.items():
        sha = _write_jsonl(path, rows)
        lock["dataset_hashes"][key] = sha
        lock["files"][key] = {"path": str(path), "sha256": sha, "rows": len(rows)}

    lock["counts"] = {
        "domain_pos_train": len(pos_train),
        "domain_neg_train": len(neg_train),
        "bitext_train_clean": len(bitext_clean),
        "bitext_train_noisy": len(bitext_noisy),
        "domain_pos_cal": len(pos_cal),
        "domain_neg_cal": len(neg_cal),
        "bitext_cal": len(bitext_cal),
        "domain_pos_eval": len(pos_eval),
        "domain_neg_eval": len(neg_eval),
        "bitext_test_eval": base_lock["counts"]["bitext_test_eval"],
    }

    # Exact 46-class positive vs Uniform-KL negative exposure breakdown
    sup12_pos_rows = [r for r in pos_train if r["intent"] not in ESCALATED_34_INTENTS]
    esc34_pos_rows = [r for r in pos_train if r["intent"] in ESCALATED_34_INTENTS]
    sup12_pos_eff = len(sup12_pos_rows) * 4
    esc34_pos_eff = len(esc34_pos_rows) * 5
    domain_pos_eff = sup12_pos_eff + esc34_pos_eff
    bitext_eff = len(bitext_clean) + len(bitext_noisy)

    base_neg_rows = [r for r in neg_train if not str(r.get("sample_id", "")).startswith(("compound_auth_", "nonretail_ood_"))]
    compound_new_rows = [r for r in neg_train if str(r.get("sample_id", "")).startswith("compound_auth_")]
    nonretail_new_rows = [r for r in neg_train if str(r.get("sample_id", "")).startswith("nonretail_ood_")]
    base_neg_eff = sum(resolve_neg_repeat(r, 12) for r in base_neg_rows)
    base_compound_raw = sum(
        1
        for r in base_neg_rows
        if r.get("intent") == "multi_intent" or r.get("category") in ("multi_intent", "compound_multi_intent")
    )
    compound_new_eff = sum(resolve_neg_repeat(r, 12) for r in compound_new_rows)
    nonretail_new_eff = sum(resolve_neg_repeat(r, 12) for r in nonretail_new_rows)
    neg_eff_total = base_neg_eff + compound_new_eff + nonretail_new_eff
    compound_eff_total = base_compound_raw * 12 + compound_new_eff
    total_eff_train = domain_pos_eff + bitext_eff + neg_eff_total

    lock["contrast_extension"] = {
        "bitext_contrast_per_intent": list(bitext_contrast_per_intent),
        "bitext_contrast_intents": ["order_history", "return_product_in_store", "track_delivery"],
        "added_bitext_parent_ids_count": len(added_bitext_parent_ids),
        "removed_contradictory_base_ids": removed_base_ids,
        "authored_contrast_pos_rows": len(AUTHORED_CONTRAST_FAMILIES),
        "authored_contrast_train_by_intent": authored_trn_counts,
        "authored_compound_neg_rows": len(AUTHORED_COMPOUND_FAMILIES),
        "authored_nonretail_ood_rows": len(AUTHORED_NONRETAIL_OOD_FAMILIES),
        "neg_intents_in_standard_46_count": 0,
        "pos_non_46_count": 0,
        "semantic_consistency_passed": True,
        "isolation_passed": isolation["passed"],
    }
    lock["effective_exposure_counts"] = {
        "positive_46_ce_mask": {
            "domain_pos_supported12_raw": len(sup12_pos_rows),
            "domain_pos_supported12_effective": sup12_pos_eff,
            "domain_pos_escalated34_raw": len(esc34_pos_rows),
            "domain_pos_escalated34_effective": esc34_pos_eff,
            "domain_pos_total_raw": len(pos_train),
            "domain_pos_total_effective": domain_pos_eff,
            "bitext_replay_effective": bitext_eff,
            "total_positive_ce_effective": domain_pos_eff + bitext_eff,
        },
        "negative_uniform_kl_mask": {
            "baseline_neg_raw": len(base_neg_rows),
            "baseline_neg_effective": base_neg_eff,
            "baseline_compound_raw": base_compound_raw,
            "new_compound_neg_raw": len(compound_new_rows),
            "new_compound_neg_effective": compound_new_eff,
            "new_nonretail_ood_raw": len(nonretail_new_rows),
            "new_nonretail_ood_effective": nonretail_new_eff,
            "total_neg_effective": neg_eff_total,
            "total_compound_neg_effective": compound_eff_total,
            "compound_share_of_effective_neg": round(compound_eff_total / neg_eff_total, 4) if neg_eff_total else 0.0,
        },
        "total_effective_train_rows": total_eff_train,
        "batches_per_epoch_bs32": (total_eff_train + 31) // 32,
    }
    lock_path.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")
    return lock
