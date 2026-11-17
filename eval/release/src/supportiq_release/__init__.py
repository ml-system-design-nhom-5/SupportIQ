"""The release command of SupportIQ: build what a release of ai-service serves (ADR-0021).

It is new code in `eval/`, separate from the evaluation code that came from `main`, and it uses
none of that code (ADR-0021, Where the code of `main` goes, statement 3).

The command line is `supportiq_release.composition_root.main`; the root package exports nothing
itself (PY-08).
"""

__all__: list[str] = []
