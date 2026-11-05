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
    pseudonymized, mapping = pseudonymize(msg, known)
    
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
    pseudonymized, mapping = pseudonymize(msg, known)
    assert "[CARD_1]" not in pseudonymized


def test_address_and_contacts_masking():
    known = {}
    msg = "Please ship to 123 Nguyen Hue Boulevard, email test@example.com or call +84901234567."
    pseudonymized, mapping = pseudonymize(msg, known)
    
    assert "[ADDRESS_1]" in pseudonymized
    assert "[EMAIL_1]" in pseudonymized
    assert "[PHONE_1]" in pseudonymized
    
    restored = restore(pseudonymized, mapping)
    assert restored == msg


def test_literal_placeholders_preserved():
    known = {}
    msg = "Customer wrote literal [NAME_1] inside the message."
    pseudonymized, mapping = pseudonymize(msg, known)
    assert "[LITERAL_1]" in pseudonymized
    
    restored = restore(pseudonymized, mapping)
    assert restored == msg


def test_spacy_free_form_ner_masking():
    # Johnathan Smith is NOT in known database values
    known = {}
    msg = "Yesterday, Johnathan Smith told me to ask for an exchange."
    pseudonymized, mapping = pseudonymize(msg, known)
    assert "[NAME_1]" in pseudonymized
    assert "Johnathan Smith" not in pseudonymized
    restored = restore(pseudonymized, mapping)
    assert restored == msg

