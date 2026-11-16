"""The cost of the tokens of an LLM call, at the provider's prices (contract `LlmUsage`).

The prices are settings, taken from the provider's price list for the model in use: no price
is written in code (ARCH-36).
"""

from dataclasses import dataclass

from supportiq_ai_service.drafting.domain.llm_call import TokenUsage

_TOKENS_PER_MILLION = 1_000_000


@dataclass(frozen=True, slots=True)
class TokenPrices:
    """The prices of the tokens of the model in use.

    Attributes:
        input_micro_usd_per_million_tokens: The price of one million input tokens, in
            millionths of a US dollar.
        output_micro_usd_per_million_tokens: The price of one million output tokens, thinking
            tokens included, in millionths of a US dollar.
    """

    input_micro_usd_per_million_tokens: int
    output_micro_usd_per_million_tokens: int


def cost_micro_usd(usage: TokenUsage, prices: TokenPrices) -> int:
    """Return the cost of the tokens of a call, rounded up as the contract states.

    Args:
        usage: The tokens of the call.
        prices: The prices of the model.

    Returns:
        The cost in millionths of a US dollar.
    """
    cost_times_million = (
        usage.input_token_count * prices.input_micro_usd_per_million_tokens
        + usage.output_token_count * prices.output_micro_usd_per_million_tokens
    )
    # Integer division rounded up, so no fraction of a micro-dollar is lost.
    return -(-cost_times_million // _TOKENS_PER_MILLION)
