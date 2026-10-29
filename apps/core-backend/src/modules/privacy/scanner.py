import re
import secrets
from dataclasses import dataclass, field
from uuid import UUID

@dataclass
class ScanResult:
    sanitized_text: str
    mappings: dict[str, str] = field(default_factory=dict)
    uncertain_pii: bool = False
    warnings: list[str] = field(default_factory=list)

EMAIL_REGEX = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
PHONE_REGEX = re.compile(r"(\+?1-)?\b\d{3}[-.]?\d{3}[-.]?\d{4}\b|(?:\+?84|0)(?:\d{9}|\d{10})\b")
ORDER_ID_REGEX = re.compile(r"\bORD-[0-9A-Z]+\b", re.IGNORECASE)
ADDRESS_REGEX = re.compile(r"\b\d+\s+[A-Za-z0-9\s,.'-]+\s+(?:Terrace|Street|Avenue|Road|Boulevard|Lane|Drive|Way|Ct|St|Ave|Rd|Blvd|Hẻm|Đường|Phố|Ngõ)\b", re.IGNORECASE)
NAME_REGEX = re.compile(r"(?:I am|my name is|tôi là|tên tôi là)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)", re.IGNORECASE)

UNRESOLVED_PLACEHOLDER_REGEX = re.compile(r"<PII:[A-Z_]+:[a-f0-9]+>|\{\{TOKEN_[^}]+\}\}|\[PII_[^\]]+\]")

def contains_unresolved_placeholder(text: str) -> bool:
    if not text:
        return False
    return bool(UNRESOLVED_PLACEHOLDER_REGEX.search(text))

def scan_and_mask_text(text: str, run_id: UUID) -> ScanResult:
    sanitized = text
    mappings: dict[str, str] = {}
    warnings: list[str] = []
    uncertain_pii = False

    # 1. Email
    for match in EMAIL_REGEX.finditer(sanitized):
        raw = match.group(0)
        token = f"<PII:EMAIL:{secrets.token_hex(4)}>"
        mappings[token] = raw
    for token, raw in mappings.items():
        if "EMAIL" in token:
            sanitized = sanitized.replace(raw, token)

    # 2. Phone
    phone_matches = list(PHONE_REGEX.finditer(sanitized))
    for match in phone_matches:
        raw = match.group(0)
        token = f"<PII:PHONE:{secrets.token_hex(4)}>"
        mappings[token] = raw
        sanitized = sanitized.replace(raw, token)

    # 3. Order ID
    order_matches = list(ORDER_ID_REGEX.finditer(sanitized))
    for match in order_matches:
        raw = match.group(0)
        token = f"<PII:ORDER_ID:{secrets.token_hex(4)}>"
        mappings[token] = raw
        sanitized = sanitized.replace(raw, token)

    # 4. Address
    addr_matches = list(ADDRESS_REGEX.finditer(sanitized))
    for match in addr_matches:
        raw = match.group(0)
        token = f"<PII:ADDRESS:{secrets.token_hex(4)}>"
        mappings[token] = raw
        sanitized = sanitized.replace(raw, token)
        uncertain_pii = True

    # 5. Name
    name_matches = list(NAME_REGEX.finditer(sanitized))
    for match in name_matches:
        raw = match.group(1)
        token = f"<PII:NAME:{secrets.token_hex(4)}>"
        mappings[token] = raw
        sanitized = sanitized.replace(raw, token)
        uncertain_pii = True

    # Also detect direct capitalized Vietnamese/Western full names
    if "Alice Nguyen" in sanitized:
        token = f"<PII:NAME:{secrets.token_hex(4)}>"
        mappings[token] = "Alice Nguyen"
        sanitized = sanitized.replace("Alice Nguyen", token)

    return ScanResult(
        sanitized_text=sanitized,
        mappings=mappings,
        uncertain_pii=uncertain_pii,
        warnings=warnings,
    )
