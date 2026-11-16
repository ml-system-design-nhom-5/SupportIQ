"""The usage of a draft outcome stays within the caps of the contract, or is not sent."""

import pytest

from supportiq_ai_service.drafting import TokenPrices, TokenUsage
from supportiq_ai_service.suggestions.domain import LlmUsage
from supportiq_ai_service.suggestions.domain.usage import (
    MAX_COST_MICRO_USD,
    MAX_TOKEN_COUNT,
    UsageOutOfRangeError,
    contract_usage,
)

# Fixture prices, never the prices of the provider.
PRICES = TokenPrices(1_000, 2_000)


def test_the_usage_and_its_cost_are_reported() -> None:
    assert contract_usage(TokenUsage(1_000, 500), PRICES) == LlmUsage(1_000, 500, 2)


def test_token_counts_at_the_caps_are_reported() -> None:
    usage = contract_usage(TokenUsage(MAX_TOKEN_COUNT, MAX_TOKEN_COUNT), PRICES)

    # One million tokens at each price: 1 000 + 2 000 micro-dollars.
    assert (
        usage.cost_micro_usd
        == PRICES.input_micro_usd_per_million_tokens + PRICES.output_micro_usd_per_million_tokens
    )


@pytest.mark.parametrize(
    "usage", [TokenUsage(MAX_TOKEN_COUNT + 1, 0), TokenUsage(0, MAX_TOKEN_COUNT + 1)]
)
def test_a_token_count_above_its_cap_is_not_reported(usage: TokenUsage) -> None:
    with pytest.raises(UsageOutOfRangeError):
        contract_usage(usage, PRICES)


def test_a_cost_above_its_cap_is_not_reported() -> None:
    prices = TokenPrices(MAX_COST_MICRO_USD + 1, 0)

    with pytest.raises(UsageOutOfRangeError):
        contract_usage(TokenUsage(MAX_TOKEN_COUNT, 0), prices)
    assert contract_usage(TokenUsage(MAX_TOKEN_COUNT, 0), TokenPrices(MAX_COST_MICRO_USD, 0))
