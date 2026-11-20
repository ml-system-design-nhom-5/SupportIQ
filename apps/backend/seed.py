"""Deterministic importer for the user-selected synthetic orders; no commerce writes at runtime."""

import json
from pathlib import Path
import uuid

from argon2 import PasswordHasher
from sqlalchemy import select

from .platform.models import Account, Order, Product


ORDER_STATUSES = {"Shipping": "shipped", "Delivery_Delayed": "shipped", "In_Transit": "shipped", "Processing": "processing", "Returned": "delivered", "Cancelled": "cancelled", "Payment_Failed": "placed", "Delivered": "delivered"}
REFUND_STATUSES = {"Processing": "under_review", "Completed": "paid", "Pending": "requested", "Approved": "approved", "Rejected": "rejected", "Refunded": "paid"}


def account_id(login):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "supportiq/account/" + login))


def normalize_order(raw, index):
    lines = [{"product_id": item["product_id"], "product_name": item["name"], "quantity": item["quantity"]} for item in raw["items"]]
    subtotal = sum(item["price"] * item["quantity"] for item in raw["items"])
    money = lambda value: {"amount_minor": int(value), "currency": "VND"}
    status = ORDER_STATUSES[raw["order_status"]]
    shipment_status = "delayed" if raw["order_status"] == "Delivery_Delayed" else "in_transit" if status == "shipped" else "delivered" if status == "delivered" else "not_shipped"
    refund = None
    if raw.get("refund_status"):
        refund = {"refund_status": REFUND_STATUSES.get(raw["refund_status"], "under_review"), "refund_amount": money(raw.get("refund_amount", 0)), "expected_refund_time": raw.get("expected_refund_time")}
    return {"order_id": raw["order_id"], "order_status": status, "source_status": raw["order_status"],
            "placed_at": f"2026-10-{min(19, 1 + index // 6):02d}T07:00:00Z", "date_is_synthetic": True,
            "order_total": money(raw["total_amount"]), "shipping_cost": money(max(0, raw["total_amount"] - subtotal)),
            "lines": lines, "shipment": {"shipment_status": shipment_status, "tracking_code": raw.get("tracking_code"), "carrier": raw.get("carrier"), "estimated_delivery_text": raw.get("estimated_delivery"), "delivered_at": raw.get("delivery_date"), "timeline": raw.get("shipping_timeline", [])},
            "refund": refund, "customer_id": raw["customer_id"], "customer_name": raw["customer_name"],
            "phone": raw.get("phone"), "transaction_id": raw.get("transaction_id"), "payment_status": raw.get("payment_status"), "source": raw}


def seed(database, passwords):
    source = Path(__file__).resolve().parents[2] / "data/knowledge/mock_orders.json"
    orders = json.loads(source.read_text(encoding="utf-8"))
    hasher = PasswordHasher()
    with database.transaction() as session:
        if session.scalar(select(Account.account_id).limit(1)):
            return
        customers = list(dict.fromkeys(order["customer_id"] for order in orders))
        for index, customer in enumerate(customers, 1):
            first = next(order for order in orders if order["customer_id"] == customer)
            login = f"customer-{index}"
            session.add(Account(account_id=account_id(login), login_name=login, display_name=first["customer_name"], role="customer", customer_id=customer, password_hash=hasher.hash(passwords["customer"])))
        for role, name in (("staff", "Mai Nguyen"), ("manager", "Hoa Pham"), ("admin", "Minh Le")):
            login = role + "-1"
            session.add(Account(account_id=account_id(login), login_name=login, display_name=name, role=role, password_hash=hasher.hash(passwords[role])))
        seen = set()
        for index, order in enumerate(orders):
            session.add(Order(order_id=order["order_id"], customer_id=order["customer_id"], payload=normalize_order(order, index)))
            for item in order["items"]:
                if item["product_id"] in seen:
                    continue
                seen.add(item["product_id"])
                session.add(Product(product_id=item["product_id"], payload={"product_id": item["product_id"], "name": item["name"], "description": "A product from the synthetic order catalog.", "category": "Catalog", "price": {"amount_minor": item["price"], "currency": "VND"}}))
