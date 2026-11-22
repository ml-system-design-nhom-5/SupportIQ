"""The release download: one archive per published release, checked against the manifest in git.

`pack-release` writes the archive of a published release and, on request, the pinned file;
`download-release` fetches the archive from its GitHub Release, checks it, and puts it into a
cache; `check-pinned-release` keeps the pinned file and GitHub in step (ADR-0030; release
download and Modal deploy design).

The public names are those of its packages `domain` and `adapters` (PY-08).
"""

__all__: list[str] = []
