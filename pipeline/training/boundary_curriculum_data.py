"""Boundary-hardened curriculum dataset builder for Task A (Ponytail Ultra).

Combines audited closure positive/negative families with targeted, group-isolated
ESCALATED_34 vs SUPPORTED_12 boundary contrasts, multi-intent compounds, and
homonym OOD negatives. Verifies split isolation and zero gold benchmark
contamination BEFORE any model training runs.
"""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

from apps.core_backend.intent.routing import ESCALATED_34_INTENTS, STANDARD_INTENTS_46, SUPPORTED_12_INTENTS
from pipeline.training.closure_domain_data import (
    generate_closure_negative_records,
    generate_closure_positive_records,
)
from pipeline.training.domain_templates import (
    REPO_ROOT,
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


@dataclass(frozen=True)
class BoundaryFamily:
    template_group_id: str
    intent: str  # 46-class label or "out_of_scope"
    partition: str  # "train" | "calibration" | "evaluation"
    category: str
    patterns: Tuple[str, ...]


# Brand-new boundary-focused families partitioned atomically before generation.
BOUNDARY_POSITIVE_FAMILIES: Tuple[BoundaryFamily, ...] = (
    # --- ESCALATED_34 vs SUPPORTED_12 hard contrasts ---
    BoundaryFamily(
        "bnd_prodinfo_warranty_trn",
        "product_information",
        "train",
        "escalated_34_contrast",
        (
            "How long does the manufacturer warranty cover refurbished electronics sold here?",
            "Does the factory protection term apply to battery wear on laptop models?",
            "Tell me the voltage rating and chassis material of the wireless vacuum.",
            "Are sealed accessories included inside the box for that camera bundle?",
        ),
    ),
    BoundaryFamily(
        "bnd_prodinfo_warranty_cal",
        "product_information",
        "calibration",
        "escalated_34_contrast",
        (
            "What length of manufacturer hardware warranty comes with factory-reconditioned tablets?",
            "Which Bluetooth codec and water-resistance grade does that speaker carry?",
        ),
    ),
    BoundaryFamily(
        "bnd_prodinfo_warranty_evl",
        "product_information",
        "evaluation",
        "escalated_34_contrast",
        (
            "Could you specify the warranty period and screen panel type on the reconditioned ultrabook?",
            "Are spare ear tips and USB-C charging cables supplied inside the retail packaging?",
        ),
    ),
    BoundaryFamily(
        "bnd_exchange_trn",
        "exchange_product",
        "train",
        "escalated_34_contrast",
        (
            "Swap the medium jacket I bought for a large size under your replacement option.",
            "Can I replace an unused pair of shoes with another color instead of claiming money back?",
            "What is the time limit to request a size swap on unopened apparel?",
        ),
    ),
    BoundaryFamily(
        "bnd_exchange_cal",
        "exchange_product",
        "calibration",
        "escalated_34_contrast",
        (
            "How many days do shoppers have to swap clothing sizes rather than returning for cash?",
        ),
    ),
    BoundaryFamily(
        "bnd_exchange_evl",
        "exchange_product",
        "evaluation",
        "escalated_34_contrast",
        (
            "Is a direct variant replacement possible if the shirt sleeve runs short?",
        ),
    ),
    BoundaryFamily(
        "bnd_damaged_trn",
        "damaged_delivery",
        "train",
        "escalated_34_contrast",
        (
            "The parcel box arrived crushed and the glass jar inside shattered in transit.",
            "My ceramic mug came chipped when the courier dropped off the parcel today.",
            "Courier handed over a soaked carton with torn packaging and dented contents.",
        ),
    ),
    BoundaryFamily(
        "bnd_damaged_cal",
        "damaged_delivery",
        "calibration",
        "escalated_34_contrast",
        (
            "The monitor panel has cracks right out of the courier shipping carton.",
        ),
    ),
    BoundaryFamily(
        "bnd_damaged_evl",
        "damaged_delivery",
        "evaluation",
        "escalated_34_contrast",
        (
            "My parcel outer sleeve was ripped and the framed print arrived bent.",
        ),
    ),
    BoundaryFamily(
        "bnd_wrong_item_trn",
        "wrong_item",
        "train",
        "escalated_34_contrast",
        (
            "I ordered black wireless headphones but the box contained a white wired headset.",
            "The warehouse packed the wrong shoe size inside my parcel.",
        ),
    ),
    BoundaryFamily(
        "bnd_wrong_item_cal",
        "wrong_item",
        "calibration",
        "escalated_34_contrast",
        (
            "You shipped a medium blue sweater instead of the navy XL I selected.",
        ),
    ),
    BoundaryFamily(
        "bnd_wrong_item_evl",
        "wrong_item",
        "evaluation",
        "escalated_34_contrast",
        (
            "The package label has my name but holds a totally different kitchen appliance.",
        ),
    ),
    BoundaryFamily(
        "bnd_missing_item_trn",
        "missing_item",
        "train",
        "escalated_34_contrast",
        (
            "Only one of the two power banks from my bundle was inside the sealed parcel.",
            "My shipment arrived missing the charger cable listed on the packing slip.",
        ),
    ),
    BoundaryFamily(
        "bnd_missing_item_cal",
        "missing_item",
        "calibration",
        "escalated_34_contrast",
        (
            "The parcel had three shirts when I paid for four on the packing list.",
        ),
    ),
    BoundaryFamily(
        "bnd_missing_item_evl",
        "missing_item",
        "evaluation",
        "escalated_34_contrast",
        (
            "One accessory pouch is absent from the multi-piece order that just landed.",
        ),
    ),
    BoundaryFamily(
        "bnd_pay_methods_trn",
        "payment_methods",
        "train",
        "escalated_34_contrast",
        (
            "Which e-wallets, domestic ATM cards, or monthly installments do you accept at checkout?",
            "Can shoppers split checkout totals between Visa debit and cash on delivery?",
        ),
    ),
    BoundaryFamily(
        "bnd_pay_methods_cal",
        "payment_methods",
        "calibration",
        "escalated_34_contrast",
        (
            "Do you support Apple Pay or zero-interest credit card installments online?",
        ),
    ),
    BoundaryFamily(
        "bnd_pay_methods_evl",
        "payment_methods",
        "evaluation",
        "escalated_34_contrast",
        (
            "Are corporate bank transfers and prepaid debit cards accepted during checkout?",
        ),
    ),
    BoundaryFamily(
        "bnd_invoice_trn",
        "request_invoice",
        "train",
        "escalated_34_contrast",
        (
            "Send an official VAT tax receipt PDF addressed to my company registration number.",
            "Where can I download a GST billing invoice for last week's purchase?",
        ),
    ),
    BoundaryFamily(
        "bnd_invoice_cal",
        "request_invoice",
        "calibration",
        "escalated_34_contrast",
        (
            "Issue a formal commercial tax invoice PDF for accounting reimbursement.",
        ),
    ),
    BoundaryFamily(
        "bnd_invoice_evl",
        "request_invoice",
        "evaluation",
        "escalated_34_contrast",
        (
            "I need an itemized company VAT statement generated for my recent order.",
        ),
    ),
    # --- SUPPORTED_12 realistic phrasing gaps ---
    BoundaryFamily(
        "bnd_refund_policy_trn",
        "refund_policy",
        "train",
        "supported_12_domain",
        (
            "Under your reimbursement rules, how quickly are funds credited back after an approved return?",
            "Are original card transactions reimbursed to the same card or issued as store credit?",
            "Explain the banking turnaround days for money-back reversals once warehouse inspection clears.",
        ),
    ),
    BoundaryFamily(
        "bnd_refund_policy_cal",
        "refund_policy",
        "calibration",
        "supported_12_domain",
        (
            "How do your reimbursement terms handle returning funds to the buyer's original payment source?",
        ),
    ),
    BoundaryFamily(
        "bnd_refund_policy_evl",
        "refund_policy",
        "evaluation",
        "supported_12_domain",
        (
            "What rules govern whether money back goes to a wallet balance versus the initial bank card?",
        ),
    ),
    BoundaryFamily(
        "bnd_refund_status_trn",
        "refund_status",
        "train",
        "supported_12_domain",
        (
            "My approved reimbursement from five days ago still has not appeared on my statement; check its progress.",
            "Has the bank processed my pending money-back transfer for order TK-4490 yet?",
        ),
    ),
    BoundaryFamily(
        "bnd_refund_status_cal",
        "refund_status",
        "calibration",
        "supported_12_domain",
        (
            "Check whether the payout for my accepted return has cleared to my card yet.",
        ),
    ),
    BoundaryFamily(
        "bnd_refund_status_evl",
        "refund_status",
        "evaluation",
        "supported_12_domain",
        (
            "Can you inspect the current stage of my awaited reimbursement from Tuesday?",
        ),
    ),
    BoundaryFamily(
        "bnd_return_product_trn",
        "return_product",
        "train",
        "supported_12_domain",
        (
            "Start a pickup request so I can send back this unopened gadget from my order.",
            "Generate a prepaid drop-off label because I want to mail back an item I bought.",
        ),
    ),
    BoundaryFamily(
        "bnd_return_product_cal",
        "return_product",
        "calibration",
        "supported_12_domain",
        (
            "Open a return shipment ticket and arrange courier collection for my parcel.",
        ),
    ),
    BoundaryFamily(
        "bnd_return_product_evl",
        "return_product",
        "evaluation",
        "supported_12_domain",
        (
            "Help me lodge a product send-back request and print the courier slip.",
        ),
    ),
    BoundaryFamily(
        "bnd_payment_issue_trn",
        "payment_issue",
        "train",
        "supported_12_domain",
        (
            "My bank card was charged twice while checkout threw a gateway timeout error.",
            "Funds left my account via QR banking yet the order remains marked unpaid.",
        ),
    ),
    BoundaryFamily(
        "bnd_payment_issue_cal",
        "payment_issue",
        "calibration",
        "supported_12_domain",
        (
            "My card balance was debited on a failed checkout attempt that never confirmed.",
        ),
    ),
    BoundaryFamily(
        "bnd_payment_issue_evl",
        "payment_issue",
        "evaluation",
        "supported_12_domain",
        (
            "A duplicate charge appeared on my credit statement for a single order checkout.",
        ),
    ),
    BoundaryFamily(
        "bnd_delivery_time_trn",
        "delivery_time",
        "train",
        "supported_12_domain",
        (
            "How many business days do express and economy courier tiers typically take to reach urban addresses?",
            "What is the estimated shipping lead time between dispatch and doorstep arrival?",
        ),
    ),
    BoundaryFamily(
        "bnd_delivery_time_cal",
        "delivery_time",
        "calibration",
        "supported_12_domain",
        (
            "Compare typical transit timeframes for standard parcel shipping versus express dispatch.",
        ),
    ),
    BoundaryFamily(
        "bnd_delivery_time_evl",
        "delivery_time",
        "evaluation",
        "supported_12_domain",
        (
            "Approximately how long does courier transit take once a parcel leaves the regional hub?",
        ),
    ),
    BoundaryFamily(
        "bnd_track_order_trn",
        "track_order",
        "train",
        "supported_12_domain",
        (
            "Show me the live fulfillment stage of order ORD-7712 which still shows Awaiting Pickup.",
            "Check what step my order is currently stuck at before courier handoff.",
        ),
    ),
    BoundaryFamily(
        "bnd_track_order_cal",
        "track_order",
        "calibration",
        "supported_12_domain",
        (
            "Pull up the latest processing status for my purchase that has not dispatched yet.",
        ),
    ),
    BoundaryFamily(
        "bnd_track_order_evl",
        "track_order",
        "evaluation",
        "supported_12_domain",
        (
            "Where does my order stand right now in the warehouse confirmation queue?",
        ),
    ),
    BoundaryFamily(
        "bnd_cancel_order_trn",
        "cancel_order",
        "train",
        "supported_12_domain",
        (
            "Stop and void order ORD-5581 right now before the warehouse hands it to the driver.",
            "Abort my freshly submitted order immediately because I entered the wrong address.",
        ),
    ),
    BoundaryFamily(
        "bnd_cancel_order_cal",
        "cancel_order",
        "calibration",
        "supported_12_domain",
        (
            "Please terminate my unshipped order before packing finishes.",
        ),
    ),
    BoundaryFamily(
        "bnd_cancel_order_evl",
        "cancel_order",
        "evaluation",
        "supported_12_domain",
        (
            "Cancel my pending purchase prior to courier pickup today.",
        ),
    ),
    BoundaryFamily(
        "bnd_shipping_costs_trn",
        "shipping_costs",
        "train",
        "supported_12_domain",
        (
            "What cart subtotal waives standard parcel delivery fees, and how much is express postage?",
            "Explain the courier surcharge when shipping bulky items below the free threshold.",
        ),
    ),
    BoundaryFamily(
        "bnd_shipping_costs_cal",
        "shipping_costs",
        "calibration",
        "supported_12_domain",
        (
            "Tell me the minimum order value for complimentary delivery versus flat postage rates.",
        ),
    ),
    BoundaryFamily(
        "bnd_shipping_costs_evl",
        "shipping_costs",
        "evaluation",
        "supported_12_domain",
        (
            "How are postage charges calculated on orders under the free-shipping cutoff?",
        ),
    ),
    BoundaryFamily(
        "bnd_delivery_issue_trn",
        "delivery_issue",
        "train",
        "supported_12_domain",
        (
            "Tracking claims parcel delivered this morning yet nothing is at reception or my gate.",
            "My parcel has stayed frozen at the sorting hub for four days past the promised window.",
        ),
    ),
    BoundaryFamily(
        "bnd_delivery_issue_cal",
        "delivery_issue",
        "calibration",
        "supported_12_domain",
        (
            "The courier marked drop-off complete but nobody at my address received a parcel.",
        ),
    ),
    BoundaryFamily(
        "bnd_delivery_issue_evl",
        "delivery_issue",
        "evaluation",
        "supported_12_domain",
        (
            "My shipment is overdue with zero movement at the local depot since Monday.",
        ),
    ),
    BoundaryFamily(
        "bnd_return_policy_trn",
        "return_policy",
        "train",
        "supported_12_domain",
        (
            "How many days are buyers allowed to send back sealed retail goods under standard store rules?",
            "Which categories are excluded from your 30-day send-back eligibility rules?",
        ),
    ),
    BoundaryFamily(
        "bnd_return_policy_cal",
        "return_policy",
        "calibration",
        "supported_12_domain",
        (
            "What condition tags and day limits govern returning eligible marketplace goods?",
        ),
    ),
    BoundaryFamily(
        "bnd_return_policy_evl",
        "return_policy",
        "evaluation",
        "supported_12_domain",
        (
            "Outline the non-returnable category rules and standard return eligibility period.",
        ),
    ),
    BoundaryFamily(
        "bnd_request_refund_trn",
        "request_refund",
        "train",
        "supported_12_domain",
        (
            "Open a formal reimbursement claim for my cancelled order paid last week.",
            "Submit a money-back request because the seller never fulfilled the order.",
        ),
    ),
    BoundaryFamily(
        "bnd_request_refund_cal",
        "request_refund",
        "calibration",
        "supported_12_domain",
        (
            "File a reimbursement ticket to get my funds returned on an unfulfilled purchase.",
        ),
    ),
    BoundaryFamily(
        "bnd_request_refund_evl",
        "request_refund",
        "evaluation",
        "supported_12_domain",
        (
            "Initiate a payout reversal claim for the order I cancelled yesterday.",
        ),
    ),
    BoundaryFamily(
        "bnd_human_agent_trn",
        "human_agent",
        "train",
        "supported_12_domain",
        (
            "Transfer this conversation to a human support specialist instead of automated replies.",
            "Put a real customer representative or floor supervisor on the chat now.",
        ),
    ),
    BoundaryFamily(
        "bnd_human_agent_cal",
        "human_agent",
        "calibration",
        "supported_12_domain",
        (
            "Connect me directly with a live person to handle this dispute.",
        ),
    ),
    BoundaryFamily(
        "bnd_human_agent_evl",
        "human_agent",
        "evaluation",
        "supported_12_domain",
        (
            "I require a live human advisor to step in rather than an automated bot.",
        ),
    ),
)

BOUNDARY_NEGATIVE_FAMILIES: Tuple[BoundaryFamily, ...] = (
    BoundaryFamily(
        "bnd_neg_multi_trn",
        "out_of_scope",
        "train",
        "compound_multi_intent",
        (
            "Check my shipping costs to Da Nang and simultaneously delete my saved credit card.",
            "What is the return policy on electronics and can you also reset my login password?",
            "Void order ORD-8812 and generate a VAT company invoice for last month's order.",
            "Tell me the delivery lead time plus explain how to open a seller merchant account.",
            "My refund has not landed yet and the mobile app keeps freezing at checkout.",
            "Track order ORD-3310 and also swap the blue shirt in my other parcel to size M.",
            "I want to claim a reimbursement on my damaged kettle and connect with a human supervisor.",
            "How many days for standard returns, and can I switch payment from COD to Mastercard?",
            "Find where my courier parcel is right now and tell me Sunday mall branch hours.",
            "Explain your money-back eligibility rules and transfer me to billing support to fix a double charge.",
        ),
    ),
    BoundaryFamily(
        "bnd_neg_multi_cal",
        "out_of_scope",
        "calibration",
        "compound_multi_intent",
        (
            "Explain your refund rules and also close my customer profile permanently.",
            "Stop order ORD-9102 before dispatch and tell me weekend flagship branch hours.",
        ),
    ),
    BoundaryFamily(
        "bnd_neg_multi_evl",
        "out_of_scope",
        "evaluation",
        "compound_multi_intent",
        (
            "Trace my parcel status and also send me a copy of last quarter's VAT invoice.",
            "What do express shipping fees cost and can I redeem a store gift voucher?",
        ),
    ),
    BoundaryFamily(
        "bnd_neg_homonym_trn",
        "out_of_scope",
        "train",
        "off_domain_homonym",
        (
            "Where do taxpayers file annual federal income tax returns online this spring?",
            "Can passengers exchange an economy airline ticket for business class at the gate?",
            "How do I cancel a municipal water utility autopay and gym contract?",
            "Do commercial landlords refund security deposits within two weeks of lease end?",
            "Steps to change my home wireless modem admin passphrase?",
            "Explain compound interest differences between treasury notes and high-yield index funds.",
            "Which hiking boots handle muddy granite switchbacks in northern national parks?",
            "What vaccination certificate rules apply when flying into Singapore next quarter?",
            "Compare Python asyncio event loops against Go goroutine scheduling overhead.",
            "How many grams of protein per kilogram support marathon endurance recovery?",
        ),
    ),
    BoundaryFamily(
        "bnd_neg_homonym_cal",
        "out_of_scope",
        "calibration",
        "off_domain_homonym",
        (
            "How do freelancers submit quarterly state tax return forms before April?",
            "Can hotel guests cancel a resort booking without losing their deposit?",
        ),
    ),
    BoundaryFamily(
        "bnd_neg_homonym_evl",
        "out_of_scope",
        "evaluation",
        "off_domain_homonym",
        (
            "What forms are required to amend a federal tax return deduction?",
            "How do I freeze a health club membership during summer travel?",
        ),
    ),
    BoundaryFamily(
        "bnd_neg_vague_trn",
        "out_of_scope",
        "train",
        "underspecified_ambiguous",
        (
            "assist me",
            "good afternoon",
            "checking status",
            "problem here",
        ),
    ),
    BoundaryFamily(
        "bnd_neg_vague_cal",
        "out_of_scope",
        "calibration",
        "underspecified_ambiguous",
        (
            "need assistance now",
            "just checking",
        ),
    ),
    BoundaryFamily(
        "bnd_neg_vague_evl",
        "out_of_scope",
        "evaluation",
        "underspecified_ambiguous",
        (
            "anybody listening",
            "having trouble",
        ),
    ),
)


def apply_realistic_noise(text: str, rng: random.Random) -> str:
    """Apply deterministic realistic typo/casing/shorthand noise ONLY on training copies."""
    mode = rng.choice(("drop_vowel", "swap_adj", "lowercase_strip_punct", "shorthand"))
    out = str(text)
    words = out.split()
    if mode == "lowercase_strip_punct":
        return "".join(ch for ch in out.lower() if ch.isalnum() or ch.isspace()).strip()
    if mode == "shorthand":
        rep = {
            "please": "pls",
            "order": "ordr",
            "refund": "rfnd",
            "return": "rtrn",
            "delivery": "dlvry",
            "shipping": "shippng",
            "payment": "pymnt",
            "where": "whre",
            "cancel": "cncl",
        }
        new_words = [rep.get(w.lower(), w) if rng.random() < 0.65 else w for w in words]
        return " ".join(new_words)
    if len(words) >= 3:
        cand_idxs = [i for i, w in enumerate(words) if len(w) >= 5 and w.isalpha()]
        if cand_idxs:
            idx = rng.choice(cand_idxs)
            w = words[idx]
            if mode == "drop_vowel":
                pos = rng.randint(1, len(w) - 2)
                words[idx] = w[:pos] + w[pos + 1 :]
            else:
                pos = rng.randint(1, len(w) - 3)
                words[idx] = w[:pos] + w[pos + 1] + w[pos] + w[pos + 2 :]
            return " ".join(words)
    return out.lower()


def generate_boundary_records() -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Generate closure + boundary positive/negative records with strict split partitions."""
    pos_records = list(generate_closure_positive_records())
    neg_records = list(generate_closure_negative_records())

    for fam in BOUNDARY_POSITIVE_FAMILIES:
        bucket = "supported_12" if fam.intent in SUPPORTED_12_INTENTS else "escalated_34"
        for idx, text in enumerate(fam.patterns):
            digest = hashlib.sha256(f"{fam.template_group_id}:{idx}:{text}".encode("utf-8")).hexdigest()[:12]
            pos_records.append(
                {
                    "sample_id": f"{fam.template_group_id}_{idx}_{digest}",
                    "instruction": text,
                    "text": text,
                    "intent": fam.intent,
                    "true_intent": fam.intent,
                    "intent_bucket": bucket,
                    "template_group_id": fam.template_group_id,
                    "group_id": fam.template_group_id,
                    "partition": fam.partition,
                    "category": fam.category,
                    "source": "boundary_positive_20261113",
                    "selective_label": 1,
                }
            )

    for fam in BOUNDARY_NEGATIVE_FAMILIES:
        for idx, text in enumerate(fam.patterns):
            digest = hashlib.sha256(f"{fam.template_group_id}:{idx}:{text}".encode("utf-8")).hexdigest()[:12]
            neg_records.append(
                {
                    "sample_id": f"{fam.template_group_id}_{idx}_{digest}",
                    "instruction": text,
                    "text": text,
                    "intent": "out_of_scope",
                    "category": fam.category,
                    "template_group_id": fam.template_group_id,
                    "group_id": fam.template_group_id,
                    "partition": fam.partition,
                    "source": "boundary_negative_20261113",
                    "selective_label": 0,
                }
            )

    # Normalize compatible fields on closure records too
    for rec in pos_records:
        rec.setdefault("text", rec["instruction"])
        rec.setdefault("true_intent", rec["intent"])
        rec.setdefault("group_id", rec["template_group_id"])
    for rec in neg_records:
        rec.setdefault("text", rec["instruction"])
        rec.setdefault("group_id", rec["template_group_id"])
    return pos_records, neg_records


def audit_and_export_boundary_datasets(
    output_dir: Path,
    *,
    repo_root: Path = REPO_ROOT,
) -> Dict[str, Any]:
    """Audit split isolation & zero gold contamination, then lock split files + SHA-256 manifest."""
    pos_records, neg_records = generate_boundary_records()
    all_records = pos_records + neg_records

    by_part: Dict[str, List[Tuple[str, str]]] = {"train": [], "calibration": [], "evaluation": []}
    groups_by_part: Dict[str, set[str]] = {"train": set(), "calibration": set(), "evaluation": set()}
    seen_norm: Dict[str, str] = {}
    exact_dups: List[Dict[str, str]] = []

    for rec in all_records:
        p = rec["partition"]
        by_part[p].append((rec["sample_id"], rec["instruction"]))
        groups_by_part[p].add(rec["template_group_id"])
        norm = _normalize_text(rec["instruction"])
        if norm in seen_norm:
            exact_dups.append({"first_id": seen_norm[norm], "dup_id": rec["sample_id"], "text": rec["instruction"]})
        else:
            seen_norm[norm] = rec["sample_id"]

    # Boundary-specific new records must also be disjoint from prior domain/selective templates
    new_only = [r for r in all_records if r["source"].startswith("boundary_")]
    prior_all = (
        generate_grouped_domain_records()
        + generate_grouped_negative_records()
        + generate_selective_positive_records()
        + generate_selective_negative_records()
    )
    prior_rows = [(r["sample_id"], r["instruction"]) for r in prior_all]
    new_rows = [(r["sample_id"], r["instruction"]) for r in new_only]
    bench_rows = _load_frozen_benchmark_texts(repo_root)
    all_rows = [(r["sample_id"], r["instruction"]) for r in all_records]

    checks = {
        "train_vs_calibration": _pairwise_max_overlap(by_part["train"], by_part["calibration"]),
        "train_vs_evaluation": _pairwise_max_overlap(by_part["train"], by_part["evaluation"]),
        "calibration_vs_evaluation": _pairwise_max_overlap(by_part["calibration"], by_part["evaluation"]),
        "boundary_new_vs_prior": _pairwise_max_overlap(new_rows, prior_rows),
        "all_vs_frozen_benchmarks": _pairwise_max_overlap(all_rows, bench_rows),
    }

    group_disjoint = (
        groups_by_part["train"].isdisjoint(groups_by_part["calibration"])
        and groups_by_part["train"].isdisjoint(groups_by_part["evaluation"])
        and groups_by_part["calibration"].isdisjoint(groups_by_part["evaluation"])
    )

    passed = group_disjoint and len(exact_dups) == 0
    for name, c in checks.items():
        if c["exact_matches"]:
            passed = False
        if name == "all_vs_frozen_benchmarks":
            if c["max_token_f1"] >= 0.65 or c["max_jaccard"] >= 0.60 or c["max_word_tfidf_cosine"] >= 0.65:
                passed = False
        else:
            if c["max_token_f1"] >= 0.65 or c["max_jaccard"] >= 0.60 or c["max_word_tfidf_cosine"] >= 0.65:
                passed = False

    if not passed:
        raise RuntimeError(f"Boundary curriculum audit failed: group_disjoint={group_disjoint}, exact_dups={exact_dups}, checks={json.dumps(checks, indent=2)}")

    output_dir.mkdir(parents=True, exist_ok=True)
    splits: Dict[str, str] = {}
    counts: Dict[str, int] = {}
    for prefix, src in (("pos", pos_records), ("neg", neg_records)):
        for part in ("train", "calibration", "evaluation"):
            subset = [r for r in src if r["partition"] == part]
            p = output_dir / f"boundary_{prefix}_{part}.jsonl"
            p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in subset) + "\n", encoding="utf-8")
            key = f"{prefix}_{part}"
            splits[key] = hashlib.sha256(p.read_bytes()).hexdigest().lower()
            counts[key] = len(subset)

    manifest = {
        "schema_version": "boundary_curriculum_split.v1",
        "group_disjoint": group_disjoint,
        "counts": counts,
        "file_sha256": splits,
        "overlap_audit": checks,
    }
    (output_dir / "split_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest
