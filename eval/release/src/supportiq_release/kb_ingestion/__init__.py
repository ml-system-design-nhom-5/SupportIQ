"""KB ingestion: admit the KB document versions of a raw KB folder, and quarantine the rest.

The rules are those of ADR-0021 (KB ingestion): a version is admitted only when the release
file of the KB holder lists it and every field that `KbDocumentVersion` requires is present and
valid. Ingestion never invents a value, never drops a record silently, and never resolves a
conflict (DATA-12, DATA-13, DATA-19).

The public names are those of its packages `domain` and `adapters` (PY-08).
"""

__all__: list[str] = []
