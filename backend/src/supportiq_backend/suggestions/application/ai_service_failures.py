"""Log a failed call to ai-service once, with the level that tells a defect from degradation."""

from enum import StrEnum

from supportiq_backend.platform import EventAttributeValue, EventName, EventRecorder
from supportiq_backend.suggestions.domain import AiServiceContractError, AiServiceUnavailableError


class AiServiceOperation(StrEnum):
    """The operations of `ai-service` contract 1.0.0 that backend calls, as logged."""

    CREATE_ANALYSIS = "createAnalysis"
    CREATE_DRAFT = "createDraft"
    GET_ASSET_VERSIONS = "getAssetVersions"


def record_ai_service_failure(
    events: EventRecorder,
    operation: AiServiceOperation,
    error: AiServiceUnavailableError,
    **attributes: EventAttributeValue,
) -> None:
    """Record a failed call at `error` for a defect and at `warning` for degradation.

    A `4xx` or a response outside the contract means that one side broke the contract, which
    is a defect; a timeout, a connection error, or a `5xx` is degradation that backend
    handles (backend ticket workflow design, The `ai-service` client; LOG-15).

    Args:
        events: Where the event is recorded.
        operation: The operation that failed.
        error: The failure.
        **attributes: The IDs of the ticket and the suggestion, when there are some.
    """
    event = (
        EventName.AI_SERVICE_CONTRACT_VIOLATED
        if isinstance(error, AiServiceContractError)
        else EventName.AI_SERVICE_CALL_FAILED
    )
    events.record(event, ai_service_operation=operation.value, **attributes)
