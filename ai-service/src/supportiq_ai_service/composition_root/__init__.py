"""The composition root of ai-service: the only place that creates and wires adapters (ARCH-21).

`build_candidate_application` and `CandidatePorts` are the entry point of the offline
evaluation gate, for the release command in `eval/release/` only (ADR-0021, Release and the
offline evaluation gate).
"""

from supportiq_ai_service.composition_root.cli import build_candidate_application, main
from supportiq_ai_service.composition_root.release_assets import CandidatePorts
from supportiq_ai_service.composition_root.settings_loading import SettingsInvalidError
from supportiq_ai_service.composition_root.web_application import ServicePorts, create_app

__all__ = [
    "CandidatePorts",
    "ServicePorts",
    "SettingsInvalidError",
    "build_candidate_application",
    "create_app",
    "main",
]
