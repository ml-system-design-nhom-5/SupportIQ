"""How the rules of step 4 read a word (leak fixes design, Layer 1, names, opening paragraphs).

A word is a letter, then letters and combining marks, so a message typed with decomposed
diacritics gives the same words. A word joined to a letter or digit by "-", ".", "/", or "@" is
part of a code, such as "ORD" in "ORD-12345". A rule compares a word with a list after NFC
normalization, and never changes the message.
"""

import unicodedata

# The combining diacritical marks U+0300 to U+036F, written with `chr` so that the source holds
# no lone combining character.
MARKS = f"{chr(0x0300)}-{chr(0x036F)}"
WORD_PATTERN = rf"[^\W\d_](?:[^\W\d_]|[{MARKS}])*"
# A word touches no other word character, and no letter or digit through "-", ".", "/", or "@".
NOTHING_JOINED_BEFORE = rf"(?<![\w{MARKS}])(?<![^\W_][-./@])"
NOTHING_JOINED_AFTER = rf"(?![\w{MARKS}])(?![-./@][^\W_])"


def nfc(text: str) -> str:
    """Return a text in Unicode NFC normalization."""
    return unicodedata.normalize("NFC", text)


def word_key(word: str) -> str:
    """Return the form in which a rule compares a word with a list: NFC, then case folding."""
    return nfc(word).casefold()
