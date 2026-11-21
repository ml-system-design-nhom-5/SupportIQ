"""Check that the locks of ai-service and eval/release agree on every package they share.

The gate image installs ai-service from ai-service/uv.lock, then the runtime dependencies of
eval/release from eval/release/uv.lock without resolving (eval/release/gate/Dockerfile). A
package that both locks pin at different versions would be replaced without a word, so the
build runs this check between the two steps and stops on any disagreement.

Usage: python check_locks.py <output of uv pip freeze> <output of uv export>
"""

import re
import sys
from pathlib import Path

# A pin as `uv pip freeze` and `uv export --format requirements-txt` write it: a name, `==`, and
# a version, then a marker, a line continuation, or nothing.
_PIN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s;\\]+)")
_ARGUMENT_COUNT = 2
_USAGE = "usage: check_locks.py <output of uv pip freeze> <output of uv export>\n"


def normalized(name: str) -> str:
    """Return the normalized form of a package name (PEP 503).

    Args:
        name: A package name as a pin writes it.

    Returns:
        The name in lowercase, with every run of `-`, `_`, and `.` as one `-`.
    """
    return re.sub(r"[-_.]+", "-", name).lower()


def pins(text: str) -> dict[str, str]:
    """Return the pinned version of each package of a freeze or requirements text.

    Args:
        text: The output of `uv pip freeze` or of `uv export`.

    Returns:
        The version of each package, by normalized name. Lines without a pin, such as
        comments, hashes, and packages installed from a path, are skipped.
    """
    found: dict[str, str] = {}
    for line in text.splitlines():
        match = _PIN.match(line)
        if match is not None:
            # A package on two lines with different markers keeps the version of the last line.
            found[normalized(match.group(1))] = match.group(2)
    return found


def disagreements(installed: dict[str, str], pinned: dict[str, str]) -> list[str]:
    """Describe each package that both sides pin at different versions.

    Args:
        installed: The versions installed from ai-service/uv.lock.
        pinned: The versions that eval/release/uv.lock pins.

    Returns:
        One line per disagreement, with the name and both versions, sorted by name.
    """
    return [
        f"the locks disagree on {name}: ai-service/uv.lock {installed[name]}, "
        f"eval/release/uv.lock {version}"
        for name, version in sorted(pinned.items())
        if name in installed and installed[name] != version
    ]


def main(arguments: list[str]) -> int:
    """Compare the installed packages with the pins of eval/release.

    Args:
        arguments: The path of the output of `uv pip freeze`, then the path of the output of
            `uv export`.

    Returns:
        0 when the locks agree, 1 when they disagree, and 2 on a usage error.
    """
    if len(arguments) != _ARGUMENT_COUNT:
        sys.stderr.write(_USAGE)
        return 2
    installed_path, pinned_path = (Path(argument) for argument in arguments)
    installed = pins(installed_path.read_text(encoding="utf-8"))
    pinned = pins(pinned_path.read_text(encoding="utf-8"))
    found = disagreements(installed, pinned)
    for line in found:
        sys.stderr.write(line + "\n")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
