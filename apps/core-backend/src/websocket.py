import asyncio
import json
from datetime import datetime, timezone
from typing import Literal, Any
from uuid import UUID
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from src.contracts import AccessScope
from src.db import AppSessionLocal
from src.errors import AppError
from src.modules.auth.service import authenticate_request
from src.modules.tickets.service import get_ticket_for_actor

router = APIRouter(tags=["websocket"])

class WebSocketConnectionManager:
    def __init__(self):
        self._connections: dict[WebSocket, dict[str, Any]] = {}

    async def connect(self, websocket: WebSocket) -> None:
        self._connections[websocket] = {
            "scope": None,
            "subscribed_resources": set(),
        }

    def set_authenticated_scope(self, websocket: WebSocket, scope: AccessScope) -> None:
        if websocket in self._connections:
            self._connections[websocket]["scope"] = scope

    def add_subscription(self, websocket: WebSocket, resource_id: str) -> None:
        if websocket in self._connections:
            self._connections[websocket]["subscribed_resources"].add(resource_id)

    def remove_subscription(self, websocket: WebSocket, resource_id: str) -> None:
        if websocket in self._connections:
            self._connections[websocket]["subscribed_resources"].discard(resource_id)

    def disconnect(self, websocket: WebSocket) -> None:
        self._connections.pop(websocket, None)

    async def disconnect_user(self, user_id: UUID | str) -> None:
        target_id = str(user_id)
        to_close = []
        for ws, info in list(self._connections.items()):
            scope: AccessScope | None = info.get("scope")
            if scope and str(scope.actor_id) == target_id:
                to_close.append(ws)

        for ws in to_close:
            try:
                await ws.close(code=1008, reason="Role revoked or session invalidated")
            except Exception:
                pass
            self.disconnect(ws)

    async def notify_resource_changed(
        self,
        event: Literal["ticket.changed", "run.changed"],
        resource_id: UUID,
        version: int,
    ) -> None:
        payload = {
            "event": event,
            "resource_id": str(resource_id),
            "version": version,
            "occurred_at": datetime.now(timezone.utc).isoformat(),
        }
        res_str = str(resource_id)
        for ws, info in list(self._connections.items()):
            if res_str in info.get("subscribed_resources", set()):
                try:
                    await ws.send_json(payload)
                except Exception:
                    self.disconnect(ws)

ws_manager = WebSocketConnectionManager()

async def notify_resource_changed(
    event: Literal["ticket.changed", "run.changed"],
    resource_id: UUID,
    version: int,
) -> None:
    await ws_manager.notify_resource_changed(event, resource_id, version)

@router.websocket("/api/v1/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    await ws_manager.connect(websocket)

    # 1. Require first frame auth within 5 seconds
    try:
        data = await asyncio.wait_for(websocket.receive_json(), timeout=5.0)
    except Exception:
        await websocket.close(code=1008, reason="Authentication timeout or invalid initial frame")
        ws_manager.disconnect(websocket)
        return

    if not isinstance(data, dict) or data.get("type") != "auth" or not data.get("access_token"):
        await websocket.close(code=1008, reason="First frame must be auth with access_token")
        ws_manager.disconnect(websocket)
        return

    token = data["access_token"]
    scope: AccessScope | None = None
    try:
        async with AppSessionLocal() as session:
            scope = await authenticate_request(session, redis=None, token=token, require_fresh_db=True)
    except AppError:
        await websocket.close(code=1008, reason="Invalid or expired access token")
        ws_manager.disconnect(websocket)
        return
    except Exception:
        await websocket.close(code=1008, reason="Authentication verification failed")
        ws_manager.disconnect(websocket)
        return

    ws_manager.set_authenticated_scope(websocket, scope)
    await websocket.send_json({"status": "authenticated"})

    # 2. Main message loop
    try:
        while True:
            msg = await websocket.receive_json()
            if not isinstance(msg, dict):
                continue

            msg_type = msg.get("type")
            if msg_type == "subscribe":
                res_id = msg.get("resource_id")
                res_type = msg.get("resource_type", "ticket")
                if not res_id:
                    await websocket.send_json({"status": "error", "message": "resource_id required"})
                    continue

                # Verify permissions
                try:
                    res_uuid = UUID(res_id)
                    if res_type == "ticket":
                        async with AppSessionLocal() as session:
                            await get_ticket_for_actor(session, res_uuid, scope)
                    ws_manager.add_subscription(websocket, str(res_id))
                    await websocket.send_json({"status": "subscribed", "resource_id": str(res_id)})
                except Exception as exc:
                    await websocket.send_json({"status": "error", "message": f"Subscription rejected: {exc}"})

            elif msg_type == "unsubscribe":
                res_id = msg.get("resource_id")
                if res_id:
                    ws_manager.remove_subscription(websocket, str(res_id))
                    await websocket.send_json({"status": "unsubscribed", "resource_id": str(res_id)})

            elif msg_type == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception:
        ws_manager.disconnect(websocket)
