"""The interim format of the retrieval index of a release: the encoder and how to index the KB.

The index asset is `index.json` and the files of the encoder, in a folder of their own that
holds no file of another asset. `ai-service` builds the index at startup from the KB of the
same release with these values, as `main` did, so the index version names the encoder, the
chunking, and the KB version together. The encoder loads only from its folder, never from the
network (ADR-0018, Egress). A data contract in `contracts/` replaces this format (ADR-0021,
Follow-ups).
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, model_validator

from app.release.assets import (
    AssetFiles,
    AssetVersionText,
    RelativePath,
    StrictDocument,
    read_json_asset,
)

INDEX_FORMAT = "supportiq-retrieval-index/interim-1"
INDEX_FILE_NAME = "index.json"
# The files that the model library reads from the folder of the encoder. `tokenizer_config.json`
# fixes the tokenizer class and its options, which the library would otherwise guess, so
# queries are tokenized as the KB was. Each is checked against the manifest.
ENCODER_LIBRARY_FILE_NAMES = (
    "config.json",
    "model.safetensors",
    "tokenizer.json",
    "tokenizer_config.json",
)
# BERT-style encoders, such as `BAAI/bge-small-en-v1.5`, hold 512 positions.
_MAX_POSITIONS = 512
_ENCODER_NAME_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}$"
_QUERY_PREFIX_MAX_LENGTH = 200

TokenCount = Annotated[int, Field(ge=1, le=_MAX_POSITIONS)]


class _Encoder(StrictDocument):
    name: Annotated[str, StringConstraints(pattern=_ENCODER_NAME_PATTERN)]
    directory: RelativePath
    query_prefix: Annotated[str, StringConstraints(max_length=_QUERY_PREFIX_MAX_LENGTH)]
    max_length: TokenCount


class _Chunking(StrictDocument):
    max_tokens: TokenCount
    overlap_tokens: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def _overlap_is_shorter_than_a_chunk(self) -> Self:
        if self.overlap_tokens >= self.max_tokens:
            message = "the overlap is shorter than a chunk"
            raise ValueError(message)
        return self


class _IndexFile(StrictDocument):
    format: Literal["supportiq-retrieval-index/interim-1"]
    version: AssetVersionText
    kb_version: AssetVersionText
    encoder: _Encoder
    chunking: _Chunking
    relevance_min_score: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


@dataclass(frozen=True, slots=True)
class IndexConfiguration:
    """How `ai-service` builds and searches the retrieval index of a release.

    Attributes:
        encoder_name: The name of the encoder, for provenance only; it is never downloaded.
        encoder_directory: The folder of the encoder, which holds only files of the index.
        query_prefix: The text that the encoder expects before each query.
        encoder_max_length: The number of tokens that the encoder reads of each text.
        chunk_max_tokens: The number of tokens of each chunk of a KB document version.
        chunk_overlap_tokens: The number of tokens that two chunks in a row share.
        relevance_min_score: The minimum similarity of a relevant chunk, for this encoder; the
            first release serves the untuned value of `main` (ADR-0027).
    """

    encoder_name: str
    encoder_directory: Path
    query_prefix: str
    encoder_max_length: int
    chunk_max_tokens: int
    chunk_overlap_tokens: int
    relevance_min_score: float


def read_index_configuration(files: AssetFiles, kb_version: str) -> IndexConfiguration:
    """Read the index asset of a verified release, without loading the encoder.

    Args:
        files: The files of the index asset.
        kb_version: The KB version of the same release.

    Returns:
        The configuration of the index.

    Raises:
        ReleaseInvalidError: The asset lacks a file, breaks the format, names another index
            or KB version, or holds a file outside `index.json` and the folder of the encoder.
    """
    index_file = files.named(INDEX_FILE_NAME)
    content = read_json_asset(index_file, _IndexFile)
    if content.version != files.version or content.kb_version != kb_version:
        raise index_file.invalid()
    encoder_path = content.encoder.directory
    encoder_directory = files.directory(encoder_path)
    for name in ENCODER_LIBRARY_FILE_NAMES:
        files.file(f"{encoder_path}/{name}")
    for asset_file in files.files:
        # Every file of the index is read: `index.json`, or a file of the encoder.
        if asset_file != index_file and not asset_file.file_path.startswith(f"{encoder_path}/"):
            raise asset_file.invalid()
    return IndexConfiguration(
        encoder_name=content.encoder.name,
        encoder_directory=encoder_directory,
        query_prefix=content.encoder.query_prefix,
        encoder_max_length=content.encoder.max_length,
        chunk_max_tokens=content.chunking.max_tokens,
        chunk_overlap_tokens=content.chunking.overlap_tokens,
        relevance_min_score=content.relevance_min_score,
    )
