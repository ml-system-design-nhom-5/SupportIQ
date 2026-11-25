"""The BGE encoder of `main`, loaded from the index asset of a release.

It embeds with CLS pooling and L2 normalization, as `main` did, and puts the query prefix of the
index before each query. It loads only from the folder of the encoder in the release, never
from the network (`local_files_only`, ADR-0018, Egress), and it falls back to nothing: a
failure stops startup or fails the request.

This module needs torch, which only the `torch` dependency group installs on Linux, so only the
composition root imports it, and only its own tests, marked `torch`, run it (ADR-0021, Python
and dependencies, statement 2).
"""

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Protocol, cast

import numpy as np
from numpy.typing import NDArray
from transformers import AutoModel, AutoTokenizer

from app.release import ReleaseInvalidError, ReleaseInvalidReason
from app.retrieval.adapters.in_memory_index import Vectors, l2_normalized
from app.retrieval.adapters.index_file import IndexConfiguration
from app.retrieval.domain import RetrievalError

_TENSOR_FORMAT = "pt"
_OFFSETS_KEY = "offset_mapping"


class _Tensor(Protocol):
    def __getitem__(self, index: object) -> "_Tensor": ...

    def detach(self) -> "_Tensor": ...

    def cpu(self) -> "_Tensor": ...

    def numpy(self) -> NDArray[np.float32]: ...


class _EncoderOutput(Protocol):
    last_hidden_state: _Tensor


class _Encoder(Protocol):
    def __call__(self, **inputs: object) -> _EncoderOutput: ...

    def eval(self) -> object: ...

    def requires_grad_(self, requires_grad: bool) -> object: ...


class _Tokenizer(Protocol):
    is_fast: bool

    def __call__(self, text: str | list[str], **options: object) -> Mapping[str, object]: ...


class _Loader(Protocol):
    def from_pretrained(self, directory: Path, *, local_files_only: bool) -> object: ...


class BgeEncoder:
    """Implement the `TextEncoder` of the index with the BGE encoder of a release."""

    def __init__(
        self, configuration: IndexConfiguration, tokenizer: _Tokenizer, model: _Encoder
    ) -> None:
        """Keep the loaded tokenizer and model of the encoder.

        Args:
            configuration: The configuration of the index asset.
            tokenizer: The fast tokenizer of the encoder.
            model: The encoder, in evaluation mode and without gradients.
        """
        self._configuration = configuration
        self._tokenizer = tokenizer
        self._model = model

    def token_spans(self, text: str) -> Sequence[tuple[int, int]]:
        """Return the character span of each token of a text, without special tokens.

        Args:
            text: The text.

        Returns:
            The spans, in order.
        """
        encoding = self._tokenizer(text, add_special_tokens=False, return_offsets_mapping=True)
        offsets = cast("Sequence[Sequence[int]]", encoding[_OFFSETS_KEY])
        return tuple((start, end) for start, end in offsets)

    def encode_passages(self, texts: Sequence[str]) -> Vectors:
        """Embed passages of the KB, one row for each.

        Args:
            texts: The passages.

        Returns:
            Their L2-normalized vectors.

        Raises:
            RetrievalError: The encoder failed.
        """
        return self._encode(list(texts))

    def encode_query(self, text: str) -> Vectors:
        """Embed one query with the query prefix of the index.

        Args:
            text: The query.

        Returns:
            Its L2-normalized vector.

        Raises:
            RetrievalError: The encoder failed.
        """
        return self._encode([f"{self._configuration.query_prefix}{text.strip()}"])[0]

    def _encode(self, texts: list[str]) -> Vectors:
        inputs = self._tokenizer(
            texts,
            max_length=self._configuration.encoder_max_length,
            padding=True,
            truncation=True,
            return_tensors=_TENSOR_FORMAT,
        )
        try:
            # CLS pooling: the vector of the first token of each text.
            hidden = self._model(**inputs).last_hidden_state
            vectors = hidden[:, 0].detach().cpu().numpy()
        except RuntimeError as error:
            raise RetrievalError from error
        return l2_normalized(vectors)


def load_bge_encoder(configuration: IndexConfiguration) -> BgeEncoder:
    """Load the encoder of an index asset from its folder only.

    Args:
        configuration: The configuration of the index asset, which `read_index_configuration`
            checked.

    Returns:
        The encoder.

    Raises:
        ReleaseInvalidError: The model library cannot load the encoder, or its tokenizer gives
            no token spans.
    """
    try:
        tokenizer = cast(
            "_Tokenizer",
            cast("_Loader", AutoTokenizer).from_pretrained(
                configuration.encoder_directory, local_files_only=True
            ),
        )
        model = cast(
            "_Encoder",
            cast("_Loader", AutoModel).from_pretrained(
                configuration.encoder_directory, local_files_only=True
            ),
        )
    except (OSError, ValueError) as error:
        raise ReleaseInvalidError(ReleaseInvalidReason.ASSET_INVALID, asset="index") from error
    if not tokenizer.is_fast:
        # Only a fast tokenizer gives the token spans that keep each snippet a passage.
        raise ReleaseInvalidError(ReleaseInvalidReason.ASSET_INVALID, asset="index")
    model.eval()
    # No parameter needs a gradient, so an embedding builds no graph and keeps no memory.
    model.requires_grad_(False)
    return BgeEncoder(configuration, tokenizer, model)
