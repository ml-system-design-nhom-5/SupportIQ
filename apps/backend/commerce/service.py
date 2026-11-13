import base64

from apps.backend.platform.database import Problem
from apps.backend.platform.models import Order


def require_order(session, order_id, customer_id=None):
    order = session.get(Order, order_id)
    if order is None or (customer_id is not None and order.customer_id != customer_id):
        raise Problem(404, "not-found", "This order was not found.")
    return order


def order_view(order, internal=False):
    payload = dict(order.payload)
    for name in ("customer_id", "customer_name", "phone", "transaction_id", "payment_method", "source"):
        payload.pop(name, None)
    if not internal:
        payload.pop("shipping_address", None)
    return payload


def page(items, limit=20, cursor=None):
    if not 1 <= limit <= 100:
        raise Problem(422, "invalid-request", "Choose a page size between 1 and 100.")
    try:
        offset = int(base64.urlsafe_b64decode(cursor).decode()) if cursor else 0
        if offset < 0:
            raise ValueError()
    except (ValueError, TypeError, UnicodeError):
        raise Problem(422, "invalid-request", "The page cursor is invalid.")
    selected = items[offset:offset + limit]
    return {"items": selected, "next_cursor": base64.urlsafe_b64encode(str(offset + limit).encode()).decode() if offset + limit < len(items) else None}


def page_query(session, query, mapper, limit=20, cursor=None):
    if not 1 <= limit <= 100:
        raise Problem(422, "invalid-request", "Choose a page size between 1 and 100.")
    try:
        offset = int(base64.urlsafe_b64decode(cursor).decode()) if cursor else 0
        if offset < 0:
            raise ValueError()
    except (ValueError, TypeError, UnicodeError):
        raise Problem(422, "invalid-request", "The page cursor is invalid.")
    rows = list(session.scalars(query.offset(offset).limit(limit + 1)))
    has_more = len(rows) > limit
    page_rows = rows[:limit]
    return {
        "items": [mapper(row) for row in page_rows],
        "next_cursor": base64.urlsafe_b64encode(str(offset + limit).encode()).decode() if has_more else None,
    }

