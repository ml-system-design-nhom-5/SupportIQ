"""The composition root of backend: the only place that creates and wires adapters (ARCH-21)."""

from app.composition_root.cli import main
from app.composition_root.web_application import BackgroundWork, create_app

__all__ = ["BackgroundWork", "create_app", "main"]
