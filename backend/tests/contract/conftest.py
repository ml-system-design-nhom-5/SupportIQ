"""Fixtures of the contract layer: the contract, and empty tables for each test."""

import asyncio
from pathlib import Path

import pytest
import schemathesis
from schemathesis import BaseSchema

from tests.integration.database import WorkerDatabase, empty_every_table

CONTRACT_FILE = Path(__file__).parents[3] / "contracts" / "backend.openapi.yaml"


@pytest.fixture(scope="session")
def contract() -> BaseSchema:
    """Load `contracts/backend.openapi.yaml` with its relative references.

    Returns:
        The contract.
    """
    return schemathesis.openapi.from_path(CONTRACT_FILE)  # pyright: ignore[reportUnknownMemberType]  # Schemathesis leaves PathLike unparametrized, #3


@pytest.fixture(autouse=True)
def empty_tables(worker_database: WorkerDatabase) -> None:
    """Start every test from empty tables, so no test sees the data of another (TEST-17).

    Args:
        worker_database: The database of the worker.
    """
    asyncio.run(empty_every_table(worker_database))
