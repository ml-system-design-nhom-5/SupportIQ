from uuid import UUID
from fastapi import APIRouter, Depends, Header, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.db import get_db_session
from src.contracts import AccessScope
from src.errors import AppError
from src.modules.auth.routes import get_current_user_scope
from src.modules.auth.service import authorize
from src.modules.commerce.models import OrderModel
from src.modules.commerce.schemas import CreateOrderRequest
from src.modules.commerce.service import list_products, create_order, get_order_by_id

router = APIRouter(prefix="/api/v1", tags=["commerce"])

@router.get("/products")
async def get_products(db: AsyncSession = Depends(get_db_session)):
    prods = await list_products(db)
    return {
        "data": [
            {
                "id": p.id,
                "sku": p.sku,
                "name": p.name,
                "description": p.description,
                "unit_price_minor": p.unit_price_minor,
                "currency": p.currency,
                "stock_quantity": p.stock_quantity,
                "category": p.category,
            }
            for p in prods
        ]
    }

@router.post("/orders", status_code=status.HTTP_201_CREATED)
async def create_new_order(
    payload: CreateOrderRequest,
    scope: AccessScope = Depends(get_current_user_scope),
    db: AsyncSession = Depends(get_db_session),
):
    authorize(scope, {"customer", "admin", "agent", "manager"})
    order = await create_order(db, customer_id=scope.actor_id, payload=payload)
    return {
        "data": {
            "id": order.id,
            "customer_id": order.customer_id,
            "status": order.status,
            "total_minor": order.total_minor,
            "currency": order.currency,
            "demo": order.demo,
            "shipping_address": order.shipping_address,
            "items": [
                {
                    "id": it.id,
                    "product_id": it.product_id,
                    "quantity": it.quantity,
                    "unit_price_minor": it.unit_price_minor,
                    "total_minor": it.total_minor,
                }
                for it in order.items
            ],
            "created_at": order.created_at.isoformat(),
        }
    }

@router.get("/orders")
async def get_orders(
    scope: AccessScope = Depends(get_current_user_scope),
    db: AsyncSession = Depends(get_db_session),
):
    stmt = select(OrderModel).options(selectinload(OrderModel.items))
    if scope.role == "customer":
        stmt = stmt.where(OrderModel.customer_id == str(scope.actor_id))
    result = await db.execute(stmt)
    orders = result.scalars().all()
    return {
        "data": [
            {
                "id": o.id,
                "customer_id": o.customer_id,
                "status": o.status,
                "total_minor": o.total_minor,
                "currency": o.currency,
                "demo": o.demo,
            }
            for o in orders
        ]
    }

@router.get("/orders/{order_id}")
async def get_order_detail(
    order_id: UUID,
    scope: AccessScope = Depends(get_current_user_scope),
    db: AsyncSession = Depends(get_db_session),
):
    cust_id = scope.actor_id if scope.role == "customer" else None
    order = await get_order_by_id(db, order_id, customer_id=cust_id)
    if not order:
        raise AppError(status=404, code="not_found", title="Not Found", detail="Order not found.")
    return {
        "data": {
            "id": order.id,
            "customer_id": order.customer_id,
            "status": order.status,
            "total_minor": order.total_minor,
            "currency": order.currency,
            "demo": order.demo,
            "shipping_address": order.shipping_address,
            "items": [
                {
                    "id": it.id,
                    "product_id": it.product_id,
                    "quantity": it.quantity,
                    "unit_price_minor": it.unit_price_minor,
                    "total_minor": it.total_minor,
                }
                for it in order.items
            ],
        }
    }
