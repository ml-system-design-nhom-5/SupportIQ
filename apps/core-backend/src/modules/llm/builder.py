import json
from pathlib import Path
from typing import Any
from src.modules.retrieval.schemas import Evidence

def build_egress_payload(
    sanitized_question: str,
    final_intent: str,
    evidence: list[Evidence],
    prompt_version: str = "v1.0.0",
) -> dict[str, Any]:
    prompt_path = Path(__file__).resolve().parent.parent.parent.parent / "config" / "prompts" / f"draft_prompt.{prompt_version}.json"
    if not prompt_path.exists():
        prompt_path = Path("apps/core-backend/config/prompts") / f"draft_prompt.{prompt_version}.json"

    with open(prompt_path, "r", encoding="utf-8") as f:
        template_data = json.load(f)

    system_content = template_data["system_template"]

    evidence_lines = []
    for ev in evidence:
        evidence_lines.append(f"[{ev.citation_id}] ({ev.title or 'KB Document'}): {ev.snippet}")
    evidence_block = "\n".join(evidence_lines) if evidence_lines else "None"

    user_content = template_data["user_template"].format(
        sanitized_question=sanitized_question,
        final_intent=final_intent,
        evidence_block=evidence_block,
    )

    return {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.0,
        "response_format": {"type": "json_object"},
    }
