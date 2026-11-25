"""Fixtures of the contract layer: the contract of ai-service."""

import pytest
from schemathesis import BaseSchema

from tests.contract.documented import load_contract


@pytest.fixture(scope="session")
def contract() -> BaseSchema:
    """Load `contracts/ai-service.openapi.yaml` with its relative references.

    Returns:
        The contract.
    """
    return load_contract()
