"""The usage of the LLM that a draft outcome reports, within the limits of the contract.

The contract caps each token count at 1 000 000 and the cost at 10 000 000 micro-dollars
(`LlmUsage`). The settings keep the sum of the two prices at most 10 000 000, so the cost stays
within its cap whenever the token counts do. A count above its cap is not cut: the output is
refused as `llm_invalid_output`, without usage, so no number outside the contract is sent
(project lead, 2026-11-16).
"""

from supportiq_ai_service.drafting import TokenPrices, TokenUsage, cost_micro_usd
from supportiq_ai_service.suggestions.domain.draft import LlmUsage

MAX_TOKEN_COUNT = 1_000_000
MAX_COST_MICRO_USD = 10_000_000


class UsageOutOfRangeError(Exception):
    """The usage of an LLM call is beyond what the contract can report."""


def contract_usage(usage: TokenUsage, prices: TokenPrices) -> LlmUsage:
    """Return the usage of an LLM call and its cost, as the contract reports them.

    Args:
        usage: The tokens of the call, retries included.
        prices: The prices of the model.

    Returns:
        The usage with its cost.

    Raises:
        UsageOutOfRangeError: A token count or the cost is above the cap of the contract.
    """
    cost = cost_micro_usd(usage, prices)
    if (
        usage.input_token_count > MAX_TOKEN_COUNT
        or usage.output_token_count > MAX_TOKEN_COUNT
        or cost > MAX_COST_MICRO_USD
    ):
        raise UsageOutOfRangeError
    return LlmUsage(
        input_token_count=usage.input_token_count,
        output_token_count=usage.output_token_count,
        cost_micro_usd=cost,
    )
