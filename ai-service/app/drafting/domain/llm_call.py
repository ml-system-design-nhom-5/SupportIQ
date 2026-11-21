"""One call of the LLM that drafts a reply, and the port of the writer that makes it.

The LLM has no tools and cannot act: it only writes text, which a schema validates (SEC-25).
The message is pseudonymized, and masked before the call (SEC-06), and every source is data
apart from the instructions (SEC-24). What the LLM writes is a suggestion that staff check and
send themselves (FR-04).
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar, Protocol

from app.platform import AiServiceError, ErrorCode


@dataclass(frozen=True, slots=True)
class PolicySource:
    """A passage of a valid KB document version that the LLM may cite.

    Attributes:
        source_id: The identifier that the LLM writes to cite it, such as `S1`.
        document_id: The document.
        version: The version of the document.
        title: The title of the version.
        snippet: The passage, exactly as the body holds it.
    """

    source_id: str
    document_id: str
    version: str
    title: str
    snippet: str


@dataclass(frozen=True, slots=True)
class OrderFact:
    """One field of the order context that the LLM may cite (ADR-0014).

    Attributes:
        source_id: The identifier that the LLM writes to cite it.
        field: The name of the field in the contract's `OrderContext`.
        value: The value of the field, in the one text form that a segment must repeat.
    """

    source_id: str
    field: str
    value: str


@dataclass(frozen=True, slots=True)
class DraftRequest:
    """What the LLM receives to draft one reply.

    Attributes:
        message: The pseudonymized message, after masking. Confidential.
        intent: The intent label that the draft answers.
        policy_sources: The passages of valid KB document versions.
        order_facts: The fields of the order context that the prompt needs (SEC-05).
        requires_authority: Whether a manager decides the request, so the draft holds
            supporting information only (ESC-03, FR-06).
    """

    message: str
    intent: str
    policy_sources: tuple[PolicySource, ...]
    order_facts: tuple[OrderFact, ...]
    requires_authority: bool


@dataclass(frozen=True, slots=True)
class TokenUsage:
    """The tokens of the LLM requests of one call, retries included, as the provider counts.

    Attributes:
        input_token_count: The input tokens.
        output_token_count: The output tokens, thinking tokens included, which the provider
            bills as output.
    """

    input_token_count: int
    output_token_count: int

    def __add__(self, other: "TokenUsage") -> "TokenUsage":
        """Add the tokens of two requests.

        Args:
            other: The tokens of the other request.

        Returns:
            The tokens of both.
        """
        return TokenUsage(
            input_token_count=self.input_token_count + other.input_token_count,
            output_token_count=self.output_token_count + other.output_token_count,
        )


@dataclass(frozen=True, slots=True)
class WrittenDraft:
    """A draft that the LLM wrote, before the grounding check.

    Attributes:
        text: The draft, with each citation written inline as `[S1]`.
        cited_source_ids: The sources that the LLM states it cited.
        is_clarification: Whether the draft asks the customer for missing information.
        usage: The tokens of the call.
    """

    text: str
    cited_source_ids: tuple[str, ...]
    is_clarification: bool
    usage: TokenUsage


@dataclass(frozen=True, slots=True)
class UnanswerableRequest:
    """The LLM found that its sources do not answer the request, so it wrote no draft.

    Attributes:
        usage: The tokens of the call.
    """

    usage: TokenUsage


type DraftReply = WrittenDraft | UnanswerableRequest


class LlmFailure(StrEnum):
    """Why an LLM call gave no reply, as the contract's reason codes name it (ESC-05)."""

    # The LLM timed out, failed, or was rate-limited, or the egress allow-list refused the call.
    UNAVAILABLE = "llm_unavailable"
    # The output failed schema validation.
    INVALID_OUTPUT = "llm_invalid_output"


class LlmCallError(AiServiceError):
    """An LLM call gave no reply: an outcome of the draft, never a draft (ESC-05)."""

    code: ClassVar[ErrorCode] = ErrorCode.INTERNAL_ERROR

    def __init__(self, failure: LlmFailure, usage: TokenUsage | None = None) -> None:
        """Build the error with a detail that names only the failure.

        Args:
            failure: Why the call gave no reply.
            usage: The tokens of the requests that the LLM answered, even with output that was
                refused; None when it never answered.
        """
        super().__init__(f"The LLM call failed: {failure}.")
        self.failure = failure
        self.usage = usage


class DraftWriter(Protocol):
    """Write a draft with the LLM, within the budget of the LLM step (NFR-07)."""

    def write(self, request: DraftRequest) -> DraftReply:
        """Draft one reply.

        Args:
            request: What the LLM receives.

        Returns:
            The draft before the grounding check, or the finding that the sources do not
            answer the request.

        Raises:
            LlmCallError: The call gave no reply.
        """
        ...
