"""One KB document version, as ai-service serves it for the citation view (UI-20, ARCH-15).

The shared schema `KbDocumentVersion` of both contracts defines every field. The text is
Public, and the identifiers are Internal (contract `KbDocumentVersion`).
"""

from dataclasses import dataclass
from datetime import datetime
from typing import NewType

# The identifier of a KB document, the same for all its versions (contract `KbDocumentId`).
KbDocumentId = NewType("KbDocumentId", str)
# The version of a KB document; with the document, it names one immutable version (contract
# `KbDocumentVersionTag`).
KbDocumentVersionTag = NewType("KbDocumentVersionTag", str)


@dataclass(frozen=True, slots=True)
class KbDocumentVersion:
    """One immutable version of a KB document, in full.

    Attributes:
        document_id: The KB document.
        version: The version of the document.
        title: The title of the version.
        body: The full text, exactly as the KB holds it.
        policy_key: The topic of the policy that the version states.
        effective_start_at: When the version came into effect.
        effective_end_at: When it stopped being in effect; absent when it is open-ended.
        owner: Who owns the policy and reviews it: a role or a team.
        source: Where the text comes from.
        last_reviewed_at: When the owner last reviewed it; absent when the source does not
            provide it.
    """

    document_id: KbDocumentId
    version: KbDocumentVersionTag
    title: str
    body: str
    policy_key: str
    effective_start_at: datetime
    effective_end_at: datetime | None
    owner: str
    source: str
    last_reviewed_at: datetime | None
