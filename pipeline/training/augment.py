"""Label-preserving text noise for robustness training of the intent model.

Bitext instructions are clean, templated English; real customers write in lowercase, drop
punctuation, abbreviate and mistype.  This module produces noisy variants of *training* rows only
(never the hold-out test set or any file under data/benchmarks/) so the model sees that variation.
"""

from __future__ import annotations

import random
import re
from typing import Callable

import pandas as pd

from apps.ml_inference.preprocessing import PLACEHOLDER_TYPES

ABBREVIATIONS = {
    "please": ["pls", "plz"], "you": ["u"], "your": ["ur", "yr"], "are": ["r"], "thanks": ["thx", "ty"],
    "thank": ["thx"], "because": ["bc", "cuz"], "with": ["w/"], "without": ["w/o"], "about": ["abt"],
    "tomorrow": ["tmrw"], "today": ["2day"], "message": ["msg"], "information": ["info"],
    "account": ["acct"], "number": ["no.", "num"], "order": ["ordr"], "people": ["ppl"],
    "want": ["wanna"], "going to": ["gonna"], "know": ["kno"], "really": ["rly"], "before": ["b4"],
}

PREFIXES = ["hi", "hello", "hey", "hi there", "good morning", "excuse me", "quick question", "um", "so"]
SUFFIXES = ["thanks", "thank you", "asap", "please help", "pls", "urgent", "?", "??", "!!"]
STOPWORDS = {"i", "a", "an", "the", "to", "do", "can", "could", "would", "you", "me", "is", "it", "of",
             "how", "what", "where", "when", "please", "help", "want", "need", "my", "for", "be", "will"}

# QWERTY neighbours for substitution typos.
_KEYBOARD_ROWS = ["qwertyuiop", "asdfghjkl", "zxcvbnm"]
_NEIGHBOURS: dict[str, str] = {}
for _row in _KEYBOARD_ROWS:
    for _i, _ch in enumerate(_row):
        _NEIGHBOURS[_ch] = _row[max(0, _i - 1):_i] + _row[_i + 1:_i + 2]


def typo_word(word: str, rng: random.Random) -> str:
    """Apply one swap / drop / duplicate / neighbour-key edit inside the word."""
    if len(word) < 3:
        return word
    i = rng.randrange(1, len(word) - 1)
    op = rng.choice(["swap", "drop", "dup", "key"])
    if op == "swap":
        return word[:i] + word[i + 1] + word[i] + word[i + 2:]
    if op == "drop":
        return word[:i] + word[i + 1:]
    if op == "dup":
        return word[:i] + word[i] + word[i:]
    neighbours = _NEIGHBOURS.get(word[i].lower())
    return word[:i] + rng.choice(neighbours) + word[i + 1:] if neighbours else word


def add_typos(text: str, rng: random.Random) -> str:
    words = text.split()
    candidates = [i for i, w in enumerate(words) if len(w) >= 4 and w.isalpha()]
    for i in rng.sample(candidates, min(rng.randint(1, 3), len(candidates))):
        words[i] = typo_word(words[i], rng)
    return " ".join(words)


def lowercase_strip(text: str, rng: random.Random) -> str:
    return re.sub(r"[?.!,;:']", "", text.lower())


def abbreviate(text: str, rng: random.Random) -> str:
    out = text.lower()
    for full, short in ABBREVIATIONS.items():
        if rng.random() < 0.7:
            out = re.sub(rf"\b{re.escape(full)}\b", rng.choice(short), out)
    return out


def add_filler(text: str, rng: random.Random) -> str:
    if rng.random() < 0.6:
        text = f"{rng.choice(PREFIXES)}{rng.choice([',', '', ' -'])} {text}"
    if rng.random() < 0.6:
        text = f"{text} {rng.choice(SUFFIXES)}"
    return text


PRODUCTS = ["bed sheet set", "wireless earbuds", "rice cooker", "phone case", "running shoes", "desk lamp",
            "air fryer", "backpack", "blender", "office chair", "water bottle", "laptop stand"]
_ORDER_WORDS = re.compile(r"\b(my|the|an|this|that)\s+(order|purchase|package|parcel|shipment|delivery)\b", re.I)


def random_order_id(rng: random.Random) -> str:
    """An order reference as the classifier sees it in service: pseudonymized and normalized (DATA-59).

    ``backend`` replaces every identifier with ``[ORDER_ID_n]`` before text leaves it, and the shared
    preprocessing maps that to ``[ORDER_ID]``; raw identifiers never reach the model.
    """
    return rng.choice(["[ORDER_ID]", "[ORDER_ID]", "no. [ORDER_ID]", "#[ORDER_ID]"])


def random_context_clause(rng: random.Random) -> str:
    """A short factual aside (date, amount, product) that does not change what is being asked."""
    templates = [
        lambda: f"i placed it {rng.randint(2, 21)} days ago",
        lambda: f"ordered on {rng.randint(1, 28)}/{rng.randint(1, 12)}",
        lambda: f"it was the {rng.choice(PRODUCTS)}",
        lambda: f"paid {rng.randint(1, 99) * 10000:,} vnd",
        lambda: f"total was ${rng.randint(5, 300)}",
        lambda: f"bought it {rng.choice(['last week', 'yesterday', 'last tuesday', 'this morning'])}",
    ]
    return rng.choice(templates)()


def inject_entities(text: str, rng: random.Random) -> str:
    """Attach an order reference and/or a date, amount or product, as real tickets do; label unchanged."""
    out = text
    match = _ORDER_WORDS.search(out)
    if match and rng.random() < 0.8:
        out = out[:match.end()] + f" {random_order_id(rng)}" + out[match.end():]
    if rng.random() < 0.5:
        sep = rng.choice([" - ", ", ", ". "])
        out = f"{out.rstrip('?.! ')}{sep}{random_context_clause(rng)}"
    return out


def keywordize(text: str, rng: random.Random) -> str:
    """Telegraphic style: keep content words only ("refund status order 2 weeks")."""
    words = [w for w in re.sub(r"[?.!,;:']", "", text.lower()).split() if w not in STOPWORDS]
    return " ".join(words) if len(words) >= 2 else text


# Order matters: entities are injected before casing/typo noise so they get the same treatment.
OPS: list[Callable[[str, random.Random], str]] = [inject_entities, add_typos, lowercase_strip, abbreviate, add_filler, keywordize]


_PLACEHOLDER_ANY_CASE = re.compile(r"\[(" + "|".join(PLACEHOLDER_TYPES) + r")\]", re.I)


def restore_placeholders(text: str) -> str:
    """Placeholders are inserted by ``backend``, not typed by the customer, so noise never changes their case."""
    return _PLACEHOLDER_ANY_CASE.sub(lambda match: f"[{match.group(1).upper()}]", text)


def make_variant(text: str, rng: random.Random) -> str:
    """Apply 1-3 distinct noise operations in a fixed relative order; never return the input unchanged."""
    chosen = sorted(rng.sample(range(len(OPS)), rng.randint(1, 3)))
    out = text
    for idx in chosen:
        out = OPS[idx](out, rng)
    out = restore_placeholders(re.sub(r"\s+", " ", out).strip())
    if out == text:
        out = restore_placeholders(add_typos(lowercase_strip(text, rng), rng))
    return out or text


def augment_frame(
    df: pd.DataFrame,
    *,
    variants_per_row: int = 1,
    fraction: float = 1.0,
    seed: int = 42,
    text_col: str = "instruction",
) -> pd.DataFrame:
    """Return noisy copies of ``fraction`` of the rows (``variants_per_row`` each), labels unchanged.

    Variant rows keep ``sample_id`` with an ``::aug<k>`` suffix so membership evidence still traces
    back to the original training sample.
    """
    if not 0.0 < fraction <= 1.0:
        raise ValueError("fraction must be in (0, 1]")
    rng = random.Random(seed)
    base = df.sample(frac=fraction, random_state=seed) if fraction < 1.0 else df
    rows = []
    for _, row in base.iterrows():
        for k in range(variants_per_row):
            new = row.copy()
            new[text_col] = make_variant(str(row[text_col]), rng)
            new["sample_id"] = f"{row['sample_id']}::aug{k}"
            rows.append(new)
    return pd.DataFrame(rows, columns=df.columns).reset_index(drop=True)
