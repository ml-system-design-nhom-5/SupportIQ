"""The output folder of a command: complete or absent, never half written.

A command writes every file into a new hidden staging folder next to the output, and moves the
staging folder to the output only when every file is written. On any error the staging folder
is removed, so a failed run leaves nothing behind (ERR-04). The output must be a new or empty
folder, so nothing is ever overwritten, and it may lie neither in `data/raw/` nor inside an
input of the run, so a run never changes its own inputs (DATA-06).
"""

import secrets
import shutil
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from enum import StrEnum
from pathlib import Path

from supportiq_release.errors import ReleaseCommandError

# The folder of raw data, whose files are never edited (DATA-06).
_RAW_DATA = ("data", "raw")
# Eight random bytes, so two runs never pick the same staging name.
_STAGING_TOKEN_BYTES = 8


class OutputFolderProblem(StrEnum):
    """Why an output folder is refused."""

    NOT_EMPTY = "not_a_new_or_empty_folder"
    IN_RAW_DATA = "inside_data_raw"
    IN_AN_INPUT = "inside_an_input"
    NOT_WRITABLE = "not_writable"


class OutputFolderError(ReleaseCommandError):
    """An output folder cannot be written. The message names the problem only."""

    def __init__(self, problem: OutputFolderProblem) -> None:
        """Build the error with a message that names the problem.

        Args:
            problem: Why the output folder is refused.
        """
        super().__init__(f"The output folder is refused: {problem}.")
        self.problem = problem


@contextmanager
def new_output_folder(output: Path, inputs: Sequence[Path]) -> Generator[Path]:
    """Yield a staging folder, and move it to the output when the block ends without an error.

    Args:
        output: The output folder: a path that does not exist, or an empty folder.
        inputs: The files and folders that the run reads.

    Yields:
        The staging folder, a new hidden folder next to the output, to write every file into.

    Raises:
        OutputFolderError: The output is not a new or empty folder, lies in `data/raw/` or
            inside an input, or cannot be written.
    """
    _check_place(output, inputs)
    staging = _make_staging_folder(output)
    try:
        yield staging
        staging.replace(output)
    except OSError as error:
        shutil.rmtree(staging, ignore_errors=True)
        raise OutputFolderError(OutputFolderProblem.NOT_WRITABLE) from error
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _check_place(output: Path, inputs: Sequence[Path]) -> None:
    try:
        taken = output.is_symlink() or (
            output.exists() and (not output.is_dir() or any(output.iterdir()))
        )
    except OSError as error:
        raise OutputFolderError(OutputFolderProblem.NOT_WRITABLE) from error
    if taken:
        raise OutputFolderError(OutputFolderProblem.NOT_EMPTY)
    place = output.resolve()
    if any(place.parts[index : index + 2] == _RAW_DATA for index in range(len(place.parts))):
        raise OutputFolderError(OutputFolderProblem.IN_RAW_DATA)
    # A folder around an input holds that input, so the check of emptiness refuses it already.
    if any(place.is_relative_to(item.resolve()) for item in inputs):
        raise OutputFolderError(OutputFolderProblem.IN_AN_INPUT)


def hidden_partial_path(target: Path) -> Path:
    """Return a new hidden path next to a target, for a file or folder written before a rename.

    Every command writes this way, so a partial entry is always `.<name>.partial-<hex>` next to
    its target, on the same file system, and the rename is atomic. No command reads such an
    entry, and the local run skips every name that starts with `.`.

    Args:
        target: The file or folder that the entry becomes once it is whole.

    Returns:
        `<parent>/.<name>.partial-<16 hexadecimal characters>`, which does not exist yet.
    """
    return target.parent / f".{target.name}.partial-{secrets.token_hex(_STAGING_TOKEN_BYTES)}"


def _make_staging_folder(output: Path) -> Path:
    staging = hidden_partial_path(output)
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        staging.mkdir()
    except OSError as error:
        raise OutputFolderError(OutputFolderProblem.NOT_WRITABLE) from error
    return staging
