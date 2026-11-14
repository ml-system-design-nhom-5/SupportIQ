"""Clause splitting for multi-request detection (docs/design/multi-request-detection.md)."""
import pytest

from apps.ml_inference.preprocessing import split_clauses


def test_splits_at_conjunction_and_sentence_end():
    assert split_clauses("Please cancel my order and tell me the refund timeline. Thanks") == [
        "Please cancel my order", "tell me the refund timeline"]
    assert split_clauses("Where is my parcel? Also how much is express shipping?") == [
        "Where is my parcel", "how much is express shipping"]


def test_single_request_returns_empty_list():
    assert split_clauses("Where is my order [ORDER_ID_1] right now?") == []
    assert split_clauses("Hi. Where is my order?") == []  # "Hi" is shorter than min_words


def test_placeholders_and_decimals_are_never_split():
    clauses = split_clauses("Track [ORDER_ID_1] for me and refund the 1.5 dollars fee please")
    assert clauses == ["Track [ORDER_ID] for me", "refund the 1.5 dollars fee please"]


def test_conjunction_inside_a_word_is_not_a_cue():
    assert split_clauses("My brand new sandals arrived broken yesterday") == []


def test_limits_and_validation():
    text = "one two three. four five six. seven eight nine. ten eleven twelve. thirteen fourteen fifteen"
    assert len(split_clauses(text)) == 4
    assert len(split_clauses(text, max_clauses=2)) == 2
    assert split_clauses("cancel it and refund me", min_words=2) == ["cancel it", "refund me"]
    with pytest.raises(ValueError):
        split_clauses("x", max_clauses=1)


def test_autoeval_model_uses_the_serving_splitter_and_skips_clause_latency():
    np = pytest.importorskip("numpy")
    from pipeline.evaluation.autoeval.backends import IntentModel

    class Fake:
        name = "fake"
        id2label = {0: "cancel_order", 1: "shipping_costs"}

        def logits(self, text):
            return np.array([3.0, 0.0]) if "cancel" in text.lower() else np.array([0.0, 3.0])

    model = IntentModel(Fake())
    assert model.predict_clauses("Where is it", 3, 4) is None
    clauses = model.predict_clauses("Cancel my order now and what is the shipping fee", 3, 4)
    assert [c["intent"] for c in clauses] == ["cancel_order", "shipping_costs"]
    assert model.latencies_ms == []


def test_request_filter_drops_background_statements():
    text = "I need to cancel [ORDER_ID_1]. I ordered the wrong colour"
    assert split_clauses(text) == ["I need to cancel [ORDER_ID]", "I ordered the wrong colour"]
    assert split_clauses(text, request_clauses_only=True) == []


def test_request_filter_keeps_questions_imperatives_and_request_phrases():
    text = "Where is my order [ORDER_ID_1]? Send me the invoice and I want to know the refund rules"
    assert split_clauses(text, request_clauses_only=True) == [
        "Where is my order [ORDER_ID]", "Send me the invoice", "I want to know the refund rules"]


def test_question_mark_counts_even_without_question_word():
    assert split_clauses("Refund rules for gifts? Delivery time to Hue?", request_clauses_only=True) == [
        "Refund rules for gifts", "Delivery time to Hue"]


def test_additive_cue_keeps_every_clause():
    text = "What is the return window for shoes? Also my parcel has been stuck for a week"
    assert split_clauses(text, request_clauses_only=True) == [
        "What is the return window for shoes", "my parcel has been stuck for a week"]


def test_is_request_clause():
    from apps.ml_inference.preprocessing import is_request_clause

    assert is_request_clause("Please check my refund")
    assert is_request_clause("my refund status", ended_with_question=True)
    assert not is_request_clause("I sent the item back on the 3rd")


def test_ensemble_backend_averages_logits_and_checks_labels():
    np = pytest.importorskip("numpy")
    from pipeline.evaluation.autoeval.backends import EnsembleBackend

    class B:
        name = "fake"

        def __init__(self, z, labels=None):
            self.z, self.id2label = np.array(z), labels or {0: "a", 1: "b"}

        def logits(self, text):
            return self.z

    ens = EnsembleBackend([B([1.0, 3.0]), B([3.0, 1.0])])
    assert ens.logits("x").tolist() == [2.0, 2.0]
    with pytest.raises(ValueError):
        EnsembleBackend([B([0, 0]), B([0, 0], {0: "b", 1: "a"})])
