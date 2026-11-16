"""Tiny models with random weights, saved like the folders of a release, for tests marked `torch`.

They are built in the test, from a vocabulary of a few words, so nothing is downloaded
(TEST-16). Building and running a model needs torch, which only the `torch` dependency group
installs on Linux, so only tests marked `torch` build one (ADR-0021, Python and dependencies,
statement 2). The tokenizer needs no torch.
"""

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol, cast

from transformers import (
    BertConfig,
    BertModel,
    BertTokenizer,
    DistilBertConfig,
    DistilBertForSequenceClassification,
)

SPECIAL_TOKENS = ("[PAD]", "[UNK]", "[CLS]", "[SEP]", "[MASK]")
WORDS = ("a", "fake", "refund", "to", "the", "card", "my", "order", "is", "late", "where")
# Small sizes, so a model builds and runs in a moment on a CPU.
_HIDDEN_SIZE = 8
_FEED_FORWARD_SIZE = 16
_ATTENTION_HEADS = 2
_POSITIONS = 128


class _SavedModel(Protocol):
    def save_pretrained(self, folder: Path) -> object: ...


def write_tokenizer(folder: Path) -> int:
    """Save a fast, lowercasing WordPiece tokenizer with its configuration in a folder.

    The tokenizer needs no torch, so tests without torch use it too.

    Args:
        folder: The folder, which is created when missing.

    Returns:
        The size of the vocabulary.
    """
    vocabulary = {token: index for index, token in enumerate((*SPECIAL_TOKENS, *WORDS))}
    tokenizer = BertTokenizer(vocab=vocabulary, do_lower_case=True)
    cast("_SavedModel", tokenizer).save_pretrained(folder)
    return len(vocabulary)


def write_classifier(folder: Path, labels: Sequence[str]) -> None:
    """Save a DistilBERT classifier with random weights and its tokenizer in a folder.

    Args:
        folder: The folder, which is created when missing.
        labels: The label of each output, by index.
    """
    vocabulary_size = write_tokenizer(folder)
    config = DistilBertConfig(
        vocab_size=vocabulary_size,
        dim=_HIDDEN_SIZE,
        n_layers=1,
        n_heads=_ATTENTION_HEADS,
        hidden_dim=_FEED_FORWARD_SIZE,
        max_position_embeddings=_POSITIONS,
        id2label=dict(enumerate(labels)),
        label2id={label: output for output, label in enumerate(labels)},
    )
    cast("_SavedModel", DistilBertForSequenceClassification(config)).save_pretrained(folder)


def write_encoder(folder: Path) -> None:
    """Save a BERT encoder with random weights and its tokenizer in a folder.

    Args:
        folder: The folder, which is created when missing.
    """
    vocabulary_size = write_tokenizer(folder)
    config = BertConfig(
        vocab_size=vocabulary_size,
        hidden_size=_HIDDEN_SIZE,
        num_hidden_layers=1,
        num_attention_heads=_ATTENTION_HEADS,
        intermediate_size=_FEED_FORWARD_SIZE,
        max_position_embeddings=_POSITIONS,
    )
    cast("_SavedModel", BertModel(config)).save_pretrained(folder)


def folder_files(folder: Path, prefix: str) -> dict[str, bytes]:
    """Read every file of a folder as the files of an asset.

    Args:
        folder: The folder.
        prefix: The path of the folder inside the release folder.

    Returns:
        The content of each file, by its path inside the release folder.
    """
    return {
        f"{prefix}/{path.relative_to(folder).as_posix()}": path.read_bytes()
        for path in sorted(folder.rglob("*"))
        if path.is_file()
    }
