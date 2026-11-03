"""Shared utilities, constants, and ID generation for data preparation."""

from __future__ import annotations

import datetime
import hashlib
import json
import re
import unicodedata
from pathlib import Path
from typing import Any

import pandas as pd

# Standard Bitext taxonomy
STANDARD_CATEGORIES = frozenset([
    "CONTACT",
    "ACCOUNT",
    "APP_WEBSITE",
    "CART",
    "DELIVERY",
    "FEEDBACK",
    "ORDER",
    "PAYMENT",
    "PRODUCT",
    "RETURNS",
    "SALES",
    "STORE",
    "USER",
])

STANDARD_INTENTS = frozenset([
    # CONTACT
    "customer_service",
    "human_agent",
    # ACCOUNT
    "change_account",
    "close_account",
    "open_account",
    "order_history",
    "recover_password",
    # APP_WEBSITE
    "technical_issue",
    "use_app",
    # CART
    "add_product",
    "remove_product",
    # DELIVERY
    "damaged_delivery",
    "delivery_issue",
    "delivery_time",
    "missing_item",
    "shipping_costs",
    "track_delivery",
    "wrong_item",
    # FEEDBACK
    "submit_feedback",
    "submit_product_feedback",
    "submit_product_idea",
    # ORDER
    "cancel_order",
    "change_order",
    "request_invoice",
    "track_order",
    # PAYMENT
    "pay",
    "payment_issue",
    "payment_methods",
    # PRODUCT
    "availability",
    "availability_in_store",
    "availability_online",
    "exchange_product",
    "exchange_product_in_store",
    "product_information",
    "product_issue",
    # RETURNS
    "refund_policy",
    "refund_status",
    "request_refund",
    "return_policy",
    "return_product",
    "return_product_in_store",
    "return_product_online",
    # SALES
    "sales_period",
    # STORE
    "store_location",
    "store_opening_hours",
    # USER
    "request_right_to_rectification",
])

# 12 Core product intents defined in CHỦ ĐỀ 1
CORE_PRODUCT_INTENTS = frozenset([
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
])


def get_next_id(base_dir: Path | str, date_str: str | None = None) -> str:
    """Generate or auto-increment an ID in the format DD-MM-YYYY-stt.

    Args:
        base_dir: Base directory containing versioned folders.
        date_str: Optional fixed date string in DD-MM-YYYY format. If None, uses today's date.

    Returns:
        String ID formatted as DD-MM-YYYY-stt (e.g. '03-11-2026-00').
    """
    if date_str is None:
        today = datetime.date.today()
        prefix = f"{today.day:02d}-{today.month:02d}-{today.year:04d}"
    else:
        prefix = date_str

    base_path = Path(base_dir)
    pattern = re.compile(rf"^{re.escape(prefix)}-(\d{{2,}})$")

    highest_seq = -1
    if base_path.exists() and base_path.is_dir():
        for entry in base_path.iterdir():
            if entry.is_dir():
                match = pattern.match(entry.name)
                if match:
                    seq = int(match.group(1))
                    if seq > highest_seq:
                        highest_seq = seq

    next_seq = highest_seq + 1
    return f"{prefix}-{next_seq:02d}"


def compute_sha256(file_path: Path | str) -> str:
    """Compute uppercase SHA-256 hash of a file."""
    path = Path(file_path)
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest().upper()


def save_json(data: Any, file_path: Path | str) -> Path:
    """Save data as pretty formatted UTF-8 JSON."""
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return path


def load_json(file_path: Path | str) -> Any:
    """Load and parse UTF-8 JSON file."""
    path = Path(file_path)
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def create_manifest(
    run_id: str,
    input_files: dict[str, str],
    output_artifacts: dict[str, str],
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a standardized manifest dictionary for tracking run lineage."""
    return {
        "run_id": run_id,
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "input_files": input_files,
        "output_artifacts": output_artifacts,
        "metadata": metadata or {},
    }


def normalize_instruction_text(text: Any, lowercase: bool = False) -> str:
    """Normalize text using NFKC, collapse multiple whitespaces, and strip edges.

    Args:
        text: Input string or object.
        lowercase: Whether to convert the result to lowercase.

    Returns:
        Cleaned, normalized string.
    """
    if pd.isna(text):
        return ""
    norm = unicodedata.normalize("NFKC", str(text))
    norm = re.sub(r"\s+", " ", norm).strip()
    if lowercase:
        norm = norm.lower()
    return norm

