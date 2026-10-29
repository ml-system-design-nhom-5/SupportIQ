import uuid
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_customer_checkout_ticket_creation_and_scope_isolation(
    client: AsyncClient, customer_token: str, other_customer_token: str, agent_token: str, admin_token: str
):
    products = (await client.get("/api/v1/products")).json()["data"]
    prod_id = products[0]["id"]

    # Customer creates demo order (server calculates total_minor)
    order_res = await client.post(
        "/api/v1/orders",
        json={"items": [{"product_id": prod_id, "quantity": 2}]},
        headers={"Authorization": f"Bearer {customer_token}", "Idempotency-Key": str(uuid.uuid4())},
    )
    assert order_res.status_code == 201
    order = order_res.json()["data"]
    assert order["demo"] is True
    assert order["total_minor"] == products[0]["unit_price_minor"] * 2

    # Other customer cannot attach this order_id or view it
    bad_ticket = await client.post(
        "/api/v1/tickets",
        json={"message": "Where is my order?", "order_id": order["id"]},
        headers={"Authorization": f"Bearer {other_customer_token}", "Idempotency-Key": str(uuid.uuid4())},
    )
    assert bad_ticket.status_code == 404

    # Owner customer creates ticket
    t_res = await client.post(
        "/api/v1/tickets",
        json={"message": "Where is my order?", "order_id": order["id"]},
        headers={"Authorization": f"Bearer {customer_token}", "Idempotency-Key": str(uuid.uuid4())},
    )
    assert t_res.status_code == 201
    assert t_res.headers["ETag"] == '"1"'
    ticket_data = t_res.json()["data"]
    assert "current_run_id" not in ticket_data
    assert "current_decision_id" not in ticket_data

    # Admin is forbidden from reading ticket content
    admin_get = await client.get(
        f"/api/v1/tickets/{ticket_data['id']}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert admin_get.status_code == 403

    # Agent claims unassigned standard ticket and sees staff pointers
    claim_res = await client.patch(
        f"/api/v1/tickets/{ticket_data['id']}",
        json={"status": "open"},
        headers={"Authorization": f"Bearer {agent_token}", "If-Match": '"1"'},
    )
    assert claim_res.status_code == 200
    assert "current_run_id" in claim_res.json()["data"]
