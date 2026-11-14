"""Generate independent local app-specific retrieval gold benchmark for SupportIQ active policies.

Applies coordinator review feedback:
- edit_order (ans17/18) moved to optional_out_of_product slice (excluded from core product Recall denominator)
- OOD intent in ood05 marked as null / out_of_scope (not claiming fake ML 46 label)
- conf01/02 marked as not_executed_in_active_release (no source conflict in active release)
- ans12 notes updated to distinguish Transferred to Bank from Refund Succeeded
- status=pending with KB and release hashes
"""

import hashlib
import json
from pathlib import Path


CASES = [
    # 1. POL-RET-001 (v2.0)
    {
        "id": "app-gold-ans-01",
        "query": "What is the return time window for products sold by Tiki Trading versus marketplace partner sellers?",
        "intent": "return_policy",
        "slice": "supported",
        "is_answerable": True,
        "is_product_12_scope": True,
        "gold_doc_ids": ["POL-RET-001:2.0"],
        "expected_action": "draft",
        "as_of": "2026-06-15T10:00:00Z",
        "notes": "Covers Tiki Trading 30-day and marketplace 7-day return window from delivery date."
    },
    {
        "id": "app-gold-ans-02",
        "query": "What condition must returned items be in regarding security seals, accessories, and packaging?",
        "intent": "return_policy",
        "slice": "supported",
        "is_answerable": True,
        "is_product_12_scope": True,
        "gold_doc_ids": ["POL-RET-001:2.0"],
        "expected_action": "draft",
        "as_of": "2026-06-15T10:00:00Z",
        "notes": "Covers intact security seals, complete packaging, accessories, gifts, no signs of usage."
    },

    # 2. POL-RET-002 (v2.0)
    {
        "id": "app-gold-ans-03",
        "query": "How do I create a return or exchange request on the Tiki app and upload defect photos?",
        "intent": "return_product",
        "slice": "supported",
        "is_answerable": True,
        "is_product_12_scope": True,
        "gold_doc_ids": ["POL-RET-002:2.0"],
        "expected_action": "draft",
        "as_of": "2026-06-15T10:00:00Z",
        "notes": "Covers Account > Order Management > Delivered > Request Return/Exchange with 3-5 photos or video."
    },
    {
        "id": "app-gold-ans-04",
        "query": "Will shipping couriers pick up my return package from my address for free or do I drop it off?",
        "intent": "return_product",
        "slice": "supported",
        "is_answerable": True,
        "is_product_12_scope": True,
        "gold_doc_ids": ["POL-RET-002:2.0"],
        "expected_action": "draft",
        "as_of": "2026-06-15T10:00:00Z",
        "notes": "Covers free doorstep pickup within 1-2 business days or partner post office drop-off."
    },

    # 3. POL-RET-003 (v2.0)
    {
        "id": "app-gold-ans-05",
        "query": "Which product categories do not support returns due to change of mind or personal preference on Tiki?",
        "intent": "return_policy",
        "slice": "supported",
        "is_answerable": True,
        "is_product_12_scope": True,
        "gold_doc_ids": ["POL-RET-003:2.0"],
        "expected_action": "draft",
        "as_of": "2026-06-15T10:00:00Z",
        "notes": "Covers restricted categories: underwear, swimwear, cosmetics/chemicals with unsealed packaging, fresh groceries, top-up cards."
    },
    {
        "id": "app-gold-ans-06",
        "query": "Can I return opened or unsealed cosmetics if I simply changed my mind?",
        "intent": "return_policy",
        "slice": "supported",
        "is_answerable": True,
        "is_product_12_scope": True,
        "gold_doc_ids": ["POL-RET-003:2.0"],
        "expected_action": "draft",
        "as_of": "2026-06-15T10:00:00Z",
        "notes": "Explicitly covers cosmetics with unsealed protective packaging excluded from change-of-mind return."
    },

    # 4. POL-REFUND-001 (v1.0)
    {
        "id": "app-gold-ans-07",
        "query": "What are the rules and requirements for a refund to be approved after cancellation or warehouse inspection?",
        "intent": "refund_policy",
        "slice": "supported",
        "is_answerable": True,
        "is_product_12_scope": True,
        "gold_doc_ids": ["POL-REFUND-001:1.0"],
        "expected_action": "draft",
        "as_of": "2026-06-15T10:00:00Z",
        "notes": "Covers refund reconciliation by authorized personnel after pre-dispatch cancel or warehouse inspection."
    },
    {
        "id": "app-gold-ans-08",
        "query": "Are original shipping fees refundable if I return an item based on personal preference?",
        "intent": "refund_policy",
        "slice": "supported",
        "is_answerable": True,
        "is_product_12_scope": True,
        "gold_doc_ids": ["POL-REFUND-001:1.0"],
        "expected_action": "draft",
        "as_of": "2026-06-15T10:00:00Z",
        "notes": "Covers original shipping fees non-refundable if return reason is personal preference."
    },

    # 5. POL-REFUND-002 (v2.0)
    {
        "id": "app-gold-ans-09",
        "query": "How long does a refund take to be credited to linked e-wallets like MoMo or ZaloPay?",
        "intent": "refund_policy",
        "slice": "supported",
        "is_answerable": True,
        "is_product_12_scope": True,
        "gold_doc_ids": ["POL-REFUND-002:2.0"],
        "expected_action": "draft",
        "as_of": "2026-06-15T10:00:00Z",
        "notes": "Covers e-wallet refund timeline of 1-2 business days."
    },
    {
        "id": "app-gold-ans-10",
        "query": "What is the refund timeline for domestic Napas ATM cards versus international Visa or Mastercard credit cards?",
        "intent": "refund_policy",
        "slice": "supported",
        "is_answerable": True,
        "is_product_12_scope": True,
        "gold_doc_ids": ["POL-REFUND-002:2.0"],
        "expected_action": "draft",
        "as_of": "2026-06-15T10:00:00Z",
        "notes": "Covers domestic ATM 3-5 business days and international cards 7-15 business days."
    },

    # 6. POL-REFUND-007 (v1.0)
    {
        "id": "app-gold-ans-11",
        "query": "Where on the Tiki app can I check the progress and history of my refund?",
        "intent": "refund_status",
        "slice": "supported",
        "is_answerable": True,
        "is_product_12_scope": True,
        "gold_doc_ids": ["POL-REFUND-007:1.0"],
        "expected_action": "draft",
        "as_of": "2026-06-15T10:00:00Z",
        "notes": "Covers Account Details > Return & Refund Management."
    },
    {
        "id": "app-gold-ans-12",
        "query": "What does Transferred to Bank refund status mean on Tiki and how can I trace it?",
        "intent": "refund_status",
        "slice": "supported",
        "is_answerable": True,
        "is_product_12_scope": True,
        "gold_doc_ids": ["POL-REFUND-007:1.0"],
        "expected_action": "draft",
        "as_of": "2026-06-15T10:00:00Z",
        "notes": "Covers Transferred to Bank status (funds dispatched from Tiki, awaiting bank credit); note that bank transaction tracing reference code is provided upon Refund Succeeded."
    },

    # 7. POL-ORD-001 (v1.0)
    {
        "id": "app-gold-ans-13",
        "query": "How can I check the delivery journey and transit hub status of my Tiki order on the app?",
        "intent": "track_order",
        "slice": "supported",
        "is_answerable": True,
        "is_product_12_scope": True,
        "gold_doc_ids": ["POL-ORD-001:1.0"],
        "expected_action": "draft",
        "as_of": "2026-06-15T10:00:00Z",
        "notes": "Covers My Orders, real-time tracking code, and transit hubs."
    },
    {
        "id": "app-gold-ans-14",
        "query": "What does the In Transit order status mean on the Tiki tracking screen?",
        "intent": "track_order",
        "slice": "supported",
        "is_answerable": True,
        "is_product_12_scope": True,
        "gold_doc_ids": ["POL-ORD-001:1.0"],
        "expected_action": "draft",
        "as_of": "2026-06-15T10:00:00Z",
        "notes": "Covers courier delivering with real-time tracking code provided."
    },

    # 8. POL-ORD-002 (v1.0)
    {
        "id": "app-gold-ans-15",
        "query": "Can I cancel an order that is still in processing or awaiting packing on the Tiki app?",
        "intent": "cancel_order",
        "slice": "supported",
        "is_answerable": True,
        "is_product_12_scope": True,
        "gold_doc_ids": ["POL-ORD-002:1.0"],
        "expected_action": "draft",
        "as_of": "2026-06-15T10:00:00Z",
        "notes": "Covers direct cancel button enabled before order is handed to carrier."
    },
    {
        "id": "app-gold-ans-16",
        "query": "Can I cancel an order that is already in transit with the courier?",
        "intent": "cancel_order",
        "slice": "supported",
        "is_answerable": True,
        "is_product_12_scope": True,
        "gold_doc_ids": ["POL-ORD-002:1.0"],
        "expected_action": "draft",
        "as_of": "2026-06-15T10:00:00Z",
        "notes": "Covers direct cancellation disabled in transit; reject package upon courier contact."
    },

    # 9. POL-ORD-003 (v1.0) — Moved to optional_out_of_product slice (edit_order is outside supported 12 and ML 46)
    {
        "id": "app-gold-ans-17",
        "query": "Can I change my delivery address or phone number after placing an order on Tiki?",
        "intent": "edit_order",
        "slice": "optional_out_of_product",
        "is_answerable": True,
        "is_product_12_scope": False,
        "gold_doc_ids": ["POL-ORD-003:1.0"],
        "expected_action": "draft",
        "as_of": "2026-06-15T10:00:00Z",
        "notes": "Covers POL-ORD-003. edit_order is outside the supported 12 intents and ML 46 labelset; classified as optional retrieval-only out-of-product slice and excluded from core product Recall denominator."
    },
    {
        "id": "app-gold-ans-18",
        "query": "What should I do to change delivery location if the order has already been handed over to courier?",
        "intent": "edit_order",
        "slice": "optional_out_of_product",
        "is_answerable": True,
        "is_product_12_scope": False,
        "gold_doc_ids": ["POL-ORD-003:1.0"],
        "expected_action": "draft",
        "as_of": "2026-06-15T10:00:00Z",
        "notes": "Covers POL-ORD-003. edit_order is outside the supported 12 intents and ML 46 labelset; classified as optional retrieval-only out-of-product slice and excluded from core product Recall denominator."
    },

    # 10. POL-SHIP-001 (v1.0)
    {
        "id": "app-gold-ans-19",
        "query": "How fast is TikiNOW 2-hour express delivery and which urban areas are supported?",
        "intent": "delivery_time",
        "slice": "supported",
        "is_answerable": True,
        "is_product_12_scope": True,
        "gold_doc_ids": ["POL-SHIP-001:1.0"],
        "expected_action": "draft",
        "as_of": "2026-06-15T10:00:00Z",
        "notes": "Covers TikiNOW 2-hour delivery in inner districts of Hanoi, HCMC, Da Nang."
    },
    {
        "id": "app-gold-ans-20",
        "query": "What are the delivery timelines for Standard Delivery across inter-provincial orders or rural districts?",
        "intent": "delivery_time",
        "slice": "supported",
        "is_answerable": True,
        "is_product_12_scope": True,
        "gold_doc_ids": ["POL-SHIP-001:1.0"],
        "expected_action": "draft",
        "as_of": "2026-06-15T10:00:00Z",
        "notes": "Covers Standard Delivery 3-5 business days for inter-provincial orders."
    },

    # 11. POL-SHIP-002 (v1.0)
    {
        "id": "app-gold-ans-21",
        "query": "What is the shipping fee schedule for intra-city and inter-provincial deliveries on Tiki?",
        "intent": "shipping_costs",
        "slice": "supported",
        "is_answerable": True,
        "is_product_12_scope": True,
        "gold_doc_ids": ["POL-SHIP-002:1.0"],
        "expected_action": "draft",
        "as_of": "2026-06-15T10:00:00Z",
        "notes": "Covers intra-city base fee 18,000-25,000 VND and inter-provincial 35,000-55,000 VND."
    },
    {
        "id": "app-gold-ans-22",
        "query": "How do Freeship TikiPRO discount vouchers apply to reduce shipping charges?",
        "intent": "shipping_costs",
        "slice": "supported",
        "is_answerable": True,
        "is_product_12_scope": True,
        "gold_doc_ids": ["POL-SHIP-002:1.0"],
        "expected_action": "draft",
        "as_of": "2026-06-15T10:00:00Z",
        "notes": "Covers orders meeting minimum 149,000 VND getting 30,000-70,000 VND discount."
    },

    # 12. POL-SHIP-004 (v1.0)
    {
        "id": "app-gold-ans-23",
        "query": "The courier marked my order as Successfully Delivered but I have not received the parcel.",
        "intent": "delivery_issue",
        "slice": "supported",
        "is_answerable": True,
        "is_product_12_scope": True,
        "gold_doc_ids": ["POL-SHIP-004:1.0"],
        "expected_action": "draft",
        "as_of": "2026-06-15T10:00:00Z",
        "notes": "Covers discrepant status complaint within 24-48 hours via hotline 1900 6035 and GPS verification."
    },
    {
        "id": "app-gold-ans-24",
        "query": "What should I do if my package is delayed and lost past the estimated delivery date?",
        "intent": "delivery_issue",
        "slice": "supported",
        "is_answerable": True,
        "is_product_12_scope": True,
        "gold_doc_ids": ["POL-SHIP-004:1.0"],
        "expected_action": "draft",
        "as_of": "2026-06-15T10:00:00Z",
        "notes": "Covers delayed package handling, GPS hub checks, replacement or 100% refund for lost parcel."
    },

    # 13. POL-PAY-001 (v1.0)
    {
        "id": "app-gold-ans-25",
        "query": "My bank account was debited but the Tiki order is still showing Awaiting Payment.",
        "intent": "payment_issue",
        "slice": "supported",
        "is_answerable": True,
        "is_product_12_scope": True,
        "gold_doc_ids": ["POL-PAY-001:1.0"],
        "expected_action": "draft",
        "as_of": "2026-06-15T10:00:00Z",
        "notes": "Covers payment gateway latency, auto-reconciliation within 15-30m, and auto-refund in 24-72h."
    },
    {
        "id": "app-gold-ans-26",
        "query": "How long does Tiki take to automatically reconcile a pending payment with the bank gateway?",
        "intent": "payment_issue",
        "slice": "supported",
        "is_answerable": True,
        "is_product_12_scope": True,
        "gold_doc_ids": ["POL-PAY-001:1.0"],
        "expected_action": "draft",
        "as_of": "2026-06-15T10:00:00Z",
        "notes": "Covers automatic gateway reconciliation within 15-30 minutes."
    },

    # 14. POL-PAY-004 (v1.0)
    {
        "id": "app-gold-ans-27",
        "query": "I was charged twice on my credit card for the exact same Tiki order code.",
        "intent": "payment_issue",
        "slice": "supported",
        "is_answerable": True,
        "is_product_12_scope": True,
        "gold_doc_ids": ["POL-PAY-004:1.0"],
        "expected_action": "draft",
        "as_of": "2026-06-15T10:00:00Z",
        "notes": "Covers double deduction refund within 48 business hours during end-of-day settlement."
    },
    {
        "id": "app-gold-ans-28",
        "query": "How does Tiki handle duplicate deductions on e-wallets caused by network congestion?",
        "intent": "payment_issue",
        "slice": "supported",
        "is_answerable": True,
        "is_product_12_scope": True,
        "gold_doc_ids": ["POL-PAY-004:1.0"],
        "expected_action": "draft",
        "as_of": "2026-06-15T10:00:00Z",
        "notes": "Covers partner bank end-of-day settlement and automated duplicate refund in 48 business hours."
    },

    # 15. Cross-policy queries
    {
        "id": "app-gold-ans-29",
        "query": "How do I request a refund and what timeline should I expect after my return is accepted?",
        "intent": "request_refund",
        "slice": "supported",
        "is_answerable": True,
        "is_product_12_scope": True,
        "gold_doc_ids": ["POL-REFUND-001:1.0", "POL-REFUND-002:2.0"],
        "expected_action": "draft",
        "as_of": "2026-06-15T10:00:00Z",
        "notes": "Covers refund reconciliation conditions and payment method receipt timelines."
    },
    {
        "id": "app-gold-ans-30",
        "query": "When will I receive my money back after successfully canceling a prepaid order?",
        "intent": "request_refund",
        "slice": "supported",
        "is_answerable": True,
        "is_product_12_scope": True,
        "gold_doc_ids": ["POL-ORD-002:1.0", "POL-REFUND-002:2.0"],
        "expected_action": "draft",
        "as_of": "2026-06-15T10:00:00Z",
        "notes": "Covers prepaid cancellation automatic refund rules and payment method crediting timelines."
    },
    {
        "id": "app-gold-ans-31",
        "query": "Can I exchange an item purchased from a marketplace partner seller on Tiki?",
        "intent": "return_product",
        "slice": "supported",
        "is_answerable": True,
        "is_product_12_scope": True,
        "gold_doc_ids": ["POL-RET-001:2.0"],
        "expected_action": "draft",
        "as_of": "2026-06-15T10:00:00Z",
        "notes": "Covers marketplace partner 7-day exchange window."
    },
    {
        "id": "app-gold-ans-32",
        "query": "What photo or video evidence must I provide when tapping Request Return/Exchange on the app?",
        "intent": "return_product",
        "slice": "supported",
        "is_answerable": True,
        "is_product_12_scope": True,
        "gold_doc_ids": ["POL-RET-002:2.0"],
        "expected_action": "draft",
        "as_of": "2026-06-15T10:00:00Z",
        "notes": "Covers 3-5 clear photos or video demonstrating product defect on Tiki app."
    },
    {
        "id": "app-gold-ans-33",
        "query": "Is swimwear or underwear eligible for return if I change my mind?",
        "intent": "return_policy",
        "slice": "supported",
        "is_answerable": True,
        "is_product_12_scope": True,
        "gold_doc_ids": ["POL-RET-003:2.0"],
        "expected_action": "draft",
        "as_of": "2026-06-15T10:00:00Z",
        "notes": "Covers swimwear and underwear explicitly non-returnable under change of mind."
    },

    # --- UNANSWERABLE / ESCALATION / ROBUSTNESS SLICES ---
    # Human Agent slice (3 cases)
    {
        "id": "app-gold-ha-01",
        "query": "I want to speak with a human agent immediately.",
        "intent": "human_agent",
        "slice": "human_agent",
        "is_answerable": False,
        "is_product_12_scope": True,
        "gold_doc_ids": [],
        "expected_action": "escalate",
        "as_of": "2026-06-15T10:00:00Z",
        "notes": "Human agent request; must escalate, no KB document expected."
    },
    {
        "id": "app-gold-ha-02",
        "query": "Please transfer me to a live customer support representative.",
        "intent": "human_agent",
        "slice": "human_agent",
        "is_answerable": False,
        "is_product_12_scope": True,
        "gold_doc_ids": [],
        "expected_action": "escalate",
        "as_of": "2026-06-15T10:00:00Z",
        "notes": "Human agent request; must escalate, no KB document expected."
    },
    {
        "id": "app-gold-ha-03",
        "query": "Can I talk to a real person from customer care?",
        "intent": "human_agent",
        "slice": "human_agent",
        "is_answerable": False,
        "is_product_12_scope": True,
        "gold_doc_ids": [],
        "expected_action": "escalate",
        "as_of": "2026-06-15T10:00:00Z",
        "notes": "Human agent request; must escalate, no KB document expected."
    },

    # Expired slice (3 cases, as_of after 2026-12-31)
    {
        "id": "app-gold-exp-01",
        "query": "What is the standard product return window on Tiki?",
        "intent": "return_policy",
        "slice": "expired",
        "is_answerable": False,
        "is_product_12_scope": False,
        "gold_doc_ids": [],
        "expected_action": "abstain",
        "as_of": "2027-03-01T00:00:00Z",
        "notes": "Evaluated after 2026 validity window; temporal filter must reject expired policies."
    },
    {
        "id": "app-gold-exp-02",
        "query": "How many business days does a refund take for e-wallets?",
        "intent": "refund_policy",
        "slice": "expired",
        "is_answerable": False,
        "is_product_12_scope": False,
        "gold_doc_ids": [],
        "expected_action": "abstain",
        "as_of": "2027-03-01T00:00:00Z",
        "notes": "Evaluated after 2026 validity window; temporal filter must reject expired policies."
    },
    {
        "id": "app-gold-exp-03",
        "query": "What are the delivery timelines for TikiNOW 2-hour express shipping?",
        "intent": "delivery_time",
        "slice": "expired",
        "is_answerable": False,
        "is_product_12_scope": False,
        "gold_doc_ids": [],
        "expected_action": "abstain",
        "as_of": "2027-03-01T00:00:00Z",
        "notes": "Evaluated after 2026 validity window; temporal filter must reject expired policies."
    },

    # Conflict slice (2 cases) — Marked as not_executed_in_active_release as active release has zero source conflicts
    {
        "id": "app-gold-conf-01",
        "query": "What is the return window under conflicting store and marketplace terms?",
        "intent": "return_policy",
        "slice": "conflict",
        "is_answerable": False,
        "is_product_12_scope": False,
        "execution_status": "not_executed_in_active_release",
        "gold_doc_ids": [],
        "expected_action": "abstain",
        "as_of": "2026-06-15T10:00:00Z",
        "notes": "Active approved KB release contains mutually coherent versioned policies with zero contradictory rules. Conflicting policy detection is evaluated in isolated synthetic fixture tests, not by query string keywords."
    },
    {
        "id": "app-gold-conf-02",
        "query": "Which contradictory refund timeline applies to international cards?",
        "intent": "refund_policy",
        "slice": "conflict",
        "is_answerable": False,
        "is_product_12_scope": False,
        "execution_status": "not_executed_in_active_release",
        "gold_doc_ids": [],
        "expected_action": "abstain",
        "as_of": "2026-06-15T10:00:00Z",
        "notes": "Active approved KB release contains mutually coherent versioned policies with zero contradictory rules. Conflicting policy detection is evaluated in isolated synthetic fixture tests, not by query string keywords."
    },

    # OOD (Out-of-Domain) slice (5 cases)
    {
        "id": "app-gold-ood-01",
        "query": "How can I register as a new merchant seller on Tiki marketplace?",
        "intent": "open_account",
        "slice": "ood",
        "is_answerable": False,
        "is_product_12_scope": False,
        "gold_doc_ids": [],
        "expected_action": "abstain",
        "as_of": "2026-06-15T10:00:00Z",
        "notes": "Out-of-scope intent; system must abstain with out_of_scope_intent or no_valid_document."
    },
    {
        "id": "app-gold-ood-02",
        "query": "I forgot my password and need to recover my login credentials.",
        "intent": "recover_password",
        "slice": "ood",
        "is_answerable": False,
        "is_product_12_scope": False,
        "gold_doc_ids": [],
        "expected_action": "abstain",
        "as_of": "2026-06-15T10:00:00Z",
        "notes": "Out-of-scope intent; system must abstain."
    },
    {
        "id": "app-gold-ood-03",
        "query": "Where is the nearest physical Tiki retail outlet in Da Nang?",
        "intent": "store_location",
        "slice": "ood",
        "is_answerable": False,
        "is_product_12_scope": False,
        "gold_doc_ids": [],
        "expected_action": "abstain",
        "as_of": "2026-06-15T10:00:00Z",
        "notes": "Out-of-scope intent; system must abstain."
    },
    {
        "id": "app-gold-ood-04",
        "query": "I want to submit an idea for a new mobile app feature.",
        "intent": "submit_product_idea",
        "slice": "ood",
        "is_answerable": False,
        "is_product_12_scope": False,
        "gold_doc_ids": [],
        "expected_action": "abstain",
        "as_of": "2026-06-15T10:00:00Z",
        "notes": "Out-of-scope intent; system must abstain."
    },
    {
        "id": "app-gold-ood-05",
        "query": "How do I apply for an open software engineering job at Tiki corporate?",
        "intent": "out_of_scope",
        "slice": "ood",
        "is_answerable": False,
        "is_product_12_scope": False,
        "gold_doc_ids": [],
        "expected_action": "abstain",
        "as_of": "2026-06-15T10:00:00Z",
        "notes": "Out-of-scope inquiry; not an ML 46 class, no valid documents in policy KB."
    },
]


def main():
    root = Path(__file__).resolve().parents[1]
    out_dir = root / "data/benchmarks"
    out_dir.mkdir(parents=True, exist_ok=True)
    gold_file = out_dir / "app_retrieval_gold_v2.json"
    manifest_file = out_dir / "app_retrieval_gold_manifest.json"

    kb_path = root / "data/knowledge/approved_kb.v2.json"
    release_path = root / "apps/ai_service/kb-release.json"

    kb_sha256 = hashlib.sha256(kb_path.read_bytes()).hexdigest()
    release_sha256 = hashlib.sha256(release_path.read_bytes()).hexdigest()

    content_bytes = (json.dumps(CASES, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    gold_file.write_bytes(content_bytes)

    gold_sha256 = hashlib.sha256(content_bytes).hexdigest()

    # Split counts
    product_12_answerable = sum(1 for c in CASES if c.get("is_product_12_scope") and c["is_answerable"])
    optional_out_of_product = sum(1 for c in CASES if c["slice"] == "optional_out_of_product")
    total_answerable = sum(1 for c in CASES if c["is_answerable"])
    total_unanswerable = sum(1 for c in CASES if not c["is_answerable"])

    manifest = {
        "benchmark_id": "supportiq-app-retrieval-gold-v2",
        "version": "2.1.0",
        "status": "pending",
        "approval": "pending_coordinator_review",
        "created_at": "2026-11-12T11:40:00Z",
        "provenance": {
            "source": "data/knowledge/approved_kb.v2.json via apps/ai_service/kb-release.json",
            "coverage": "All 14 active POL-* documents with full 12 product intents, human_agent, expired, conflict, and OOD slices",
            "approval_note": "Delegated stakeholder review pending; no external instructor or cross-group approval claimed",
            "kb_source_sha256": kb_sha256,
            "kb_release_sha256": release_sha256,
        },
        "target_release": "current-policies-v1",
        "file": "data/benchmarks/app_retrieval_gold_v2.json",
        "sha256": gold_sha256,
        "total_cases": len(CASES),
        "slice_counts": {
            "supported_12_product_answerable": product_12_answerable,
            "optional_out_of_product": optional_out_of_product,
            "human_agent_escalation": sum(1 for c in CASES if c["slice"] == "human_agent"),
            "expired_temporal_rejection": sum(1 for c in CASES if c["slice"] == "expired"),
            "conflicting_policies": sum(1 for c in CASES if c["slice"] == "conflict"),
            "out_of_domain": sum(1 for c in CASES if c["slice"] == "ood"),
        },
        "core_product_recall_denominator": product_12_answerable,
        "total_answerable": total_answerable,
        "total_unanswerable": total_unanswerable,
    }

    manifest_bytes = (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    manifest_file.write_bytes(manifest_bytes)

    print(f"Generated {gold_file} ({len(CASES)} cases)")
    print(f"Generated {manifest_file}")
    print(f"SHA-256: {gold_sha256}")
    print(f"Core Supported 12 Product Answerable: {product_12_answerable}")
    print(f"Optional Out-of-Product Answerable: {optional_out_of_product}")
    print(f"Total Unanswerable: {total_unanswerable}")


if __name__ == "__main__":
    main()
