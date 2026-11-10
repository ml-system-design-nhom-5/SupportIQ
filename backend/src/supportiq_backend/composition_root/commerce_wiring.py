"""The wiring of commerce: its gateway, use cases, and router (ARCH-21)."""

from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from supportiq_backend.commerce import (
    GetShopOrder,
    GetShopProduct,
    ListShopOrders,
    ListShopProducts,
)
from supportiq_backend.commerce.adapters.commerce_gateway import PostgresCommerceGateway
from supportiq_backend.commerce.api.shop import ShopCommerceRoutes, build_shop_commerce_router
from supportiq_backend.composition_root.accounts_wiring import AccountsWiring
from supportiq_backend.platform.adapters.database import SqlAlchemyTransactionRunner


def wire_commerce(
    session_factory: async_sessionmaker[AsyncSession], accounts: AccountsWiring
) -> APIRouter:
    """Create the use cases of commerce and their router.

    Args:
        session_factory: The session factory of the replicas.
        accounts: The role checks and the session dependency.

    Returns:
        The router of the catalog and the caller's orders.
    """
    transactions = SqlAlchemyTransactionRunner(session_factory, PostgresCommerceGateway)
    return build_shop_commerce_router(
        ShopCommerceRoutes(
            list_products=ListShopProducts(transactions, accounts.authorizer),
            get_product=GetShopProduct(transactions, accounts.authorizer),
            list_orders=ListShopOrders(transactions, accounts.authorizer),
            get_order=GetShopOrder(transactions, accounts.authorizer),
            current_session=accounts.current_session,
        )
    )
