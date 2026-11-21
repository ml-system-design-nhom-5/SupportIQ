"""Tests of the shop's read use cases with a fake gateway (ADR-0013, SEC-17)."""

import pytest

from app.accounts import (
    AccountId,
    Authorizer,
    CustomerId,
    CustomerPrincipal,
    ForbiddenRoleError,
    InternalPrincipal,
    InternalRole,
)
from app.commerce import (
    GetShopOrder,
    GetShopProduct,
    ListShopOrders,
    ListShopProducts,
    OrderId,
    OrderNotFoundError,
    ProductId,
    ProductNotFoundError,
    ProductPosition,
)
from app.platform import DatabaseUnavailableError
from tests.unit.commerce.fakes import FakeCommerceGateway, build_order, build_product
from tests.unit.platform.fakes import FakeTransactionRunner, RecordingEventRecorder

pytestmark = pytest.mark.anyio

CUSTOMER_ID = CustomerId("10000000-0000-4000-8000-000000000001")
OTHER_CUSTOMER_ID = CustomerId("10000000-0000-4000-8000-000000000002")
CUSTOMER = CustomerPrincipal(AccountId("account-of-the-customer"), CUSTOMER_ID)
ADMIN = InternalPrincipal(AccountId("account-of-the-admin"), InternalRole.ADMIN)
LAMP = build_product("Desk lamp", "PRD-1001")
MUG = build_product("Mug", "PRD-1002")
FIRST_ORDER = build_order("ORD-20901")
SECOND_ORDER = build_order("ORD-20902")


def authorizer() -> Authorizer:
    return Authorizer(RecordingEventRecorder())


def gateway() -> FakeCommerceGateway:
    return FakeCommerceGateway(
        products=(LAMP, MUG),
        orders={CUSTOMER_ID: (FIRST_ORDER, SECOND_ORDER)},
    )


def list_products() -> ListShopProducts:
    return ListShopProducts(FakeTransactionRunner(gateway()), authorizer())


def list_orders() -> ListShopOrders:
    return ListShopOrders(FakeTransactionRunner(gateway()), authorizer())


def get_order() -> GetShopOrder:
    return GetShopOrder(FakeTransactionRunner(gateway()), authorizer())


def get_product() -> GetShopProduct:
    return GetShopProduct(FakeTransactionRunner(gateway()), authorizer())


async def test_product_page_names_the_next_position_when_more_follow() -> None:
    page = await list_products().execute(CUSTOMER, None, 1)

    assert page.items == (LAMP,)
    assert page.next_position == ProductPosition("Desk lamp", ProductId("PRD-1001"))


async def test_product_page_continues_after_the_position() -> None:
    position = ProductPosition("Desk lamp", ProductId("PRD-1001"))

    page = await list_products().execute(CUSTOMER, position, 1)

    assert page.items == (MUG,)
    assert page.next_position is None


async def test_empty_catalog_gives_an_empty_page() -> None:
    use_case = ListShopProducts(FakeTransactionRunner(FakeCommerceGateway()), authorizer())

    page = await use_case.execute(CUSTOMER, None, 20)

    assert page.items == ()
    assert page.next_position is None


async def test_known_product_is_returned() -> None:
    product = await get_product().execute(CUSTOMER, ProductId("PRD-1002"))

    assert product == MUG


async def test_unknown_product_is_not_found() -> None:
    with pytest.raises(ProductNotFoundError):
        await get_product().execute(CUSTOMER, ProductId("PRD-9999"))


async def test_order_page_names_the_position_of_the_next_item() -> None:
    page = await list_orders().execute(CUSTOMER, 0, 1)

    assert page.items == (FIRST_ORDER,)
    assert page.next_position == 1


async def test_order_page_continues_from_the_position() -> None:
    page = await list_orders().execute(CUSTOMER, 1, 1)

    assert page.items == (SECOND_ORDER,)
    assert page.next_position is None


async def test_order_list_of_another_customer_is_empty() -> None:
    other = CustomerPrincipal(AccountId("other"), OTHER_CUSTOMER_ID)

    page = await list_orders().execute(other, 0, 20)

    assert page.items == ()


async def test_order_of_the_caller_is_returned() -> None:
    order = await get_order().execute(CUSTOMER, OrderId("ORD-20902"))

    assert order == SECOND_ORDER


async def test_order_of_another_customer_is_not_found() -> None:
    other = CustomerPrincipal(AccountId("other"), OTHER_CUSTOMER_ID)

    with pytest.raises(OrderNotFoundError):
        await get_order().execute(other, OrderId("ORD-20902"))


async def test_unknown_order_is_not_found() -> None:
    with pytest.raises(OrderNotFoundError):
        await get_order().execute(CUSTOMER, OrderId("ORD-99999"))


async def test_every_shop_read_refuses_an_internal_role() -> None:
    with pytest.raises(ForbiddenRoleError):
        list_products().authorize(ADMIN)
    with pytest.raises(ForbiddenRoleError):
        list_orders().authorize(ADMIN)
    with pytest.raises(ForbiddenRoleError):
        await get_product().execute(ADMIN, ProductId("PRD-1001"))
    with pytest.raises(ForbiddenRoleError):
        await get_order().execute(ADMIN, OrderId("ORD-20901"))


@pytest.fixture(params=["transaction", "gateway"])
def failing_runner(request: pytest.FixtureRequest) -> FakeTransactionRunner[FakeCommerceGateway]:
    failure = DatabaseUnavailableError()
    outcomes = {
        "transaction": FakeTransactionRunner(gateway(), begin_failure=failure),
        "gateway": FakeTransactionRunner(FakeCommerceGateway(failure=failure)),
    }
    return outcomes[request.param]


async def test_failure_of_a_port_reaches_the_product_list(
    failing_runner: FakeTransactionRunner[FakeCommerceGateway],
) -> None:
    with pytest.raises(DatabaseUnavailableError):
        await ListShopProducts(failing_runner, authorizer()).execute(CUSTOMER, None, 20)


async def test_failure_of_a_port_reaches_the_product_read(
    failing_runner: FakeTransactionRunner[FakeCommerceGateway],
) -> None:
    with pytest.raises(DatabaseUnavailableError):
        await GetShopProduct(failing_runner, authorizer()).execute(CUSTOMER, ProductId("PRD-1"))


async def test_failure_of_a_port_reaches_the_order_list(
    failing_runner: FakeTransactionRunner[FakeCommerceGateway],
) -> None:
    with pytest.raises(DatabaseUnavailableError):
        await ListShopOrders(failing_runner, authorizer()).execute(CUSTOMER, 0, 20)


async def test_failure_of_a_port_reaches_the_order_read(
    failing_runner: FakeTransactionRunner[FakeCommerceGateway],
) -> None:
    with pytest.raises(DatabaseUnavailableError):
        await GetShopOrder(failing_runner, authorizer()).execute(CUSTOMER, OrderId("ORD-20901"))
