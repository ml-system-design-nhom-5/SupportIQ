import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_login_refresh_csrf_and_last_admin_protection(client: AsyncClient):
    res = await client.post(
        "/api/v1/sessions",
        json={"email": "admin@supportiq.demo", "password": "DemoPassword123!"},
        headers={"Origin": "https://supportiq.local"},
    )
    assert res.status_code == 201
    data = res.json()["data"]
    assert data["token_type"] == "Bearer"
    assert data["expires_in"] == 900
    assert data["user"]["role"] == "admin"
    assert "refresh_token=" in res.headers.get("set-cookie", "")

    admin_token = data["access_token"]
    admin_id = data["user"]["id"]
    # Cannot demote or deactivate the sole active Admin
    demote = await client.patch(
        f"/api/v1/users/{admin_id}",
        json={"role": "agent"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert demote.status_code == 409
    assert demote.json()["code"] == "state_conflict"

@pytest.mark.asyncio
async def test_revoked_role_blocks_mutation_with_warm_cache(client: AsyncClient):
    # Agent logs in and warms cache via GET /me
    agent_login = await client.post(
        "/api/v1/sessions",
        json={"email": "agent1@supportiq.demo", "password": "DemoPassword123!"},
        headers={"Origin": "https://supportiq.local"},
    )
    agent_token = agent_login.json()["data"]["access_token"]
    agent_id = agent_login.json()["data"]["user"]["id"]
    assert (await client.get("/api/v1/me", headers={"Authorization": f"Bearer {agent_token}"})).status_code == 200

    # Admin deactivates agent while cache is still within 30s TTL
    admin_login = await client.post(
        "/api/v1/sessions",
        json={"email": "admin@supportiq.demo", "password": "DemoPassword123!"},
        headers={"Origin": "https://supportiq.local"},
    )
    admin_token = admin_login.json()["data"]["access_token"]
    patch_res = await client.patch(
        f"/api/v1/users/{agent_id}",
        json={"active": False},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert patch_res.status_code == 200

    # Agent's existing JWT is immediately rejected
    me_after = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {agent_token}"})
    assert me_after.status_code == 401
