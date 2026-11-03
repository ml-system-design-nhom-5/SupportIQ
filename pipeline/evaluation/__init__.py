"""Evaluation subsystem for SupportIQ intent classification and system pipelines."""

from __future__ import annotations


class EvaluationError(Exception):
    """Raised when an evaluation input, model, benchmark, or report fails contract validation."""
