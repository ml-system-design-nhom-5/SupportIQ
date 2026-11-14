"""DATA-59: one placeholder normalization for training, evaluation, and serving."""
import random

from apps.ml_inference.preprocessing import PLACEHOLDER_TYPES, normalize_placeholders
from pipeline.training import augment as A


def test_numbered_placeholders_map_to_their_type():
    assert normalize_placeholders("Where is [ORDER_ID_1]? Ask [NAME_12].") == "Where is [ORDER_ID]? Ask [NAME]."


def test_text_without_placeholders_is_unchanged():
    text = "Refund of 5 to 7 days [S1], not [FOO_1]"
    assert normalize_placeholders(text) == text


def test_every_adr_0010_type_is_covered():
    for kind in PLACEHOLDER_TYPES:
        assert normalize_placeholders(f"[{kind}_3]") == f"[{kind}]"


def test_augmentation_never_inserts_raw_identifiers_and_keeps_placeholder_case():
    rng = random.Random(0)
    for _ in range(300):
        out = A.make_variant("I want to cancel my order please", rng)
        assert "ORD-" not in out.upper()
        assert "[order_id]" not in out
    assert A.restore_placeholders("where is [order_id] now") == "where is [ORDER_ID] now"


def test_serving_and_evaluation_use_the_same_function():
    from pipeline.evaluation.autoeval import backends

    assert backends.normalize_placeholders is normalize_placeholders
