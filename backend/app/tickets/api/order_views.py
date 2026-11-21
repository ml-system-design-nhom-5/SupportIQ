"""The order mappings of commerce that the console's views reuse.

The console's order views repeat the shop's order schemas (`ShopOrderLine`, `ShopShipmentView`,
`ShopRefundView`; CODE-48), so they reuse the shop's mapping instead of copying it. tickets
never imports the interface of commerce (ARCH-17): the composition root passes the two
functions in (ARCH-21, ARCH-22).
"""

from collections.abc import Callable
from dataclasses import dataclass

from app.commerce import Money, Order
from app.generated import Money as ContractMoney
from app.generated import ShopOrderView


@dataclass(frozen=True, slots=True)
class OrderViewMappers:
    """The two order mappings of commerce, given by the composition root.

    Attributes:
        to_order_view: Maps an order to the shop's order view, without its shipping address
            and transaction ID.
        to_money: Maps an amount to the contract's `Money`.
    """

    to_order_view: Callable[[Order], ShopOrderView]
    to_money: Callable[[Money], ContractMoney]
