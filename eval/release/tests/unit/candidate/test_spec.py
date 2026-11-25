"""A spec is refused before any copy when ai-service would refuse what it describes."""

from pathlib import Path

import pytest

from supportiq_release.candidate.adapters import read_release_spec
from supportiq_release.candidate.domain import (
    ASSET_NAMES,
    AssetName,
    AssetSpec,
    SpecInvalidError,
    SpecProblem,
    is_release_path,
)
from tests.unit.candidate.fakes import (
    MODEL_VERSION,
    RELEASE_ID,
    asset_entries,
    spec_document,
    write_spec,
)

ENTRIES = asset_entries()


def _refusal(tmp_path: Path, document: object) -> SpecInvalidError:
    with pytest.raises(SpecInvalidError) as refused:
        read_release_spec(write_spec(tmp_path, document))
    return refused.value


def test_a_spec_gives_its_release_id_and_its_six_assets_in_the_order_of_the_manifest(
    tmp_path: Path,
) -> None:
    spec = read_release_spec(write_spec(tmp_path))

    assert spec.release_id == RELEASE_ID
    assert tuple(asset.name for asset in spec.assets) == ASSET_NAMES
    assert spec.assets[ASSET_NAMES.index(AssetName.ROUTING)] == AssetSpec(
        name=AssetName.ROUTING,
        version="fake-routing-1",
        source="routing.json",
        path="routing/routing.json",
        model_version=MODEL_VERSION,
    )
    assert [asset.model_version for asset in spec.assets] == [
        None,
        None,
        None,
        None,
        MODEL_VERSION,
        None,
    ]


@pytest.mark.parametrize(
    ("document", "asset"),
    [
        pytest.param([spec_document()], None, id="not-an-object"),
        pytest.param({**spec_document(), "format": "another/1"}, None, id="other-format"),
        pytest.param({**spec_document(), "gate_run": None}, None, id="unknown-field"),
        pytest.param({**spec_document(), "release_id": 3}, None, id="release-id-not-text"),
        pytest.param(
            {**spec_document(), "assets": {k: v for k, v in ENTRIES.items() if k != "index"}},
            None,
            id="asset-missing",
        ),
        pytest.param(
            {**spec_document(), "assets": {**ENTRIES, "extra": ENTRIES["kb"]}},
            None,
            id="asset-unknown",
        ),
        pytest.param(
            spec_document(kb={**ENTRIES["kb"], "sha256": "x"}), "kb", id="asset-field-unknown"
        ),
        pytest.param(
            spec_document(
                routing={k: v for k, v in ENTRIES["routing"].items() if k != "model_version"}
            ),
            "routing",
            id="routing-without-model-version",
        ),
        pytest.param(
            spec_document(model={**ENTRIES["model"], "model_version": MODEL_VERSION}),
            "model",
            id="model-version-elsewhere",
        ),
        pytest.param(spec_document(kb={**ENTRIES["kb"], "source": ""}), "kb", id="empty-source"),
    ],
)
def test_a_spec_of_another_shape_is_refused(
    tmp_path: Path, document: object, asset: str | None
) -> None:
    refused = _refusal(tmp_path, document)

    assert (refused.problem, refused.asset) == (SpecProblem.SHAPE_INVALID, asset)


@pytest.mark.parametrize(
    ("document", "problem", "asset"),
    [
        pytest.param(
            {**spec_document(), "release_id": "a release"},
            SpecProblem.RELEASE_ID_INVALID,
            None,
            id="release-id",
        ),
        pytest.param(
            spec_document(kb={**ENTRIES["kb"], "version": "v 9"}),
            SpecProblem.ASSET_VERSION_INVALID,
            "kb",
            id="version",
        ),
        pytest.param(
            spec_document(routing={**ENTRIES["routing"], "model_version": "-model"}),
            SpecProblem.ASSET_VERSION_INVALID,
            "routing",
            id="model-version",
        ),
        pytest.param(
            spec_document(routing={**ENTRIES["routing"], "model_version": "fake-model-2"}),
            SpecProblem.ROUTING_MODEL_MISMATCH,
            "routing",
            id="routing-for-another-model",
        ),
        pytest.param(
            spec_document(kb={**ENTRIES["kb"], "path": "model"}),
            SpecProblem.PATHS_OVERLAP,
            "kb",
            id="same-path",
        ),
        pytest.param(
            spec_document(kb={**ENTRIES["kb"], "path": "model/kb.json"}),
            SpecProblem.PATHS_OVERLAP,
            "kb",
            id="inside-another",
        ),
        pytest.param(
            spec_document(index={**ENTRIES["index"], "path": "kb"}),
            SpecProblem.PATHS_OVERLAP,
            "index",
            id="around-another",
        ),
        pytest.param(
            spec_document(kb={**ENTRIES["kb"], "path": "release-manifest.json"}),
            SpecProblem.PATHS_OVERLAP,
            "kb",
            id="the-manifest",
        ),
        pytest.param(
            spec_document(kb={**ENTRIES["kb"], "path": "Release-Manifest.json"}),
            SpecProblem.PATHS_OVERLAP,
            "kb",
            id="the-manifest-in-another-case",
        ),
        pytest.param(
            spec_document(index={**ENTRIES["index"], "path": "KB"}),
            SpecProblem.PATHS_OVERLAP,
            "index",
            id="around-another-in-another-case",
        ),
    ],
)
def test_a_spec_that_ai_service_would_refuse_is_refused_first(
    tmp_path: Path, document: object, problem: SpecProblem, asset: str | None
) -> None:
    refused = _refusal(tmp_path, document)

    assert (refused.problem, refused.asset) == (problem, asset)


@pytest.mark.parametrize(
    "path", ["/model", "model/../kb", "./model", "model//x", "model/", "a model", "m" * 256]
)
def test_a_path_that_a_release_cannot_hold_is_refused(tmp_path: Path, path: str) -> None:
    refused = _refusal(tmp_path, spec_document(model={**ENTRIES["model"], "path": path}))

    assert (refused.problem, refused.asset) == (SpecProblem.PATH_INVALID, "model")


def test_a_release_path_may_reach_255_characters() -> None:
    assert is_release_path("m" * 255)
    assert not is_release_path("m" * 256)


def test_the_message_of_a_refusal_names_the_problem_and_the_asset_only(tmp_path: Path) -> None:
    refused = _refusal(tmp_path, spec_document(kb={**ENTRIES["kb"], "path": "/secret/text"}))

    assert str(refused) == "The release spec is refused: path_invalid, asset kb."
