"""Fixtures of the ticket tests: a signed-in customer with an order."""

from uuid import UUID

import pytest

from tests.integration.builders import DatabaseBuilder
from tests.integration.tickets.shop_requests import (
    Customer,
    sign_in_as_new_customer,
)


@pytest.fixture
async def customer(builder: DatabaseBuilder) -> Customer:
    return await sign_in_as_new_customer(builder)


@pytest.fixture
def customer_id(customer: Customer) -> UUID:
    return customer[0]


@pytest.fixture
def headers(customer: Customer) -> dict[str, str]:
    return customer[1]


@pytest.fixture
async def order_id(builder: DatabaseBuilder, customer_id: UUID) -> str:
    return await builder.order_of_one_product(customer_id)
