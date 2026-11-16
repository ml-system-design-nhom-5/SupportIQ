"""The routing configuration of a release holds the values of DATA-58, for one model version."""

import copy
from collections.abc import Callable
from pathlib import Path

import pytest

from supportiq_ai_service.suggestions.adapters.routing_file import read_routing_configuration
from supportiq_ai_service.suggestions.domain import (
    AuthorityCategory,
    IntentName,
    RoutingConfiguration,
    SensitiveTerm,
)
from tests.unit.release.fakes import EXAMPLE_VERSIONS
from tests.unit.release.release_folder import (
    ROUTING_DOCUMENT,
    AssetFileChanges,
    JsonDocument,
    asset_refusal,
    json_file,
    verified_release,
)

ROUTING_PATH = "routing/routing.json"
MODEL_VERSION = EXAMPLE_VERSIONS.model_version


def test_the_routing_configuration_is_read_with_its_values(tmp_path: Path) -> None:
    files = verified_release(tmp_path).asset_files("routing")

    assert read_routing_configuration(files, MODEL_VERSION) == RoutingConfiguration(
        version=EXAMPLE_VERSIONS.routing_version,
        model_version=MODEL_VERSION,
        min_top_probability=0.5,
        min_top_two_gap=0.1,
        rerank_weight=0.2,
        high_band_min_probability=0.9,
        sensitive_intents=frozenset({IntentName("request_refund"), IntentName("payment_issue")}),
        sensitive_intent_min_probability=0.2,
        sensitive_terms=(
            SensitiveTerm("fake legal term", AuthorityCategory.LEGAL_CLAIM),
            SensitiveTerm("fake fraud term", AuthorityCategory.SUSPECTED_FRAUD),
        ),
    )


def test_a_configuration_tuned_for_another_model_version_is_refused(tmp_path: Path) -> None:
    files = verified_release(tmp_path).asset_files("routing")

    error = asset_refusal(lambda: read_routing_configuration(files, "intent-model-sample-2"))

    assert (error.asset, error.file_path) == ("routing", ROUTING_PATH)


def _routing(change: Callable[[JsonDocument], None]) -> AssetFileChanges:
    document = copy.deepcopy(ROUTING_DOCUMENT)
    change(document)
    return {"routing": {ROUTING_PATH: json_file(document)}}


def _add_terms(*entries: JsonDocument) -> Callable[[JsonDocument], None]:
    # The terms of the fixture stay, so only the added entries can break the list.
    def change(document: JsonDocument) -> None:
        document["sensitive_terms"].extend(entries)

    return change


def _add_legal_terms(*terms: str) -> Callable[[JsonDocument], None]:
    return _add_terms(*({"term": term, "category": "legal_claim"} for term in terms))


def _keep_terms_of(category: str) -> Callable[[JsonDocument], None]:
    def change(document: JsonDocument) -> None:
        document["sensitive_terms"] = [
            entry for entry in document["sensitive_terms"] if entry["category"] == category
        ]

    return change


# Each way to break the routing configuration; every refusal names the routing file.
ROUTING_BREAKS: dict[str, AssetFileChanges] = {
    "another routing version": _routing(lambda document: document.update(version="routing-2")),
    "another model version in the file": _routing(
        lambda document: document.update(model_version="intent-model-sample-2")
    ),
    "a probability above 1": _routing(lambda document: document.update(min_top_probability=1.1)),
    "a negative gap": _routing(lambda document: document.update(min_top_two_gap=-0.1)),
    "a negative rerank weight": _routing(lambda document: document.update(rerank_weight=-1)),
    "a high band below the minimum": _routing(
        lambda document: document.update(high_band_min_probability=0.4)
    ),
    "no sensitive intent": _routing(lambda document: document.update(sensitive_intents=[])),
    "no request_refund": _routing(
        lambda document: document.update(sensitive_intents=["payment_issue"])
    ),
    "an unknown intent": _routing(
        lambda document: document.update(sensitive_intents=["request_refund", "refund_now"])
    ),
    "an intent twice": _routing(
        lambda document: document.update(sensitive_intents=["request_refund", "request_refund"])
    ),
    "a sensitive probability of 0": _routing(
        lambda document: document.update(sensitive_intent_min_probability=0)
    ),
    "an uppercase term": _routing(_add_legal_terms("Lawyer")),
    "a term that looks like a pattern": _routing(_add_legal_terms("law(yer)?")),
    "a term with two spaces": _routing(_add_legal_terms("small  claims")),
    "a term twice": _routing(_add_legal_terms("lawyer", "lawyer")),
    "an unknown category": _routing(_add_terms({"term": "lawyer", "category": "angry_customer"})),
    "no sensitive term": _routing(lambda document: document.update(sensitive_terms=[])),
    "no legal claim term": _routing(_keep_terms_of("suspected_fraud")),
    "no suspected fraud term": _routing(_keep_terms_of("legal_claim")),
    "a string for a number": _routing(lambda document: document.update(rerank_weight="0.2")),
    "an unknown field": _routing(lambda document: document.update(per_intent_thresholds={})),
}


@pytest.mark.parametrize("name", sorted(ROUTING_BREAKS))
def test_a_routing_configuration_that_breaks_its_format_is_refused(
    tmp_path: Path, name: str
) -> None:
    files = verified_release(tmp_path, ROUTING_BREAKS[name]).asset_files("routing")

    error = asset_refusal(lambda: read_routing_configuration(files, MODEL_VERSION))

    assert (error.asset, error.file_path) == ("routing", ROUTING_PATH)


def test_a_routing_asset_of_two_files_is_refused(tmp_path: Path) -> None:
    files = verified_release(
        tmp_path, {"routing": {"routing/extra.json": json_file(ROUTING_DOCUMENT)}}
    ).asset_files("routing")

    error = asset_refusal(lambda: read_routing_configuration(files, MODEL_VERSION))

    assert (error.asset, error.file_path) == ("routing", None)
