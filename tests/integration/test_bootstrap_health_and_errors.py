import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_health_live_and_ready_require_internal_token(client: AsyncClient):
    res_unauth = await client.get("/api/v1/health/live")
    assert res_unauth.status_code == 401
    assert res_unauth.headers["content-type"].startswith("application/problem+json")
    body = res_unauth.json()
    assert body["type"] == "urn:supportiq:problem:unauthenticated"
    assert "request_id" in body

    headers = {"Authorization": "Bearer test-internal-service-token"}
    res_live = await client.get("/api/v1/health/live", headers=headers)
    assert res_live.status_code == 200
    assert res_live.json() == {"data": {"status": "ok", "ai_available": False}}

    res_ready = await client.get("/api/v1/health/ready", headers=headers)
    assert res_ready.status_code == 200
    assert res_ready.json()["data"]["status"] == "ok"

@pytest.mark.asyncio
async def test_if_match_and_idempotency_conflict_contracts():
    from src.idempotency import parse_if_match
    from src.errors import AppError

    with pytest.raises(AppError) as exc_missing:
        parse_if_match(None, current_version=3)
    assert exc_missing.value.status == 428
    assert exc_missing.value.code == "precondition_required"

    with pytest.raises(AppError) as exc_mismatch:
        parse_if_match('"2"', current_version=3)
    assert exc_mismatch.value.status == 412
    assert exc_mismatch.value.code == "version_conflict"
