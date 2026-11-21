"""Schemathesis over every operation and the health checks (CON-27, TEST-15).

Hypothesis runs derandomized, so each run sends the same requests. Each generated request
carries the service token, because the scheme leaves its value to the caller. The pipeline
and the KB are fakes that answer the contract's examples. Every response is checked against
the contract: status, media type, headers, and schema. This test follows the one of backend.
"""

from collections.abc import Iterator, Mapping

import pytest
import schemathesis
from hypothesis import HealthCheck, settings
from schemathesis import APIOperation, BaseSchema, Case
from schemathesis.core.adapter import OperationParameter, ResponsesContainer
from schemathesis.python.asgi import shutdown_lifespans

from tests.contract.documented import CONTRACT_FILE
from tests.integration.application import SERVICE_TOKEN_HEADERS, build_app, build_ports
from tests.unit.platform.fakes import RecordingEventRecorder

EXAMPLES_PER_OPERATION = 25
# The contract: a value that is not a valid `traceparent` is ignored and never causes `422`, so
# no value of it can make a request invalid. A unit test covers that case, and generation
# leaves the header out, because negative testing would expect a rejection.
TRACEPARENT_REFERENCE = {"$ref": "#/components/parameters/Traceparent"}
# The document version that the fake KB holds, so seeded requests reach it.
SEEDED_PATH_VALUES = {"path.document_id": "SAMPLE-REFUND-001", "path.version": "1.0"}
# The contract: a `kb_version` other than the loaded one, and a timestamp that matches the
# pattern but is no real time, return `422`; a document version outside the loaded KB returns
# `404`. So on these operations a request can match the schema and still get a 4xx. Every
# other operation keeps the strict default of the check.
OPERATIONS_WITH_A_DOCUMENTED_4XX_FOR_VALID_DATA = [
    "createAnalysis",
    "createDraft",
    "getKbDocumentVersion",
]
ACCEPTED_STATUSES = ["2xx", "3xx", "401", "404", "422", "5xx"]
SUPPRESSED_HEALTH_CHECKS = [
    HealthCheck.function_scoped_fixture,
    HealthCheck.too_slow,
    HealthCheck.filter_too_much,
]

type GeneratedOperation = APIOperation[
    OperationParameter, ResponsesContainer[object], object, BaseSchema
]
type GeneratedCase = Case[GeneratedOperation]


def load_contract(generation_mode: str, parameters: Mapping[str, str]) -> BaseSchema:
    config = schemathesis.Config.from_dict(  # pyright: ignore[reportUnknownMemberType]  # Schemathesis leaves its dict argument unparametrized, as in backend (#3)
        {
            "generation": {
                "mode": generation_mode,
                "max-examples": EXAMPLES_PER_OPERATION,
                "deterministic": True,
                # Each request carries the service token, set below.
                "with-security-parameters": False,
            },
            "parameters": dict(parameters),
            "operations": [
                {
                    "include-operation-id": OPERATIONS_WITH_A_DOCUMENTED_4XX_FOR_VALID_DATA,
                    "checks": {
                        "positive_data_acceptance": {"expected-statuses": ACCEPTED_STATUSES}
                    },
                }
            ],
        }
    )
    schema = schemathesis.openapi.from_path(CONTRACT_FILE, config=config)  # pyright: ignore[reportUnknownMemberType]  # Schemathesis leaves PathLike unparametrized, as in backend (#3)
    leave_out_traceparent(schema)
    schema.app = build_app(build_ports(), RecordingEventRecorder())
    return schema


def leave_out_traceparent(schema: BaseSchema) -> None:
    for path_item in schema.raw_schema["paths"].values():
        for operation in path_item.values():
            operation["parameters"] = [
                parameter
                for parameter in operation["parameters"]
                if parameter != TRACEPARENT_REFERENCE
            ]


def call_and_validate(case: GeneratedCase) -> None:
    case.call_and_validate(headers=dict(SERVICE_TOKEN_HEADERS))  # pyright: ignore[reportUnknownMemberType]  # Schemathesis leaves `Case` unparametrized in its checks, as in backend (#3)


@pytest.fixture
def generated_requests_schema() -> Iterator[BaseSchema]:
    yield load_contract("all", {})
    shutdown_lifespans()


@pytest.fixture
def seeded_requests_schema() -> Iterator[BaseSchema]:
    yield load_contract("positive", SEEDED_PATH_VALUES)
    shutdown_lifespans()


generated_requests = schemathesis.pytest.from_fixture("generated_requests_schema")
seeded_requests = schemathesis.pytest.from_fixture("seeded_requests_schema")


@generated_requests.parametrize()  # pyright: ignore[reportUnknownMemberType, reportUntypedFunctionDecorator]  # the decorator of Schemathesis is untyped, as in backend (#3)
@settings(max_examples=EXAMPLES_PER_OPERATION, suppress_health_check=SUPPRESSED_HEALTH_CHECKS)
def test_generated_requests_match_the_contract(case: GeneratedCase) -> None:
    call_and_validate(case)


@seeded_requests.parametrize()  # pyright: ignore[reportUnknownMemberType, reportUntypedFunctionDecorator]  # the decorator of Schemathesis is untyped, as in backend (#3)
@settings(max_examples=EXAMPLES_PER_OPERATION, suppress_health_check=SUPPRESSED_HEALTH_CHECKS)
def test_requests_about_seeded_records_match_the_contract(case: GeneratedCase) -> None:
    call_and_validate(case)
