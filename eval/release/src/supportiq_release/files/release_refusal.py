"""The text of a release that `ai-service` refuses, the same in every command."""

from app.release.manifest import ReleaseInvalidError


def describe_release_refusal(error: ReleaseInvalidError) -> str:
    """Describe why `ai-service` refuses a release, never with the content of a file.

    Args:
        error: The refusal of `verify_release`, `verify_candidate`, or `read_release_manifest`.

    Returns:
        The reason, then the asset and the path inside the release when the error names them.
    """
    where = "".join(
        f" {name}={value}"
        for name, value in (("asset", error.asset), ("file", error.file_path))
        if value is not None
    )
    return f"{error}{where}"
