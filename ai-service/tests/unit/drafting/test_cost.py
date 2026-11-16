"""The cost of the tokens of a call is rounded up to a whole micro-dollar (contract `LlmUsage`)."""

import pytest

from supportiq_ai_service.drafting import TokenPrices, TokenUsage, cost_micro_usd

# Fixture prices, never the prices of the provider.
PRICES = TokenPrices(
    input_micro_usd_per_million_tokens=1_000, output_micro_usd_per_million_tokens=2_000
)


@pytest.mark.parametrize(
    ("input_tokens", "output_tokens", "cost"),
    [
        (0, 0, 0),
        (1_000_000, 0, 1_000),
        (0, 1_000_000, 2_000),
        (1, 0, 1),
        (999, 1, 2),
        (1_000, 1_000, 3),
        (1_001, 0, 2),
    ],
)
def test_the_cost_is_the_price_of_each_token_rounded_up(
    input_tokens: int, output_tokens: int, cost: int
) -> None:
    usage = TokenUsage(input_token_count=input_tokens, output_token_count=output_tokens)

    assert cost_micro_usd(usage, PRICES) == cost


def test_tokens_at_no_price_cost_nothing() -> None:
    free = TokenPrices(input_micro_usd_per_million_tokens=0, output_micro_usd_per_million_tokens=0)

    assert cost_micro_usd(TokenUsage(500, 500), free) == 0
