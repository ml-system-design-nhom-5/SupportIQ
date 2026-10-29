import json
import re
from uuid import UUID
from src.modules.llm.schemas import ValidatedDraft

class InvalidLlmOutputError(Exception):
    pass

URL_PATTERN = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
MARKDOWN_LINK_PATTERN = re.compile(r"\[.*?\]\((https?://.*?)\)", re.IGNORECASE)

def validate_llm_output(
    raw_output: str,
    allowed_citation_ids: set[str],
    run_id: UUID,
) -> ValidatedDraft:
    try:
        # If output has markdown backticks like ```json ... ```, strip them
        cleaned = raw_output.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\n", "", cleaned)
            cleaned = re.sub(r"\n```$", "", cleaned)
        data = json.loads(cleaned)
    except Exception as exc:
        raise InvalidLlmOutputError(f"Raw output is not valid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise InvalidLlmOutputError("Output must be a JSON object")

    body = data.get("body")
    citation_ids = data.get("citation_ids")

    if not isinstance(body, str) or not body.strip():
        raise InvalidLlmOutputError("Field 'body' must be a non-empty string")

    if not isinstance(citation_ids, list) or len(citation_ids) == 0:
        raise InvalidLlmOutputError("Field 'citation_ids' must be a non-empty list of strings")

    for cid in citation_ids:
        if not isinstance(cid, str):
            raise InvalidLlmOutputError("Citation items must be strings")
        if cid not in allowed_citation_ids:
            raise InvalidLlmOutputError(f"Citation ID '{cid}' is not in allowed citations")

    # Disallow URLs and links
    if URL_PATTERN.search(body) or MARKDOWN_LINK_PATTERN.search(body):
        raise InvalidLlmOutputError("Body contains forbidden external URLs or links")

    return ValidatedDraft(body=body.strip(), citation_ids=citation_ids)
