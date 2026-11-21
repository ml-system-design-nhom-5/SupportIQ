"""The candidate release: copy the six assets into a new folder, and write its manifest (DATA-56).

The candidate has no gate run yet (`"gate_run": null`), so `ai-service serve` refuses it. Only
the offline evaluation gate may link a passing run and publish it (ADR-0021, Release and the
offline evaluation gate; DATA-57).

The public names are those of its packages `domain` and `adapters` (PY-08).
"""

__all__: list[str] = []
