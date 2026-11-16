"""The two models of a release, faked, so that wiring a replica needs no torch and no weights."""

from supportiq_ai_service.composition_root.release_assets import ReleaseModels
from supportiq_ai_service.intent import IntentDistribution
from supportiq_ai_service.intent.adapters.model_artifact import ModelArtifact
from supportiq_ai_service.retrieval.adapters.index_file import IndexConfiguration
from tests.unit.intent.fakes import distribution
from tests.unit.retrieval.fakes import KeywordEncoder


class FakeClassifier:
    """An intent model that is sure of `track_order`."""

    def classify(self, message: str) -> IntentDistribution:
        """Return the fixed distribution.

        Args:
            message: The message, ignored.

        Returns:
            Probability 1 for `track_order`, and 0 for every other label.
        """
        del message
        return distribution(("track_order", 1.0))


def load_fake_models(
    artifact: ModelArtifact, index: IndexConfiguration, cpu_threads: int
) -> ReleaseModels:
    """Stand in for `cli.load_release_models`, which needs torch.

    Args:
        artifact: The checked model artifact, ignored.
        index: The checked configuration of the index, ignored.
        cpu_threads: The CPU threads, ignored.

    Returns:
        The fake classifier and the keyword encoder.
    """
    del artifact, index, cpu_threads
    return ReleaseModels(classifier=FakeClassifier(), encoder=KeywordEncoder())
