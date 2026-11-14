"""Return-channel cues for the routing guard (docs/design/return-channel-guard.md, label definitions D2).

A return request that names a channel belongs to ``return_product_in_store`` or ``return_product_online``, both
outside the 12 supported intents (ESC-02). Pure function, no third-party imports, shared by serving and evaluation.
"""

import re

_RETURN_CHANNEL = re.compile(
    r"\b(?:"
    # in store
    r"(?<!app )store(?! credit)|shops?|branch(?:es)?|outlets?|counter|mall|in person|walk in(?:to)?"
    # remote
    r"|post office|by post|post (?:it|them|my return|the \w+) back|mail|courier|pick ?up|collect"
    r"|website|online return|return (?:it |them |this )?online"
    r")\b",
    re.IGNORECASE,
)


def names_return_channel(text: str) -> bool:
    """True when the message names a return channel: a store or branch, the post, a courier, or the website."""
    return bool(_RETURN_CHANNEL.search(text or ""))
