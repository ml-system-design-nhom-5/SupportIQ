"""The prompts of a release are its two prompt files, read as they are (DATA-38)."""

from pathlib import Path

import pytest

from supportiq_ai_service.drafting.adapters.prompt_files import (
    DraftingPrompts,
    read_drafting_prompts,
)
from tests.unit.release.fakes import EXAMPLE_VERSIONS
from tests.unit.release.release_folder import (
    AssetFileChanges,
    asset_refusal,
    verified_release,
)

SYSTEM_PATH = "prompts/drafting-system.txt"
AUTHORITY_PATH = "prompts/drafting-requires-authority.txt"


def test_the_prompts_are_read_with_the_version_of_their_asset(tmp_path: Path) -> None:
    prompts = read_drafting_prompts(verified_release(tmp_path).asset_files("prompts"))

    assert prompts == DraftingPrompts(
        version=EXAMPLE_VERSIONS.prompt_version,
        system_instructions="A fake system prompt for tests.\n",
        requires_authority_instructions="A fake prompt for authority.\n",
    )


# Each way to break the prompts asset, with the path that the refusal names.
PROMPT_BREAKS: dict[str, tuple[AssetFileChanges, str | None]] = {
    "a third file": ({"prompts": {"prompts/drafting-extra.txt": b"An extra prompt.\n"}}, None),
    "no authority prompt": (
        {"prompts": {AUTHORITY_PATH: None, "prompts/other.txt": b"Another prompt.\n"}},
        None,
    ),
    "a system prompt that is not UTF-8": (
        {"prompts": {SYSTEM_PATH: b"\xff\xfe"}},
        SYSTEM_PATH,
    ),
    "an authority prompt of spaces": ({"prompts": {AUTHORITY_PATH: b"  \n"}}, AUTHORITY_PATH),
}


@pytest.mark.parametrize("name", sorted(PROMPT_BREAKS))
def test_a_prompts_asset_that_breaks_its_format_is_refused(tmp_path: Path, name: str) -> None:
    changes, file_path = PROMPT_BREAKS[name]
    files = verified_release(tmp_path, changes).asset_files("prompts")

    error = asset_refusal(lambda: read_drafting_prompts(files))

    assert (error.asset, error.file_path) == ("prompts", file_path)
