"""The mappings of other features that the console's views reuse, given by the composition root.

The console's views repeat contract schemas that other features map already: the shop's order
schemas, and the `AssetVersions` of the admin area. The same knowledge is mapped once
(CODE-55), and tickets never imports the interface of another feature (ARCH-17), so the
composition root passes the functions in (ARCH-21, ARCH-22).
"""

from collections.abc import Callable
from dataclasses import dataclass

from app.generated import AssetVersions as ContractAssetVersions
from app.suggestions import AssetVersions
from app.tickets.api.order_views import OrderViewMappers


@dataclass(frozen=True, slots=True)
class ConsoleViewMappers:
    """The mappings of commerce and suggestions that the workspace reuses.

    Attributes:
        orders: The order mappings of commerce, for the orders and the order citations.
        to_asset_versions_view: Maps the release and asset versions of ai-service to the
            contract's `AssetVersions`, as the admin area of suggestions does.
    """

    orders: OrderViewMappers
    to_asset_versions_view: Callable[[AssetVersions], ContractAssetVersions]
