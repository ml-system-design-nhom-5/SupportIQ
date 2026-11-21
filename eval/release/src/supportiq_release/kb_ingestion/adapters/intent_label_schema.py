"""Read the intent labels from the schema `IntentLabel` of the contracts.

The release command never imports the internals of `ai-service` (ADR-0021, Where the code of
`main` goes, statement 1), so it takes the labels from the contract that `ai-service` itself is
generated from: `contracts/schemas/IntentLabel.yaml`. The file is read without a YAML library,
as one `enum:` line followed only by lines of the form `  - <label>`. A file of any other shape
stops the run, so a change of its layout cannot drop a label unnoticed.
"""

import re
from enum import StrEnum
from pathlib import Path

from supportiq_release.errors import ReleaseCommandError

_ENUM_LINE = "enum:"
_LABEL_LINE = re.compile(r"  - ([a-z][a-z_]*)")


class IntentLabelSchemaProblem(StrEnum):
    """Why the schema file of the intent labels is refused."""

    NOT_A_REGULAR_FILE = "missing_or_not_a_regular_file"
    UNREADABLE = "unreadable_or_not_utf8"
    SHAPE_INVALID = "shape_invalid"


class IntentLabelSchemaInvalidError(ReleaseCommandError):
    """The schema file of the intent labels cannot give the labels."""

    def __init__(self, file_name: str, problem: IntentLabelSchemaProblem) -> None:
        """Build the error with a message that names only the file and the problem.

        Args:
            file_name: The name of the schema file.
            problem: Why the file is refused.
        """
        super().__init__(f"The intent label schema {file_name} is refused: {problem}.")
        self.file_name = file_name
        self.problem = problem


def read_intent_labels(path: Path) -> frozenset[str]:
    """Read the labels of the schema `IntentLabel`.

    Args:
        path: `contracts/schemas/IntentLabel.yaml`.

    Returns:
        Every label of its `enum`.

    Raises:
        IntentLabelSchemaInvalidError: The file is missing, a link, unreadable, not UTF-8, or
            of another shape: no `enum:` line or more than one, a line after it that is not a
            label, no label, or a label twice.
    """
    if path.is_symlink() or not path.is_file():
        raise IntentLabelSchemaInvalidError(path.name, IntentLabelSchemaProblem.NOT_A_REGULAR_FILE)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as error:
        raise IntentLabelSchemaInvalidError(
            path.name, IntentLabelSchemaProblem.UNREADABLE
        ) from error
    if lines.count(_ENUM_LINE) != 1:
        raise IntentLabelSchemaInvalidError(path.name, IntentLabelSchemaProblem.SHAPE_INVALID)
    items = [_LABEL_LINE.fullmatch(line) for line in lines[lines.index(_ENUM_LINE) + 1 :]]
    labels = [item.group(1) for item in items if item is not None]
    if not labels or len(labels) != len(items) or len(set(labels)) != len(labels):
        raise IntentLabelSchemaInvalidError(path.name, IntentLabelSchemaProblem.SHAPE_INVALID)
    return frozenset(labels)
