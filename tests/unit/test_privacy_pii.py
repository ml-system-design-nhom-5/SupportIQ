from types import SimpleNamespace
import pytest
from apps.backend.tickets.privacy import pseudonymize, restore, luhn_checksum_valid


def test_luhn_algorithm_validation():
    # Valid Visa card
    assert luhn_checksum_valid("4532015112830366") is True
    assert luhn_checksum_valid("4532-0151-1283-0366") is True
    # Invalid card number
    assert luhn_checksum_valid("4532015112830367") is False
    # Too short or too long
    assert luhn_checksum_valid("123456") is False
    assert luhn_checksum_valid("12345678901234567890123") is False


def test_credit_card_masking_and_restoration():
    known = {"NAME": ["Jane Doe"]}
    msg = "My name is Jane Doe and I paid with card 4532-0151-1283-0366 for order ORD-9999."
    # Explicit offline opt-out (require_ner=False) for regex/Luhn/known unit tests without spaCy
    pseudonymized, mapping = pseudonymize(msg, known, require_ner=False)
    
    assert "[CARD_1]" in pseudonymized
    assert "4532-0151-1283-0366" not in pseudonymized
    assert "[NAME_1]" in pseudonymized
    assert "[ORDER_ID_1]" in pseudonymized
    
    restored = restore(pseudonymized, mapping)
    assert restored == msg


def test_invalid_card_not_masked_as_card():
    known = {}
    # Random 16-digit number that fails Luhn
    msg = "Tracking reference 1234567890123453 is in transit."
    pseudonymized, mapping = pseudonymize(msg, known, require_ner=False)
    assert "[CARD_1]" not in pseudonymized


def test_address_and_contacts_masking():
    known = {}
    msg = "Please ship to 123 Nguyen Hue Boulevard, email test@example.com or call +84901234567."
    pseudonymized, mapping = pseudonymize(msg, known, require_ner=False)
    
    assert "[ADDRESS_1]" in pseudonymized
    assert "[EMAIL_1]" in pseudonymized
    assert "[PHONE_1]" in pseudonymized
    
    restored = restore(pseudonymized, mapping)
    assert restored == msg


def test_literal_placeholders_preserved():
    known = {}
    msg = "Customer wrote literal [NAME_1] inside the message."
    pseudonymized, mapping = pseudonymize(msg, known, require_ner=False)
    assert "[LITERAL_1]" in pseudonymized
    
    restored = restore(pseudonymized, mapping)
    assert restored == msg


def test_deterministic_ner_adapter_masks_free_form_person(monkeypatch):
    """Deterministic unit coverage: simulates spaCy NER PERSON detection without external downloads."""
    class MockEnt:
        def __init__(self, label, text):
            self.label_ = label
            self.text = text

    class MockDoc:
        def __init__(self, text, ents):
            self.text = text
            self.ents = ents

    def mock_nlp(text):
        ents = []
        if "Johnathan Smith" in text:
            ents.append(MockEnt("PERSON", "Johnathan Smith"))
        return MockDoc(text, ents)

    monkeypatch.setattr("apps.backend.tickets.privacy._get_spacy_nlp", lambda: mock_nlp)

    known = {}
    msg = "Yesterday, Johnathan Smith told me to ask for an exchange."
    pseudonymized, mapping = pseudonymize(msg, known)
    assert "[NAME_1]" in pseudonymized
    assert "Johnathan Smith" not in pseudonymized
    restored = restore(pseudonymized, mapping)
    assert restored == msg


def test_unavailable_ner_adapter_preserves_known_and_pattern_pii_masks(monkeypatch):
    """When spaCy/NER model is unavailable, regex and known customer PII masks remain safe and functional.
    Note: Full PII recall is not guaranteed for arbitrary uncataloged names when offline without NER."""
    monkeypatch.setattr("apps.backend.tickets.privacy._get_spacy_nlp", lambda: None)

    known = {"NAME": ["Jane Doe"]}
    msg = "Customer Jane Doe (email jane@example.com, phone +84901234567, order ORD-1234) spoke with agent Bob."
    # Explicit offline opt-out (require_ner=False) verifies known/regex masking when NER is intentionally off
    pseudonymized, mapping = pseudonymize(msg, known, require_ner=False)

    assert "[NAME_1]" in pseudonymized
    assert "Jane Doe" not in pseudonymized
    assert "[EMAIL_1]" in pseudonymized
    assert "jane@example.com" not in pseudonymized
    assert "[PHONE_1]" in pseudonymized
    assert "[ORDER_ID_1]" in pseudonymized
    # Uncataloged free-form name 'Bob' is not masked when NER is unavailable, but pipeline does not fail:
    assert "Bob" in pseudonymized

    restored = restore(pseudonymized, mapping)
    assert restored == msg


def _spacy_model_installed() -> bool:
    try:
        import spacy
        spacy.load("en_core_web_sm")
        return True
    except Exception:
        return False


@pytest.mark.skipif(
    not _spacy_model_installed(),
    reason="Optional spaCy library and 'en_core_web_sm' model are not installed in the environment",
)
def test_live_spacy_free_form_ner_masking_integration():
    """Live integration test: verifies free-form PERSON masking only when the spaCy model is installed."""
    known = {}
    msg = "Yesterday, Johnathan Smith told me to ask for an exchange."
    pseudonymized, mapping = pseudonymize(msg, known)
    assert "[NAME_1]" in pseudonymized
    assert "Johnathan Smith" not in pseudonymized
    restored = restore(pseudonymized, mapping)
    assert restored == msg
