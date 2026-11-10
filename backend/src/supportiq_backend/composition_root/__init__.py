"""The composition root of backend: the only place that creates and wires adapters (ARCH-21)."""

from supportiq_backend.composition_root.cli import main
from supportiq_backend.composition_root.web_application import create_app

__all__ = ["create_app", "main"]
