"""The composition root of ai-service: the only place that creates and wires adapters (ARCH-21)."""

from supportiq_ai_service.composition_root.cli import main
from supportiq_ai_service.composition_root.web_application import create_app

__all__ = ["create_app", "main"]
