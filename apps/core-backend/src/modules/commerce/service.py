from uuid import UUID, uuid4
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.contracts import AccessScope
from src.errors import AppError
from src.modules.commerce.models import ProductModel, OrderModel, OrderItemModel, ShipmentModel
from src.modules.commerce.schemas import CreateOrderRequest, OrderSnapshotDTO, OrderItemResponse

async def list_products(db: AsyncSession) -> list[ProductModel]:
    result = await db.execute(select(ProductModel).order_by(ProductModel.name))
    return list(result.scalars().all())

async def create_order(db: AsyncSession, customer_id: UUID, payload: CreateOrderRequest) -> OrderModel:
    if not payload.items:
        raise AppError(status=422, code="validation_error", title="Validation Error", detail="Order must contain at least one item.")

    total_minor = 0
    order_id = uuid4()
    order_items: list[OrderItemModel] = []

    for item in payload.items:
        prod = await db.get(ProductModel, str(item.product_id))
        if not prod:
            raise AppError(status=404, code="not_found", title="Not Found", detail=f"Product {item.product_id} not found.")
        if item.quantity <= 0:
            raise AppError(status=422, code="validation_error", title="Validation Error", detail="Quantity must be greater than zero.")

        line_total = prod.unit_price_minor * item.quantity
        total_minor += line_total
        order_items.append(
            OrderItemModel(
                id=str(uuid4()),
                order_id=str(order_id),
                product_id=prod.id,
                quantity=item.quantity,
                unit_price_minor=prod.unit_price_minor,
                total_minor=line_total,
            )
        )

    order = OrderModel(
        id=str(order_id),
        customer_id=str(customer_id),
        status="placed",
        total_minor=total_minor,
        currency="VND",
        demo=True,
        shipping_address=payload.shipping_address,
        items=order_items,
    )
    db.add(order)
    await db.commit()
    await db.refresh(order, ["items"])
    return order

async def get_order_by_id(db: AsyncSession, order_id: UUID, customer_id: UUID | None = None) -> OrderModel | None:
    stmt = select(OrderModel).where(OrderModel.id == str(order_id)).options(selectinload(OrderModel.items))
    if customer_id is not None:
        stmt = stmt.where(OrderModel.customer_id == str(customer_id))
    result = await db.execute(stmt)
    return result.scalar_one_or_none()

async def get_order_snapshot_for_ticket(
    session: AsyncSession,
    order_id: UUID,
    scope: AccessScope,
) -> OrderSnapshotDTO | None:
    cust_id = scope.actor_id if scope.role == "customer" else None
    order = await get_order_by_id(session, order_id, customer_id=cust_id)
    if not order:
        return None

    shipment_stmt = select(ShipmentModel).where(ShipmentModel.order_id == str(order_id))
    shipment_res = await session.execute(shipment_stmt)
    shipment = shipment_res.scalar_one_or_none()

    items_dto = [
        OrderItemResponse(
            id=UUID(it.id),
            product_id=UUID(it.product_id),
            quantity=it.quantity,
            unit_price_minor=it.unit_price_minor,
            total_minor=it.total_minor,
        )
        for it in order.items
    ]

    return OrderSnapshotDTO(
        order_id=UUID(order.id),
        customer_id=UUID(order.customer_id),
        status=order.status,
        total_minor=order.total_minor,
        currency=order.currency,
        demo=order.demo,
        items=items_dto,
        shipment_status=shipment.status if shipment else None,
        tracking_code=shipment.tracking_code if shipment else None,
        estimated_delivery=shipment.estimated_delivery if shipment else None,
    )
