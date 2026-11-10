"""In-memory fake of the `CommerceGateway` port, and test data builders (ARCH-27, TEST-05)."""

from dataclasses import dataclass, field

from supportiq_backend.accounts import CustomerId
from supportiq_backend.commerce import (
    Money,
    Order,
    OrderId,
    OrderLine,
    OrderStatus,
    Product,
    ProductId,
    ProductPosition,
    Shipment,
    ShipmentStatus,
)
from supportiq_backend.platform import BackendError
from tests.unit.platform.fakes import FAKE_CLOCK_START

USD_ONE = Money(100, "USD")


def build_product(name: str = "Desk lamp", product_id: str = "PRD-1001") -> Product:
    """Build a product of the catalog."""
    return Product(ProductId(product_id), name, "A description.", "Home office", USD_ONE)


def build_order(order_id: str = "ORD-20901") -> Order:
    """Build an order with one line, no shipment record, and no refund."""
    return Order(
        order_id=OrderId(order_id),
        status=OrderStatus.PLACED,
        placed_at=FAKE_CLOCK_START,
        order_total=USD_ONE,
        shipping_cost=Money(0, "USD"),
        lines=(OrderLine(ProductId("PRD-1001"), "Desk lamp", 1),),
        shipment=Shipment(ShipmentStatus.NOT_SHIPPED),
        refund=None,
    )


@dataclass(slots=True)
class FakeCommerceGateway:
    """Products in catalog order, and orders by customer in the contract's order."""

    products: tuple[Product, ...] = ()
    orders: dict[CustomerId, tuple[Order, ...]] = field(
        default_factory=dict[CustomerId, tuple[Order, ...]]
    )
    failure: BackendError | None = None

    def _fail_when_chosen(self) -> None:
        if self.failure is not None:
            raise self.failure

    async def load_products(self, after: ProductPosition | None, limit: int) -> tuple[Product, ...]:
        """Return the products after the position."""
        self._fail_when_chosen()
        if after is None:
            return self.products[:limit]
        remaining = tuple(
            product
            for product in self.products
            if (product.name, product.product_id) > (after.name, after.product_id)
        )
        return remaining[:limit]

    async def load_product(self, product_id: ProductId) -> Product | None:
        """Return the product, if any."""
        self._fail_when_chosen()
        return next(
            (product for product in self.products if product.product_id == product_id), None
        )

    async def load_orders(
        self, customer_id: CustomerId, *, position: int, limit: int
    ) -> tuple[Order, ...]:
        """Return the orders of the customer from the position."""
        self._fail_when_chosen()
        return self.orders.get(customer_id, ())[position : position + limit]

    async def load_order(self, customer_id: CustomerId, order_id: OrderId) -> Order | None:
        """Return the order of the customer, if any."""
        self._fail_when_chosen()
        orders = self.orders.get(customer_id, ())
        return next((order for order in orders if order.order_id == order_id), None)

    async def is_order_of_customer(self, customer_id: CustomerId, order_id: OrderId) -> bool:
        """Tell whether the customer has the order."""
        return await self.load_order(customer_id, order_id) is not None
