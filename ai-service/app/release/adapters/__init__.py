"""Adapters of release: the interim format of the release manifest and its check."""

from app.release.adapters.manifest_file import (
    VerifiedReleaseSource,
    verify_candidate,
    verify_release,
)

__all__ = ["VerifiedReleaseSource", "verify_candidate", "verify_release"]
