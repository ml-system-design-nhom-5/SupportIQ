"""The routing configuration of the first release is a valid routing asset (ADR-0025, DATA-58).

The release command copies `ai-service/routing/<routing_version>/routing.json` into the routing
asset of a release. The first version holds the values of `main`, which were not tuned, and all
53 sensitive terms of `main` (ADR-0025).
"""

from collections import Counter
from pathlib import Path

import pytest

from supportiq_ai_service.release.manifest import verify_release
from supportiq_ai_service.suggestions.adapters.routing_file import read_routing_configuration
from supportiq_ai_service.suggestions.domain import (
    AuthorityCategory,
    IntentName,
    RoutingConfiguration,
)
from tests.unit.release.release_folder import JsonDocument, with_changes, write_release

ROUTING_VERSION = "main-untuned-v1"
MODEL_VERSION = "v1.0.0"
ROUTING_SOURCE = Path(__file__).parents[3] / "routing" / ROUTING_VERSION / "routing.json"
FRAUD = AuthorityCategory.SUSPECTED_FRAUD
LEGAL = AuthorityCategory.LEGAL_CLAIM
DISPUTE = AuthorityCategory.TRANSACTION_DISPUTE
EXCEPTION = AuthorityCategory.POLICY_EXCEPTION
# The 53 terms of `SENSITIVE_AUTHORITY_PATTERN` in `apps/core_backend/safety.py` of `main` at
# `19ece5d`, as whole-word terms, sorted (ADR-0025, Sensitive terms).
MAIN_TERMS = (
    ("approve an exception", EXCEPTION),
    ("approve exception", EXCEPTION),
    ("ask for an exception", EXCEPTION),
    ("ask for exception", EXCEPTION),
    ("attorney", LEGAL),
    ("charge not authorized", FRAUD),
    ("chargeback", DISPUTE),
    ("court", LEGAL),
    ("debit not authorized", FRAUD),
    ("defraud", FRAUD),
    ("defrauded", FRAUD),
    ("demand an exception", EXCEPTION),
    ("demand exception", EXCEPTION),
    ("dispute", DISPUTE),
    ("disputed", DISPUTE),
    ("disputes", DISPUTE),
    ("exception clause", EXCEPTION),
    ("exception request", EXCEPTION),
    ("exception to", EXCEPTION),
    ("fraud", FRAUD),
    ("fraudulent", FRAUD),
    ("grant an exception", EXCEPTION),
    ("grant exception", EXCEPTION),
    ("lawsuit", LEGAL),
    ("lawyer", LEGAL),
    ("legal action", LEGAL),
    ("legal claim", LEGAL),
    ("legal dispute", LEGAL),
    ("make an exception", EXCEPTION),
    ("make exception", EXCEPTION),
    ("manager exception", EXCEPTION),
    ("need an exception", EXCEPTION),
    ("need exception", EXCEPTION),
    ("not authorized by me", FRAUD),
    ("not authorized to charge", FRAUD),
    ("order exception", EXCEPTION),
    ("order not authorized", FRAUD),
    ("payment not authorized", FRAUD),
    ("policy exception", EXCEPTION),
    ("purchase not authorized", FRAUD),
    ("refund exception", EXCEPTION),
    ("refund not authorized", FRAUD),
    ("request an exception", EXCEPTION),
    ("request exception", EXCEPTION),
    ("return exception", EXCEPTION),
    ("seek an exception", EXCEPTION),
    ("seek exception", EXCEPTION),
    ("supervisor exception", EXCEPTION),
    ("transaction not authorized", FRAUD),
    ("unauthorized", FRAUD),
    ("want an exception", EXCEPTION),
    ("want exception", EXCEPTION),
    ("warranty exception", EXCEPTION),
)


def _name_the_first_routing_version(document: JsonDocument) -> None:
    document["assets"]["routing"]["version"] = ROUTING_VERSION


@pytest.fixture
def routing(tmp_path: Path) -> RoutingConfiguration:
    assets = with_changes({"routing": {"routing/routing.json": ROUTING_SOURCE.read_bytes()}})
    manifest = write_release(tmp_path, change=_name_the_first_routing_version, assets=assets)
    files = verify_release(manifest).asset_files("routing")
    return read_routing_configuration(files, MODEL_VERSION)


def test_the_routing_source_is_the_only_file_of_its_version() -> None:
    assert [path.name for path in ROUTING_SOURCE.parent.iterdir()] == ["routing.json"]


def test_the_first_routing_configuration_holds_the_values_of_main_for_v1_0_0(
    routing: RoutingConfiguration,
) -> None:
    assert (routing.version, routing.model_version) == (ROUTING_VERSION, MODEL_VERSION)
    assert (
        routing.min_top_probability,
        routing.min_top_two_gap,
        routing.rerank_weight,
        routing.high_band_min_probability,
        routing.sensitive_intent_min_probability,
    ) == (0.7, 0.1, 0.15, 0.9, 0.1)
    assert routing.sensitive_intents == {
        IntentName("cancel_order"),
        IntentName("request_refund"),
        IntentName("return_product"),
        IntentName("payment_issue"),
    }


def test_the_first_routing_configuration_keeps_the_53_terms_of_main_with_their_categories(
    routing: RoutingConfiguration,
) -> None:
    # Each term exactly, so a typo or a term in another category fails (ADR-0025).
    assert sorted((term.term, term.category) for term in routing.sensitive_terms) == list(
        MAIN_TERMS
    )
    assert Counter(category for _term, category in MAIN_TERMS) == {
        EXCEPTION: 28,
        FRAUD: 14,
        LEGAL: 7,
        DISPUTE: 4,
    }
