"""Training pipeline package for SupportIQ intent classification."""

from __future__ import annotations


class TrainingError(Exception):
    """Raised when a training run cannot be completed safely."""
