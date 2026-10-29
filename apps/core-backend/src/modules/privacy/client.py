from uuid import UUID
from dataclasses import dataclass
from src.contracts import AccessScope
from src.modules.privacy.scanner import scan_and_mask_text

@dataclass
class SanitizedRunContext:
    run_id: UUID
    sanitized_text: str
    token_count: int
    uncertain_pii: bool

async def sanitize_for_run(
    run_id: UUID,
    ticket_id: UUID,
    scope: AccessScope,
    raw_text: str,
) -> SanitizedRunContext:
    # Direct local scanner invocation
    result = scan_and_mask_text(raw_text, run_id=run_id)
    return SanitizedRunContext(
        run_id=run_id,
        sanitized_text=result.sanitized_text,
        token_count=len(result.mappings),
        uncertain_pii=result.uncertain_pii,
    )
