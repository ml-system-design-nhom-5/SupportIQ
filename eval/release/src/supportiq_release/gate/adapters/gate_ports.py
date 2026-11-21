"""The ports that the gate gives a candidate: the real model, unless the case injects a part.

`ai-service` builds a candidate with `CandidatePorts` and holds no fake of its own (ADR-0021,
decision driver 1). The fakes are here:

- the intent model of the candidate answers every case, except a case that injects a
  distribution, which gets exactly that distribution, or a failure of the intent model;
- the search of the candidate answers every case, except a case that injects its failure;
- the LLM step records each call and fails with `llm_unavailable`, so a gate run never calls a
  provider (ADR-0021, CI, statement 2). A case that injects the failure of the LLM gets the
  same step.

The runner sets the case before it sends the requests of that case, so the two models load once.
"""

from collections.abc import Sequence

from app.composition_root import CandidatePorts
from app.drafting import DraftReply, DraftRequest, LlmCallError, LlmFailure
from app.intent import (
    INTENT_LABELS,
    IntentClassifier,
    IntentDistribution,
    IntentModelError,
    IntentProbability,
)
from app.retrieval import DocumentMatch, DocumentSearch, RetrievalError

from supportiq_release.gate.domain import Failure, Injection


class GatePorts:
    """The ports of the gate around one candidate, for one case at a time."""

    def __init__(self, *, labels: Sequence[str] = INTENT_LABELS) -> None:
        """Keep the intent labels that an injected distribution covers.

        Args:
            labels: Every intent label of the model; the 46 labels of `ai-service`.
        """
        self._labels = tuple(labels)
        self._injection: Injection | None = None
        self.llm_calls = 0

    def use(self, injection: Injection | None) -> None:
        """Set the parts that the next requests replace.

        Args:
            injection: The injection of the case, or None for the candidate as it is.
        """
        self._injection = injection

    def candidate_ports(self) -> CandidatePorts:
        """Return the ports for `build_candidate_application`.

        Returns:
            The wrappers of the intent model and the search, and the LLM step of the gate.
        """
        return CandidatePorts(
            classifier=self._classifier, search=self._search, writer=_GateWriter(self)
        )

    @property
    def injection(self) -> Injection | None:
        """Return the injection of the current case."""
        return self._injection

    def distribution(self, listed: Sequence[tuple[str, float]]) -> IntentDistribution:
        """Return an injected distribution over every label, most likely first.

        The listed probabilities are kept exactly, so a case at a threshold tests it. Every
        other label gets an equal share of the rest.

        Args:
            listed: The listed intents and their probabilities.

        Returns:
            The distribution.
        """
        names = {label for label, _probability in listed}
        rest = [label for label in self._labels if label not in names]
        share = (1 - sum(probability for _label, probability in listed)) / len(rest)
        entries = [
            *(IntentProbability(label, probability) for label, probability in listed),
            *(IntentProbability(label, share) for label in rest),
        ]
        # A stable sort keeps the listed intents first when a share equals one of them.
        return IntentDistribution(
            tuple(sorted(entries, key=lambda entry: entry.probability, reverse=True))
        )

    def _classifier(self, real: IntentClassifier) -> IntentClassifier:
        return _GateClassifier(self, real)

    def _search(self, real: DocumentSearch) -> DocumentSearch:
        return _GateSearch(self, real)


class _GateClassifier:
    def __init__(self, ports: GatePorts, real: IntentClassifier) -> None:
        self._ports = ports
        self._real = real

    def classify(self, message: str) -> IntentDistribution:
        injection = self._ports.injection
        if injection is not None and injection.failure is Failure.INTENT_MODEL:
            raise IntentModelError
        if injection is not None and injection.intent_distribution is not None:
            return self._ports.distribution(injection.intent_distribution)
        return self._real.classify(message)


class _GateSearch:
    def __init__(self, ports: GatePorts, real: DocumentSearch) -> None:
        self._ports = ports
        self._real = real

    def search(self, message: str) -> tuple[DocumentMatch, ...]:
        injection = self._ports.injection
        if injection is not None and injection.failure is Failure.RETRIEVAL:
            raise RetrievalError
        return self._real.search(message)


class _GateWriter:
    def __init__(self, ports: GatePorts) -> None:
        self._ports = ports

    def write(self, request: DraftRequest) -> DraftReply:
        del request
        self._ports.llm_calls += 1
        raise LlmCallError(LlmFailure.UNAVAILABLE)
