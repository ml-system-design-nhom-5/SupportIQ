import json
from pathlib import Path
from typing import Optional, Dict, Any

class CommerceAdapter:
    """Production-grade commerce adapter backed by knowledge base mock orders with RBAC scope checks."""
    def __init__(self, data_path: Optional[str] = None):
        if data_path:
            p = Path(data_path)
        else:
            p = Path("data/knowledge/mock_orders.json")
        self.orders: Dict[str, Dict[str, Any]] = {}
        if p.exists():
            with open(p, "r", encoding="utf-8") as f:
                orders_list = json.load(f)
                for ord_item in orders_list:
                    self.orders[ord_item["order_id"]] = ord_item

    def lookup_order(
        self,
        order_id: str,
        ticket_customer_id: str,
        verified_scope: str
    ) -> Dict[str, Any]:
        """Look up order details ensuring caller has valid read scope and customer ownership."""
        # Check authorization scope
        has_read_scope = "order:read" in verified_scope or "ticket:read" in verified_scope or "admin" in verified_scope
        if not has_read_scope:
            return {"authorized": False, "error": "unauthorized_scope", "order": None}

        order = self.orders.get(order_id)
        if not order:
            return {"authorized": False, "error": "order_not_found", "order": None}

        # Check customer ownership (staff/admin scope can inspect any order, customer can only inspect own)
        is_privileged = "staff" in verified_scope or "admin" in verified_scope or "support" in verified_scope
        if not is_privileged and order["customer_id"] != ticket_customer_id:
            return {"authorized": False, "error": "unauthorized_customer", "order": None}

        return {"authorized": True, "error": None, "order": order}
