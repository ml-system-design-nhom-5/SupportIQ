"""The routes of `createAnalysis` and `createDraft` (ADR-0005).

The body is read inside each route, after the service token check of the router, so a
request without the token is refused with `401` before its body is read.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from app.generated import SuggestionRequest
from app.platform.web import json_response, parse_json_body, provide
from app.suggestions.api.requests import suggestion_input
from app.suggestions.api.responses import analysis_body, draft_outcome_body
from app.suggestions.application import CreateAnalysis, CreateDraft


def build_suggestions_router(
    create_analysis: CreateAnalysis, create_draft: CreateDraft
) -> APIRouter:
    """Build the router of the suggestion operations.

    Args:
        create_analysis: The use case of `createAnalysis`.
        create_draft: The use case of `createDraft`.

    Returns:
        The router with `POST /v1/analyses` and `POST /v1/drafts`. The composition root adds
        the service token check to it.
    """
    router = APIRouter()
    analysis_use_case = Depends(provide(create_analysis))
    draft_use_case = Depends(provide(create_draft))

    @router.post("/v1/analyses")
    async def handle_create_analysis(
        request: Request, use_case: Annotated[CreateAnalysis, analysis_use_case]
    ) -> Response:
        body = await parse_json_body(request, SuggestionRequest)
        analysis = await use_case.execute(suggestion_input(body))
        return json_response(analysis_body(analysis))

    @router.post("/v1/drafts")
    async def handle_create_draft(
        request: Request, use_case: Annotated[CreateDraft, draft_use_case]
    ) -> Response:
        body = await parse_json_body(request, SuggestionRequest)
        outcome = await use_case.execute(suggestion_input(body))
        return json_response(draft_outcome_body(outcome))

    return router
