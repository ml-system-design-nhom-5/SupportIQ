"""The shop's read use cases: the catalog and the customer's own orders (ADR-0013)."""

from app.accounts import (
    Authorizer,
    CustomerPrincipal,
    OperationId,
    Principal,
)
from app.commerce.domain import (
    CommerceGateway,
    Order,
    OrderId,
    OrderNotFoundError,
    OrderPage,
    Product,
    ProductId,
    ProductNotFoundError,
    ProductPage,
    ProductPosition,
)
from app.platform import TransactionRunner


class ListShopProducts:
    """Return one page of the read-only catalog (`listShopProducts`)."""

    def __init__(
        self, transactions: TransactionRunner[CommerceGateway], authorizer: Authorizer
    ) -> None:
        """Keep the dependencies.

        Args:
            transactions: Opens the transaction of the read.
            authorizer: The role checks.
        """
        self._transactions = transactions
        self._authorizer = authorizer

    def authorize(self, principal: Principal) -> CustomerPrincipal:
        """Allow only a customer, before the request is parsed.

        Args:
            principal: The caller.

        Returns:
            The caller as a customer.

        Raises:
            ForbiddenRoleError: The caller is not a customer.
        """
        return self._authorizer.require_customer(principal, OperationId.LIST_SHOP_PRODUCTS)

    async def execute(
        self, _customer: CustomerPrincipal, after: ProductPosition | None, limit: int
    ) -> ProductPage:
        """Load one page of products.

        Args:
            _customer: The caller; the type proves the role check.
            after: The last product of the previous page, or None for the first page.
            limit: The maximum number of products.

        Returns:
            The page.

        Raises:
            DatabaseUnavailableError: The database is not available or a timeout fired.
        """
        async with self._transactions.begin() as transaction:
            products = await transaction.stores.load_products(after, limit + 1)
        items = products[:limit]
        last = items[-1] if len(products) > limit else None
        next_position = None if last is None else ProductPosition(last.name, last.product_id)
        return ProductPage(items, next_position)


class GetShopProduct:
    """Return one product of the catalog (`getShopProduct`)."""

    def __init__(
        self, transactions: TransactionRunner[CommerceGateway], authorizer: Authorizer
    ) -> None:
        """Keep the dependencies.

        Args:
            transactions: Opens the transaction of the read.
            authorizer: The role checks.
        """
        self._transactions = transactions
        self._authorizer = authorizer

    async def execute(self, principal: Principal, product_id: ProductId) -> Product:
        """Load one product.

        Args:
            principal: The caller.
            product_id: The identifier.

        Returns:
            The product.

        Raises:
            ForbiddenRoleError: The caller is not a customer.
            ProductNotFoundError: The product is unknown.
            DatabaseUnavailableError: The database is not available or a timeout fired.
        """
        self._authorizer.require_customer(principal, OperationId.GET_SHOP_PRODUCT)
        async with self._transactions.begin() as transaction:
            product = await transaction.stores.load_product(product_id)
        if product is None:
            raise ProductNotFoundError
        return product


class ListShopOrders:
    """Return one page of the caller's own orders (`listShopOrders`, SEC-17)."""

    def __init__(
        self, transactions: TransactionRunner[CommerceGateway], authorizer: Authorizer
    ) -> None:
        """Keep the dependencies.

        Args:
            transactions: Opens the transaction of the read.
            authorizer: The role checks.
        """
        self._transactions = transactions
        self._authorizer = authorizer

    def authorize(self, principal: Principal) -> CustomerPrincipal:
        """Allow only a customer, before the request is parsed.

        Args:
            principal: The caller.

        Returns:
            The caller as a customer.

        Raises:
            ForbiddenRoleError: The caller is not a customer.
        """
        return self._authorizer.require_customer(principal, OperationId.LIST_SHOP_ORDERS)

    async def execute(self, customer: CustomerPrincipal, position: int, limit: int) -> OrderPage:
        """Load one page of the customer's orders.

        Args:
            customer: The caller, whose `customer_id` filters the query.
            position: The position of the first order of the page, from 0.
            limit: The maximum number of orders.

        Returns:
            The page.

        Raises:
            DatabaseUnavailableError: The database is not available or a timeout fired.
        """
        async with self._transactions.begin() as transaction:
            orders = await transaction.stores.load_orders(
                customer.customer_id, position=position, limit=limit + 1
            )
        items = orders[:limit]
        return OrderPage(items, position + limit if len(orders) > limit else None)


class GetShopOrder:
    """Return one of the caller's orders (`getShopOrder`, SEC-17)."""

    def __init__(
        self, transactions: TransactionRunner[CommerceGateway], authorizer: Authorizer
    ) -> None:
        """Keep the dependencies.

        Args:
            transactions: Opens the transaction of the read.
            authorizer: The role checks.
        """
        self._transactions = transactions
        self._authorizer = authorizer

    async def execute(self, principal: Principal, order_id: OrderId) -> Order:
        """Load one order of the caller.

        Args:
            principal: The caller.
            order_id: The identifier.

        Returns:
            The order.

        Raises:
            ForbiddenRoleError: The caller is not a customer.
            OrderNotFoundError: The order is unknown or belongs to another customer.
            DatabaseUnavailableError: The database is not available or a timeout fired.
        """
        customer = self._authorizer.require_customer(principal, OperationId.GET_SHOP_ORDER)
        async with self._transactions.begin() as transaction:
            order = await transaction.stores.load_order(customer.customer_id, order_id)
        if order is None:
            raise OrderNotFoundError
        return order
