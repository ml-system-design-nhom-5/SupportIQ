"""The route of `getKbDocumentVersion` and the mapping of its body (UI-20)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from pydantic import MISSING, ValidationError

from app.generated import KbDocumentId, KbDocumentVersionTag
from app.generated import KbDocumentVersion as KbDocumentVersionBody
from app.platform import RequestContractError
from app.platform.web import format_timestamp, json_response, provide
from app.retrieval.application import GetKbDocumentVersion
from app.retrieval.domain import KbDocument


def build_retrieval_router(get_document: GetKbDocumentVersion) -> APIRouter:
    """Build the router of the KB operations.

    Args:
        get_document: The use case of `getKbDocumentVersion`.

    Returns:
        The router with `GET /v1/kb-documents/{document_id}/versions/{version}`. The
        composition root adds the service token check to it.
    """
    router = APIRouter()
    use_case = Depends(provide(get_document))

    @router.get("/v1/kb-documents/{document_id}/versions/{version}")
    async def handle_get_kb_document_version(
        document_id: str,
        version: str,
        get_version: Annotated[GetKbDocumentVersion, use_case],
    ) -> Response:
        identifier = _parameter(KbDocumentId, document_id, "path.document_id")
        tag = _parameter(KbDocumentVersionTag, version, "path.version")
        return json_response(kb_document_body(get_version.execute(identifier.root, tag.root)))

    return router


def kb_document_body(document: KbDocument) -> KbDocumentVersionBody:
    """Map a document version to the contract's `KbDocumentVersion`.

    Args:
        document: The document version.

    Returns:
        The body of `getKbDocumentVersion`.
    """
    end, reviewed = document.effective_end_at, document.last_reviewed_at
    return KbDocumentVersionBody(
        document_id=KbDocumentId(document.document_id),
        version=KbDocumentVersionTag(document.version),
        title=document.title,
        body=document.body,
        policy_key=document.policy_key,
        effective_start_at=format_timestamp(document.effective_start_at),
        effective_end_at=MISSING if end is None else format_timestamp(end),
        owner=document.owner,
        source=document.source,
        last_reviewed_at=MISSING if reviewed is None else format_timestamp(reviewed),
    )


def _parameter[ParameterT: KbDocumentId | KbDocumentVersionTag](
    model: type[ParameterT], value: str, location: str
) -> ParameterT:
    # The schema of each path parameter comes from the contract, through its generated model.
    try:
        return model.model_validate(value, strict=True)
    except ValidationError as error:
        raise RequestContractError((location,)) from error
