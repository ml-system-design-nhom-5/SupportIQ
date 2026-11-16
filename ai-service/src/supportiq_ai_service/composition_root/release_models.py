"""Load the intent model and the encoder of a release, with the threads that they use.

This module needs torch, which only the `torch` dependency group installs on Linux, and it
imports the model library, which reads its environment when it is imported. So the command
imports it lazily, after it set Hugging Face offline (ADR-0018, Egress; ADR-0021, Python and
dependencies, statement 2), and only its own tests, marked `torch`, run it.
"""

import importlib
from typing import Protocol, cast

from supportiq_ai_service.composition_root.release_assets import ReleaseModels
from supportiq_ai_service.intent.adapters.distilbert_model import load_distilbert_classifier
from supportiq_ai_service.intent.adapters.model_artifact import ModelArtifact
from supportiq_ai_service.retrieval.adapters.bge_encoder import load_bge_encoder
from supportiq_ai_service.retrieval.adapters.index_file import IndexConfiguration


class _Threads(Protocol):
    def set_num_threads(self, threads: int) -> None: ...


def load_release_models(
    artifact: ModelArtifact, index: IndexConfiguration, cpu_threads: int
) -> ReleaseModels:
    """Load the two models of a release from their checked folders only.

    Args:
        artifact: The checked model artifact.
        index: The checked configuration of the index, with the folder of the encoder.
        cpu_threads: The CPU threads that the models use (setting `model_cpu_threads`).

    Returns:
        The loaded models.

    Raises:
        ReleaseInvalidError: The model library cannot load a model of the release.
    """
    cast("_Threads", importlib.import_module("torch")).set_num_threads(cpu_threads)
    return ReleaseModels(
        classifier=load_distilbert_classifier(artifact), encoder=load_bge_encoder(index)
    )
