"""The prompts of a release: the instructions that drafting sends to the LLM (DATA-38).

The prompts asset holds two text files. Their sources are versioned files in
`ai-service/prompts/<prompt_version>/`, reviewed like code, and the release command copies
them into the release, where the manifest checks them (DATA-56). Every result reports the
version of the asset as its `prompt_version` (ARCH-39).
"""

from dataclasses import dataclass

from app.release.assets import AssetFiles, read_text_asset

# The instructions of every drafting call, which keep the message, the KB, and the order
# context apart from the instructions as data (SEC-24).
SYSTEM_PROMPT_FILE_NAME = "drafting-system.txt"
# The instructions added when authority is required: the draft holds supporting information
# only, and decides, approves, or promises nothing (ESC-03, FR-06).
REQUIRES_AUTHORITY_PROMPT_FILE_NAME = "drafting-requires-authority.txt"
_PROMPT_FILE_NAMES = (SYSTEM_PROMPT_FILE_NAME, REQUIRES_AUTHORITY_PROMPT_FILE_NAME)


@dataclass(frozen=True, slots=True)
class DraftingPrompts:
    """The prompts of one release.

    Attributes:
        version: The version of the prompts asset, which every result reports.
        system_instructions: The instructions of every drafting call.
        requires_authority_instructions: The instructions added when authority is required.
    """

    version: str
    system_instructions: str
    requires_authority_instructions: str


def read_drafting_prompts(files: AssetFiles) -> DraftingPrompts:
    """Read the prompts asset of a verified release.

    Args:
        files: The files of the prompts asset.

    Returns:
        The prompts.

    Raises:
        ReleaseInvalidError: The asset holds another file than the two prompts, or a prompt
            is not UTF-8 or holds only spaces.
    """
    if len(files.files) != len(_PROMPT_FILE_NAMES):
        # Every prompt file of the release is read, so an extra file would be dead weight that
        # nobody reviews.
        raise files.invalid()
    return DraftingPrompts(
        version=files.version,
        system_instructions=read_text_asset(files.named(SYSTEM_PROMPT_FILE_NAME)),
        requires_authority_instructions=read_text_asset(
            files.named(REQUIRES_AUTHORITY_PROMPT_FILE_NAME)
        ),
    )
