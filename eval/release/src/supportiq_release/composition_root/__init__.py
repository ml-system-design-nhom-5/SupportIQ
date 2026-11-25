"""The composition root of the release command: the only place that wires adapters (ARCH-21)."""

from supportiq_release.composition_root.cli import main

__all__ = ["main"]
