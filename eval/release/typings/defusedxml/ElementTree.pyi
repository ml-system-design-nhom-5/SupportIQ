# The names of defusedxml.ElementTree that the release command uses; the package ships no type
# information. `fromstring` refuses an entity and an external reference, and with `forbid_dtd`
# a document type too.

from xml.etree.ElementTree import Element, ParseError

__all__ = ["ParseError", "fromstring"]

def fromstring(
    text: str | bytes,
    forbid_dtd: bool = ...,
    forbid_entities: bool = ...,
    forbid_external: bool = ...,
) -> Element: ...
