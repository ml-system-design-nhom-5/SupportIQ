"""The shop's read operations: `listShopProducts`, `getShopProduct`, `listShopOrders`, ..."""

from dataclasses import dataclass
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from pydantic import MISSING

from app.accounts import AuthenticatedSession, OperationId
from app.commerce.application import (
    GetShopOrder,
    GetShopProduct,
    ListShopOrders,
    ListShopProducts,
)
from app.commerce.domain import (
    Money,
    Order,
    OrderId,
    OrderPage,
    Product,
    ProductId,
    ProductPage,
    ProductPosition,
    Refund,
    Shipment,
)
from app.generated import Cursor as ContractCursor
from app.generated import Money as ContractMoney
from app.generated import OrderStatus as ContractOrderStatus
from app.generated import RefundStatus as ContractRefundStatus
from app.generated import (
    ShipmentStatus as ContractShipmentStatus,
)
from app.generated import (
    ShopOrderLine,
    ShopOrderPage,
    ShopOrderView,
    ShopProductPage,
    ShopProductView,
    ShopRefundView,
    ShopShipmentView,
)
from app.platform.web import (
    RequestDependency,
    decode_cursor,
    encode_cursor,
    format_timestamp,
    json_response,
    parse_limit,
    provide,
)

LIST_PRODUCTS_OPERATION = OperationId.LIST_SHOP_PRODUCTS.value
LIST_ORDERS_OPERATION = OperationId.LIST_SHOP_ORDERS.value
CURSOR_NAME_FIELD = "name"
CURSOR_PRODUCT_FIELD = "product_id"
CURSOR_POSITION_FIELD = "position"
FIRST_POSITION = 0


@dataclass(frozen=True, slots=True)
class ShopCommerceRoutes:
    """What the read routes of the shop need from the composition root.

    Attributes:
        list_products: The catalog list.
        get_product: One product.
        list_orders: The caller's orders.
        get_order: One order of the caller.
        current_session: The session of a request.
    """

    list_products: ListShopProducts
    get_product: GetShopProduct
    list_orders: ListShopOrders
    get_order: GetShopOrder
    current_session: RequestDependency[AuthenticatedSession]


def to_money(money: Money) -> ContractMoney:
    """Map money to the contract.

    Args:
        money: The amount.

    Returns:
        The contract model.
    """
    return ContractMoney(amount_minor=money.amount_minor, currency=money.currency)


def to_product_view(product: Product) -> ShopProductView:
    """Map a product to the contract.

    Args:
        product: The product.

    Returns:
        The contract model.
    """
    return ShopProductView(
        product_id=product.product_id,
        name=product.name,
        description=product.description,
        category=product.category,
        price=to_money(product.price),
    )


def to_shipment_view(shipment: Shipment) -> ShopShipmentView:
    """Map a shipment to the contract; absent dates stay absent.

    Args:
        shipment: The shipment.

    Returns:
        The contract model.
    """
    estimate = shipment.estimated_delivery_at
    delivered = shipment.delivered_at
    return ShopShipmentView(
        shipment_status=ContractShipmentStatus(shipment.status.value),
        estimated_delivery_at=MISSING if estimate is None else format_timestamp(estimate),
        delivered_at=MISSING if delivered is None else format_timestamp(delivered),
    )


def to_refund_view(refund: Refund) -> ShopRefundView:
    """Map a refund to the contract.

    Args:
        refund: The refund.

    Returns:
        The contract model.
    """
    return ShopRefundView(
        refund_status=ContractRefundStatus(refund.status.value),
        refund_amount=to_money(refund.amount),
        refund_requested_at=format_timestamp(refund.requested_at),
    )


def to_order_view(order: Order) -> ShopOrderView:
    """Map an order to the contract: it has no shipping address and no transaction ID.

    Args:
        order: The order.

    Returns:
        The contract model.
    """
    return ShopOrderView(
        order_id=order.order_id,
        order_status=ContractOrderStatus(order.status.value),
        placed_at=format_timestamp(order.placed_at),
        order_total=to_money(order.order_total),
        shipping_cost=to_money(order.shipping_cost),
        lines=[
            ShopOrderLine(
                product_id=line.product_id,
                product_name=line.product_name,
                quantity=line.quantity,
            )
            for line in order.lines
        ],
        shipment=to_shipment_view(order.shipment),
        refund=MISSING if order.refund is None else to_refund_view(order.refund),
    )


def to_product_page(page: ProductPage) -> ShopProductPage:
    """Map a page of products to the contract.

    Args:
        page: The page.

    Returns:
        The contract model; `next_cursor` is absent on the last page.
    """
    position = page.next_position
    next_cursor: ContractCursor | MISSING = MISSING
    if position is not None:
        next_cursor = ContractCursor(
            encode_cursor(
                LIST_PRODUCTS_OPERATION,
                {CURSOR_NAME_FIELD: position.name, CURSOR_PRODUCT_FIELD: position.product_id},
            )
        )
    return ShopProductPage(
        items=[to_product_view(product) for product in page.items], next_cursor=next_cursor
    )


def to_order_page(page: OrderPage) -> ShopOrderPage:
    """Map a page of orders to the contract.

    Args:
        page: The page.

    Returns:
        The contract model; the cursor holds a position and no value of an order.
    """
    next_cursor: ContractCursor | MISSING = MISSING
    if page.next_position is not None:
        next_cursor = ContractCursor(
            encode_cursor(LIST_ORDERS_OPERATION, {CURSOR_POSITION_FIELD: page.next_position})
        )
    return ShopOrderPage(
        items=[to_order_view(order) for order in page.items], next_cursor=next_cursor
    )


def parse_product_cursor(raw: str | None) -> ProductPosition | None:
    """Read the cursor of `listShopProducts`.

    Args:
        raw: The `cursor` query parameter, or None when absent.

    Returns:
        The last product of the previous page, or None for the first page.

    Raises:
        InvalidCursorError: The cursor is malformed or from another operation.
    """
    fields = decode_cursor(
        raw, LIST_PRODUCTS_OPERATION, frozenset({CURSOR_NAME_FIELD, CURSOR_PRODUCT_FIELD})
    )
    if fields is None:
        return None
    return ProductPosition(
        fields.text(CURSOR_NAME_FIELD), ProductId(fields.text(CURSOR_PRODUCT_FIELD))
    )


def parse_order_cursor(raw: str | None) -> int:
    """Read the cursor of `listShopOrders`.

    Args:
        raw: The `cursor` query parameter, or None when absent.

    Returns:
        The position of the first order of the page.

    Raises:
        InvalidCursorError: The cursor is malformed or from another operation.
    """
    fields = decode_cursor(raw, LIST_ORDERS_OPERATION, frozenset({CURSOR_POSITION_FIELD}))
    return FIRST_POSITION if fields is None else fields.natural_number(CURSOR_POSITION_FIELD)


def build_shop_commerce_router(routes: ShopCommerceRoutes) -> APIRouter:
    """Build the router of the catalog and the caller's orders. Every route only reads.

    Args:
        routes: The use cases and the session dependency.

    Returns:
        The router.
    """
    router = APIRouter()
    _add_catalog_routes(router, routes)
    _add_order_routes(router, routes)
    return router


def _add_catalog_routes(router: APIRouter, routes: ShopCommerceRoutes) -> None:
    current_session = Depends(routes.current_session)
    list_products = Depends(provide(routes.list_products))
    get_product = Depends(provide(routes.get_product))

    @router.get("/v1/shop/products", status_code=HTTPStatus.OK)
    async def handle_list_shop_products(
        session: Annotated[AuthenticatedSession, current_session],
        use_case: Annotated[ListShopProducts, list_products],
        limit: Annotated[str | None, Query()] = None,
        cursor: Annotated[str | None, Query()] = None,
    ) -> Response:
        customer = use_case.authorize(session.principal)
        page = await use_case.execute(customer, parse_product_cursor(cursor), parse_limit(limit))
        return json_response(to_product_page(page))

    @router.get("/v1/shop/products/{product_id}", status_code=HTTPStatus.OK)
    async def handle_get_shop_product(
        product_id: str,
        session: Annotated[AuthenticatedSession, current_session],
        use_case: Annotated[GetShopProduct, get_product],
    ) -> Response:
        product = await use_case.execute(session.principal, ProductId(product_id))
        return json_response(to_product_view(product))


def _add_order_routes(router: APIRouter, routes: ShopCommerceRoutes) -> None:
    current_session = Depends(routes.current_session)
    list_orders = Depends(provide(routes.list_orders))
    get_order = Depends(provide(routes.get_order))

    @router.get("/v1/shop/orders", status_code=HTTPStatus.OK)
    async def handle_list_shop_orders(
        session: Annotated[AuthenticatedSession, current_session],
        use_case: Annotated[ListShopOrders, list_orders],
        limit: Annotated[str | None, Query()] = None,
        cursor: Annotated[str | None, Query()] = None,
    ) -> Response:
        customer = use_case.authorize(session.principal)
        page = await use_case.execute(customer, parse_order_cursor(cursor), parse_limit(limit))
        return json_response(to_order_page(page))

    @router.get("/v1/shop/orders/{order_id}", status_code=HTTPStatus.OK)
    async def handle_get_shop_order(
        order_id: str,
        session: Annotated[AuthenticatedSession, current_session],
        use_case: Annotated[GetShopOrder, get_order],
    ) -> Response:
        order = await use_case.execute(session.principal, OrderId(order_id))
        return json_response(to_order_view(order))
