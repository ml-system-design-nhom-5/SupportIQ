"""The two models of a release, faked, so that wiring a replica needs no torch and no weights.

`KB_RELEASE_CHANGES` gives a release two KB document versions, both mapped to `track_order`,
the intent that the fake classifier is sure of.
"""

from app.composition_root.release_assets import ReleaseModels
from app.intent import IntentDistribution
from app.intent.adapters.model_artifact import ModelArtifact
from app.retrieval.adapters.index_file import IndexConfiguration
from tests.unit.intent.fakes import distribution
from tests.unit.release.release_folder import (
    KB_DOCUMENT,
    KB_ENTRY,
    MAPPING_DOCUMENT,
    AssetFileChanges,
    json_file,
)
from tests.unit.retrieval.fakes import KeywordEncoder

# 150 words, so the chunking of the release (100 tokens, 10 of overlap) makes two passages.
LONG_DOCUMENT = {**KB_ENTRY, "body": " ".join(["refund"] * 150)}
SHORT_DOCUMENT = {
    **KB_ENTRY,
    "document_id": "SAMPLE-REFUND-002",
    "title": "A fake refund method",
    "body": "A refund to the card.",
    "policy_key": "refund_method",
}
KB_RELEASE_CHANGES: AssetFileChanges = {
    "kb": {"kb/kb.json": json_file({**KB_DOCUMENT, "documents": [LONG_DOCUMENT, SHORT_DOCUMENT]})},
    "mapping": {
        "mapping/document-intents.json": json_file(
            {
                **MAPPING_DOCUMENT,
                "documents": [
                    {
                        "document_id": document["document_id"],
                        "version": document["version"],
                        "intents": ["track_order"],
                    }
                    for document in (LONG_DOCUMENT, SHORT_DOCUMENT)
                ],
            }
        )
    },
}


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
