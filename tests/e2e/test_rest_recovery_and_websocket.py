import uuid
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_staff_reload_recovery_via_ticket_pointers(
    client: AsyncClient, agent_token: str, assigned_ticket_with_draft
):
    t_id = assigned_ticket_with_draft["ticket_id"]
    draft_id = assigned_ticket_with_draft["draft_id"]

    # Staff approves draft -> network drops before send; browser reloads with empty state
    dec_res = await client.post(
        f"/api/v1/tickets/{t_id}/decisions",
        json={"source": "ai", "action": "approve", "draft_id": draft_id},
        headers={"Authorization": f"Bearer {agent_token}", "Idempotency-Key": str(uuid.uuid4()), "If-Match": '"2"'},
    )
    assert dec_res.status_code == 201
    expected_dec_id = dec_res.json()["data"]["id"]

    # On reload, staff GETs ticket and recovers current_decision_id & ETag
    t_get = await client.get(f"/api/v1/tickets/{t_id}", headers={"Authorization": f"Bearer {agent_token}"})
    assert t_get.status_code == 200
    assert t_get.json()["data"]["current_decision_id"] == expected_dec_id
    etag = t_get.headers["ETag"]

    # Staff completes send using recovered pointer
    send_res = await client.post(
        f"/api/v1/tickets/{t_id}/replies",
        json={"decision_id": expected_dec_id},
        headers={"Authorization": f"Bearer {agent_token}", "Idempotency-Key": str(uuid.uuid4()), "If-Match": etag},
    )
    assert send_res.status_code == 201

@pytest.mark.asyncio
async def test_ws_disconnects_on_role_revocation(
    client: AsyncClient, agent_token: str, assigned_ticket_with_draft
):
    from starlette.testclient import TestClient
    from src.main import app
    from src.websocket import notify_resource_changed, ws_manager

    t_id = assigned_ticket_with_draft["ticket_id"]

    with TestClient(app).websocket_connect("/api/v1/ws") as ws:
        # First frame must be auth
        ws.send_json({"type": "auth", "access_token": agent_token})
        auth_ack = ws.receive_json()
        assert auth_ack["status"] == "authenticated"

        # Subscribe to ticket
        ws.send_json({"type": "subscribe", "resource_type": "ticket", "resource_id": t_id})
        sub_ack = ws.receive_json()
        assert sub_ack["status"] == "subscribed"

        # Broadcast event
        await notify_resource_changed("ticket.changed", uuid.UUID(t_id), 3)
        event = ws.receive_json()
        assert event["event"] == "ticket.changed"
        assert event["resource_id"] == t_id
        assert event["version"] == 3

        # Revoke user sessions / disconnect
        agent_user_id = uuid.UUID("a0000000-0000-0000-0000-000000000003")
        await ws_manager.disconnect_user(agent_user_id)

        with pytest.raises(Exception):
            ws.receive_json()
