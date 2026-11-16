"""The DistilBERT intent model of `main`, loaded from the model asset of a release.

The model runs inside the `ai-service` process, on the CPU, and only loads, checks, and
predicts: it never trains (ADR-0011, ADR-0021, DATA-37). It loads only from the folder of its
artifact, never from the network (`local_files_only`, ADR-0018, Egress). The regular-expression
fallback, the `/predict` app, the pinned checksums, and the calibration manifest of `main` are
gone: the release manifest checks every file (DATA-56), and the first release has no
calibration, so the scores are the softmax of the outputs (README.md, Known limits).

This module needs torch, which only the `torch` dependency group installs on Linux, so only the
composition root imports it, and only its own tests, marked `torch`, run it (ADR-0021, Python
and dependencies, statement 2).
"""

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Protocol, cast

from transformers import AutoModelForSequenceClassification, AutoTokenizer

from supportiq_ai_service.intent.adapters.model_artifact import ModelArtifact
from supportiq_ai_service.intent.domain import IntentDistribution, distribution_from_logits
from supportiq_ai_service.release import ReleaseInvalidError, ReleaseInvalidReason

_TENSOR_FORMAT = "pt"


class _Logits(Protocol):
    def tolist(self) -> list[list[float]]: ...


class _ClassifierOutput(Protocol):
    logits: _Logits


class _ClassifierConfig(Protocol):
    id2label: Mapping[int, str]


class _Classifier(Protocol):
    config: _ClassifierConfig

    def __call__(self, **inputs: object) -> _ClassifierOutput: ...

    def eval(self) -> object: ...

    def requires_grad_(self, requires_grad: bool) -> object: ...


class _Tokenizer(Protocol):
    def __call__(
        self,
        text: str,
        *,
        max_length: int,
        padding: str,
        truncation: bool,
        return_tensors: str,
    ) -> Mapping[str, object]: ...


class _Loader(Protocol):
    def from_pretrained(self, directory: Path, *, local_files_only: bool) -> object: ...


class DistilBertClassifier:
    """Implement the `IntentClassifier` port with the DistilBERT model of a release."""

    def __init__(self, artifact: ModelArtifact, tokenizer: _Tokenizer, model: _Classifier) -> None:
        """Keep the loaded tokenizer and model of one artifact.

        Args:
            artifact: The checked artifact.
            tokenizer: Its tokenizer.
            model: Its model, in evaluation mode and without gradients.
        """
        self._artifact = artifact
        self._tokenizer = tokenizer
        self._model = model

    def classify(self, message: str) -> IntentDistribution:
        """Classify one message with the preprocessing of the artifact.

        Args:
            message: The pseudonymized message. Confidential.

        Returns:
            The probability of every intent.

        Raises:
            IntentModelError: The model returned an output that is not a score for every intent.
        """
        inputs = self._tokenizer(
            message,
            max_length=self._artifact.max_length,
            padding="max_length",
            truncation=True,
            return_tensors=_TENSOR_FORMAT,
        )
        (logits,) = self._model(**inputs).logits.tolist()
        return distribution_from_logits(logits, self._artifact.labels)


def load_distilbert_classifier(artifact: ModelArtifact) -> DistilBertClassifier:
    """Load the model of a checked artifact from its folder only.

    Args:
        artifact: The artifact, which `read_model_artifact` checked.

    Returns:
        The classifier.

    Raises:
        ReleaseInvalidError: The model library cannot load the artifact, or the loaded model
            holds another label map than the artifact.
    """
    try:
        tokenizer = cast(
            "_Tokenizer",
            cast("_Loader", AutoTokenizer).from_pretrained(
                artifact.directory, local_files_only=True
            ),
        )
        model = cast(
            "_Classifier",
            cast("_Loader", AutoModelForSequenceClassification).from_pretrained(
                artifact.directory, local_files_only=True
            ),
        )
    except (OSError, ValueError) as error:
        raise ReleaseInvalidError(ReleaseInvalidReason.ASSET_INVALID, asset="model") from error
    if _labels_of(model) != artifact.labels:
        raise ReleaseInvalidError(ReleaseInvalidReason.ASSET_INVALID, asset="model")
    model.eval()
    # No parameter needs a gradient, so a prediction builds no graph and keeps no memory.
    model.requires_grad_(False)
    return DistilBertClassifier(artifact, tokenizer, model)


def _labels_of(model: _Classifier) -> Sequence[str]:
    id2label = model.config.id2label
    return tuple(id2label[output] for output in sorted(id2label))
