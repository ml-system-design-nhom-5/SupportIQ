"""The offline evaluation gate: run a candidate on the guardrails and the escalation cases.

The gate loads exactly the candidate release, in its own process, through the one entry point
of `ai-service` for it, and gives it the ports of `adapters/` (ADR-0021, Release and the
offline evaluation gate; DATA-57). Its record states every part, the known gaps of the first
release, and that no LLM call was made.

The public names are those of its packages `domain` and `adapters` (PY-08).
"""

__all__: list[str] = []
