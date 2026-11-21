"""The console's read of a KB document version, for the citation view (UI-20).

The handler is thin: the role check runs first, so another role gets `403` whatever path it
sent; then it parses the path, calls the use case, and maps the result (ARCH-14, PY-36). The
document is returned as ai-service serves it, and absent optional fields stay absent (backend
ticket workflow design, Data and contracts).
"""

from dataclasses import dataclass
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from pydantic import RootModel, ValidationError

from app.accounts import AuthenticatedSession
from app.generated import KbDocumentId as ContractKbDocumentId
from app.generated import KbDocumentVersion as ContractKbDocumentVersion
from app.generated import KbDocumentVersionTag as ContractKbDocumentVersionTag
from app.platform.web import (
    RequestDependency,
    format_optional_timestamp,
    format_timestamp,
    json_response,
    provide,
)
from app.suggestions.application import GetConsoleKbDocumentVersion
from app.suggestions.domain import (
    KbDocumentId,
    KbDocumentVersion,
    KbDocumentVersionNotFoundError,
    KbDocumentVersionTag,
)

KB_DOCUMENT_VERSION_PATH = "/v1/console/kb-documents/{document_id}/versions/{version}"


@dataclass(frozen=True, slots=True)
class ConsoleKbDocumentRoutes:
    """What the route of the console's KB document read needs from the composition root.

    Attributes:
        get_document_version: The read.
        current_session: The session of a request.
    """

    get_document_version: GetConsoleKbDocumentVersion
    current_session: RequestDependency[AuthenticatedSession]


def parse_kb_document_id(raw: str) -> KbDocumentId:
    """Read the `document_id` path parameter (contract `KbDocumentIdPath`).

    Args:
        raw: The path parameter.

    Returns:
        The KB document.

    Raises:
        KbDocumentVersionNotFoundError: It does not match the pattern of `KbDocumentId`, so
            it names no document; the operation documents no `422`.
    """
    return KbDocumentId(_match_pattern(ContractKbDocumentId, raw))


def parse_kb_document_version_tag(raw: str) -> KbDocumentVersionTag:
    """Read the `version` path parameter (contract `KbDocumentVersionPath`).

    Args:
        raw: The path parameter.

    Returns:
        The version of the document.

    Raises:
        KbDocumentVersionNotFoundError: It does not match the pattern of
            `KbDocumentVersionTag`, so it names no version; the operation documents no `422`.
    """
    return KbDocumentVersionTag(_match_pattern(ContractKbDocumentVersionTag, raw))


def to_kb_document_version_view(document: KbDocumentVersion) -> ContractKbDocumentVersion:
    """Map a KB document version to the contract, without changing any value.

    Args:
        document: The document version.

    Returns:
        The contract model; `effective_end_at` and `last_reviewed_at` are absent when the
        document has none.
    """
    return ContractKbDocumentVersion(
        document_id=ContractKbDocumentId(document.document_id),
        version=ContractKbDocumentVersionTag(document.version),
        title=document.title,
        body=document.body,
        policy_key=document.policy_key,
        effective_start_at=format_timestamp(document.effective_start_at),
        effective_end_at=format_optional_timestamp(document.effective_end_at),
        owner=document.owner,
        source=document.source,
        last_reviewed_at=format_optional_timestamp(document.last_reviewed_at),
    )


def build_console_kb_documents_router(routes: ConsoleKbDocumentRoutes) -> APIRouter:
    """Build the router of the console's KB document read.

    Args:
        routes: The use case and the session dependency.

    Returns:
        The router.
    """
    router = APIRouter()
    current_session = Depends(routes.current_session)
    get_document_version = Depends(provide(routes.get_document_version))

    @router.get(KB_DOCUMENT_VERSION_PATH, status_code=HTTPStatus.OK)
    async def handle_get_console_kb_document_version(
        document_id: str,
        version: str,
        session: Annotated[AuthenticatedSession, current_session],
        use_case: Annotated[GetConsoleKbDocumentVersion, get_document_version],
    ) -> Response:
        use_case.authorize(session.principal)
        document = await use_case.execute(
            parse_kb_document_id(document_id), parse_kb_document_version_tag(version)
        )
        return json_response(to_kb_document_version_view(document))

    return router


def _match_pattern(model: type[RootModel[str]], raw: str) -> str:
    try:
        return model.model_validate(raw, strict=True).root
    except ValidationError as error:
        raise KbDocumentVersionNotFoundError from error
