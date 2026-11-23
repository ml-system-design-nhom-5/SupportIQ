"""Text preprocessing shared by intent training, evaluation, and serving (DATA-59).

The classifier sees pseudonymized text. Numbered placeholders such as ``[ORDER_ID_1]`` are mapped to their type
alone (``[ORDER_ID]``) so the model learns the type, not the counter. This module has no third-party imports so
that training (``pipeline/``), evaluation, and model serving all call the same function.
"""

import re

# Intents that may lead to a draft: the 12 supported intents except human_agent (docs/design/intent-model-v1.2.md).
DRAFTABLE_INTENTS = frozenset({
    "track_order", "cancel_order", "delivery_time", "delivery_issue", "shipping_costs", "return_policy",
    "return_product", "refund_policy", "request_refund", "refund_status", "payment_issue",
})

# Placeholder types from ADR-0010 (placeholder syntax).
PLACEHOLDER_TYPES = ("NAME", "EMAIL", "PHONE", "CARD", "ADDRESS", "ORDER_ID", "TRACKING_ID", "TRANSACTION_ID", "LITERAL")
_NUMBERED = re.compile(r"\[(" + "|".join(PLACEHOLDER_TYPES) + r")_[1-9][0-9]{0,2}\]")


def normalize_placeholders(text: str) -> str:
    """Map ``[TYPE_n]`` to ``[TYPE]``; every other character is left unchanged."""
    return _NUMBERED.sub(lambda match: f"[{match.group(1)}]", text)


# Clause splitting for multi-request detection (docs/design/multi-request-detection.md).
# Sentence ends split only when followed by whitespace or the end, so decimals ("1.5") and placeholders stay whole.
_SENTENCE_END = re.compile(r"([.?!;]+)(?=\s|$)")
_CONJUNCTION = re.compile(r"\s+(?:as\s+well\s+as|and|also|then|plus|but)\s+", re.IGNORECASE)
_EDGE = re.compile(r"^[\s,:\-]+|[\s,:\-]+$")
DEFAULT_MIN_CLAUSE_WORDS = 3
DEFAULT_MAX_CLAUSES = 4

# Request cues (English, like the model). A clause is a request when it ended with "?", starts with a question word
# or an imperative verb, or contains a request phrase. An additive cue anywhere in the message keeps every clause.
_QUESTION_START = re.compile(
    r"^(?:how|what|what's|when|where|where's|why|which|who|is|are|do|does|did|has|have|can|could|would|will|should|may)\b",
    re.IGNORECASE)
_IMPERATIVE_START = re.compile(
    r"^(?:please\s+)?(?:cancel|track|refund|check|stop|send|tell|explain|update|start|change|close|give|return|connect"
    r"|reset|add|show|find|confirm)\b", re.IGNORECASE)
_REQUEST_PHRASE = re.compile(
    r"\b(?:please|i want|i'd like|i would like|i need|want to|need to|like to|let me know|tell me|send me|help me"
    r"|connect me|show me|give me)\b", re.IGNORECASE)
_ADDITIVE = re.compile(r"\b(?:also|plus|as well as|another thing|one more thing)\b", re.IGNORECASE)


def is_request_clause(clause: str, ended_with_question: bool = False) -> bool:
    """True when the clause asks for something rather than giving background."""
    return bool(ended_with_question or _QUESTION_START.search(clause) or _IMPERATIVE_START.search(clause)
                or _REQUEST_PHRASE.search(clause))


def split_clauses(
    text: str,
    min_words: int = DEFAULT_MIN_CLAUSE_WORDS,
    max_clauses: int = DEFAULT_MAX_CLAUSES,
    request_clauses_only: bool = False,
) -> list[str]:
    """Split a message into clauses at sentence ends and coordinating cues.

    Clauses shorter than ``min_words`` words are dropped. With ``request_clauses_only``, clauses that only give
    background are dropped too, unless the message has an additive cue ("also", "plus"). At most ``max_clauses``
    are kept, in message order. Fewer than two clauses returns ``[]``: callers then classify the whole message only.
    """
    if min_words < 1 or max_clauses < 2:
        raise ValueError("min_words must be >= 1 and max_clauses >= 2")
    normalized = normalize_placeholders(text)
    keep_all = not request_clauses_only or bool(_ADDITIVE.search(normalized))
    parts = _SENTENCE_END.split(normalized)
    clauses = []
    for i in range(0, len(parts), 2):
        question = "?" in (parts[i + 1] if i + 1 < len(parts) else "")
        for part in _CONJUNCTION.split(" " + parts[i] + " "):
            part = _EDGE.sub("", part)
            if len(part.split()) >= min_words and (keep_all or is_request_clause(part, question)):
                clauses.append(part)
    clauses = clauses[:max_clauses]
    return clauses if len(clauses) >= 2 else []
