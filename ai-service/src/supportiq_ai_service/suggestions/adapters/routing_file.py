"""The interim format of the routing configuration of a release (DATA-58).

The routing asset holds one JSON file. Its values are tuned on validation data for the model
artifact version that the file records, and the release manifest records the same version
(DATA-56). The sensitive-term list is reviewed by the policy owner and the RAG engineer
(DATA-58). A data contract in `contracts/` replaces this format (ADR-0021, Follow-ups).
"""

from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, model_validator

from supportiq_ai_service.release.assets import (
    AssetFiles,
    AssetVersionText,
    StrictDocument,
    read_json_asset,
)
from supportiq_ai_service.suggestions.adapters.intent_label_field import IntentLabelField
from supportiq_ai_service.suggestions.domain import (
    AuthorityCategory,
    IntentName,
    RoutingConfiguration,
    SensitiveTerm,
)

ROUTING_FORMAT = "supportiq-routing-configuration/interim-1"
# Every list of sensitive intents holds `request_refund` (contracts v1 design, Authority rule).
_REQUIRED_SENSITIVE_INTENT = IntentName("request_refund")
# The sensitive-term list detects legal claims and suspected fraud (contracts v1 design,
# Authority rule; requirements, Interpretations, row 5). A list without a term of either would
# turn that detection off without a word, so it is refused (ERR-17).
_REQUIRED_TERM_CATEGORIES = frozenset(
    {AuthorityCategory.LEGAL_CLAIM, AuthorityCategory.SUSPECTED_FRAUD}
)
# Lowercase words of letters and digits, joined by one space, apostrophe, or hyphen, so a term
# is matched as whole words and never as a regular expression.
_TERM_PATTERN = r"^[a-z0-9]+(?:[ '-][a-z0-9]+)*$"
_TERM_MAX_LENGTH = 100

Probability = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


class _SensitiveTermEntry(StrictDocument):
    term: Annotated[str, StringConstraints(max_length=_TERM_MAX_LENGTH, pattern=_TERM_PATTERN)]
    category: AuthorityCategory


class _RoutingFile(StrictDocument):
    format: Literal["supportiq-routing-configuration/interim-1"]
    version: AssetVersionText
    model_version: AssetVersionText
    min_top_probability: Probability
    min_top_two_gap: Probability
    rerank_weight: Annotated[float, Field(ge=0, allow_inf_nan=False)]
    high_band_min_probability: Probability
    sensitive_intents: Annotated[tuple[IntentLabelField, ...], Field(min_length=1)]
    sensitive_intent_min_probability: Annotated[float, Field(gt=0, le=1, allow_inf_nan=False)]
    sensitive_terms: tuple[_SensitiveTermEntry, ...]

    @model_validator(mode="after")
    def _terms_detect_legal_claims_and_fraud(self) -> Self:
        categories = {entry.category for entry in self.sensitive_terms}
        if not _REQUIRED_TERM_CATEGORIES.issubset(categories):
            message = "the sensitive terms hold a legal claim term and a suspected fraud term"
            raise ValueError(message)
        return self

    @model_validator(mode="after")
    def _values_fit_together(self) -> Self:
        terms = [entry.term for entry in self.sensitive_terms]
        if (
            self.high_band_min_probability < self.min_top_probability
            or len(set(self.sensitive_intents)) != len(self.sensitive_intents)
            or _REQUIRED_SENSITIVE_INTENT not in self.sensitive_intents
            or len(set(terms)) != len(terms)
        ):
            message = "the values of the routing configuration fit together"
            raise ValueError(message)
        return self


def read_routing_configuration(files: AssetFiles, model_version: str) -> RoutingConfiguration:
    """Read the routing asset of a verified release.

    Args:
        files: The files of the routing asset, which holds one file.
        model_version: The model artifact version of the same release.

    Returns:
        The routing configuration.

    Raises:
        ReleaseInvalidError: The asset holds more than one file, or the file breaks the
            format, names another routing version, or was tuned for another model version.
    """
    routing_file = files.sole()
    content = read_json_asset(routing_file, _RoutingFile)
    if content.version != files.version or content.model_version != model_version:
        raise routing_file.invalid()
    return RoutingConfiguration(
        version=content.version,
        model_version=content.model_version,
        min_top_probability=content.min_top_probability,
        min_top_two_gap=content.min_top_two_gap,
        rerank_weight=content.rerank_weight,
        high_band_min_probability=content.high_band_min_probability,
        sensitive_intents=frozenset(content.sensitive_intents),
        sensitive_intent_min_probability=content.sensitive_intent_min_probability,
        sensitive_terms=tuple(
            SensitiveTerm(term=entry.term, category=entry.category)
            for entry in content.sensitive_terms
        ),
    )
