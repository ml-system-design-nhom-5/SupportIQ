"""Read the spec of a candidate release: `supportiq-release-spec/interim-1`.

The spec is a JSON object with exactly these fields:

- `format`: always `supportiq-release-spec/interim-1`;
- `release_id`: the identifier of the release;
- `assets`: exactly the six assets, each with `version`, `source`, and `path`, and the
  `routing` asset also with `model_version`.

`source` is absolute, or relative to the folder of the spec. A field that is missing, unknown,
or of another type refuses the spec, and so does any rule of `check_spec`.
"""

from collections.abc import Mapping
from pathlib import Path
from typing import cast

from supportiq_release.candidate.domain import (
    ASSET_NAMES,
    AssetName,
    AssetSpec,
    ReleaseSpec,
    SpecInvalidError,
    SpecProblem,
    check_spec,
)
from supportiq_release.files import read_json_file

SPEC_FORMAT = "supportiq-release-spec/interim-1"
_SPEC_FIELDS = frozenset({"format", "release_id", "assets"})
_ASSET_FIELDS = frozenset({"version", "source", "path"})
_ROUTING_FIELDS = _ASSET_FIELDS | {"model_version"}


def read_release_spec(path: Path) -> ReleaseSpec:
    """Read and check the spec of a candidate release.

    Args:
        path: The spec file.

    Returns:
        The spec, with its six assets in the order of the manifest.

    Raises:
        JsonFileInvalidError: The file is missing, a link, or not strict JSON in UTF-8.
        SpecInvalidError: The spec breaks its shape or a rule of `check_spec`.
    """
    document = _object(read_json_file(path).content, _SPEC_FIELDS, None)
    assets = _object(document["assets"], frozenset(ASSET_NAMES), None)
    if document["format"] != SPEC_FORMAT:
        raise SpecInvalidError(SpecProblem.SHAPE_INVALID)
    spec = ReleaseSpec(
        release_id=_text(document["release_id"], None),
        assets=tuple(_asset(name, assets[name]) for name in ASSET_NAMES),
    )
    check_spec(spec)
    return spec


def _asset(name: AssetName, value: object) -> AssetSpec:
    routing = name is AssetName.ROUTING
    fields = _object(value, _ROUTING_FIELDS if routing else _ASSET_FIELDS, name)
    return AssetSpec(
        name=name,
        version=_text(fields["version"], name),
        source=_text(fields["source"], name),
        path=_text(fields["path"], name),
        model_version=_text(fields["model_version"], name) if routing else None,
    )


def _object(value: object, names: frozenset[str], asset: AssetName | None) -> Mapping[str, object]:
    # The cast only names the type that `isinstance` found in a JSON value (PY-12).
    document = cast("dict[str, object]", value) if isinstance(value, dict) else None
    if document is None or frozenset(document) != names:
        raise SpecInvalidError(SpecProblem.SHAPE_INVALID, asset)
    return document


def _text(value: object, asset: AssetName | None) -> str:
    if not isinstance(value, str) or not value:
        raise SpecInvalidError(SpecProblem.SHAPE_INVALID, asset)
    return value
