"""The egress allow-list and the only factory of HTTP clients that leave the system (SEC-40).

ai-service calls outside the system only the hosts of the egress allow-list (ADR-0010,
Egress control). The list is the file `egress-allow-list.v1.json` next to this module. It
ships inside the package and is not a setting, so only a reviewed change in the repository
can change it (ADR-0010, Egress control, statement 2; ARCH-37).

The hosting has no outbound filter, so egress is enforced here, in code (ADR-0018, Egress):
every client of `create_egress_client` refuses, before it connects, a request that is not
HTTPS on the default port to an allow-listed host. No other module of ai-service creates an
HTTP client (ARCH-19), and a guardrail test checks that.
"""

from dataclasses import dataclass
from importlib import resources
from importlib.resources.abc import Traversable
from typing import Annotated, ClassVar, Literal

import httpx
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    field_validator,
)

from supportiq_ai_service.platform import AiServiceError, ErrorCode

ALLOW_LIST_FILE_NAME = "egress-allow-list.v1.json"
_ALLOW_LIST_PACKAGE = "supportiq_ai_service.platform.adapters"
_ALLOWED_SCHEME = "https"
# A lowercase DNS name of two labels or more whose last label is alphabetic, so no scheme,
# port, path, wildcard, or IP address fits (RFC 1035, section 2.3.4, for the lengths).
_HOST_NAME_PATTERN = r"^([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$"
_HOST_NAME_MAX_LENGTH = 253

HostName = Annotated[
    str, StringConstraints(max_length=_HOST_NAME_MAX_LENGTH, pattern=_HOST_NAME_PATTERN)
]


class EgressAllowListInvalidError(AiServiceError):
    """The egress allow-list file is missing or breaks its format, so ai-service stops."""

    code: ClassVar[ErrorCode] = ErrorCode.INTERNAL_ERROR

    def __init__(self, file_name: str) -> None:
        """Keep the name of the file, never its content.

        Args:
            file_name: The name of the allow-list file.
        """
        super().__init__(f"The egress allow-list {file_name} is missing or invalid.")
        self.file_name = file_name


class EgressRefusedError(httpx.RequestError):
    """A request outside the egress allow-list, refused before any connection.

    It is an `httpx.RequestError`, so the LLM client handles it like every other failed
    call: no draft, and the outcome `llm_unavailable` (ADR-0010, Failure handling).
    """

    def __init__(self, request: httpx.Request) -> None:
        """Build the error with a fixed message, which repeats no part of the request.

        Args:
            request: The refused request.
        """
        super().__init__("The request is outside the egress allow-list.", request=request)


@dataclass(frozen=True, slots=True)
class EgressAllowList:
    """The hosts outside the system that ai-service may call.

    Attributes:
        version: The version of the allow-list file.
        hosts: The allowed host names, in lowercase.
    """

    version: str
    hosts: frozenset[str]


class _AllowListFile(BaseModel):
    """The format of the allow-list file: read strictly, every other field refused."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    version: Literal["1"]
    hosts: Annotated[list[HostName], Field(min_length=1)]

    @field_validator("hosts")
    @classmethod
    def _each_host_is_listed_once(cls, hosts: list[str]) -> list[str]:
        if len(set(hosts)) != len(hosts):
            message = "every host is listed once"
            raise ValueError(message)
        return hosts


def load_egress_allow_list(source: Traversable) -> EgressAllowList:
    """Read an egress allow-list file and check its format.

    Args:
        source: The file: the packaged one in production, a temporary one in tests.

    Returns:
        The allow-list.

    Raises:
        EgressAllowListInvalidError: The file is missing or unreadable, is not JSON in UTF-8,
            or breaks the format of `_AllowListFile`.
    """
    try:
        document = _AllowListFile.model_validate_json(source.read_bytes())
    except (OSError, ValidationError) as error:
        raise EgressAllowListInvalidError(source.name) from error
    return EgressAllowList(version=document.version, hosts=frozenset(document.hosts))


def packaged_egress_allow_list() -> EgressAllowList:
    """Read the allow-list file that ships with ai-service, and check its format.

    Returns:
        The allow-list.

    Raises:
        EgressAllowListInvalidError: The packaged file is missing or invalid.
    """
    return load_egress_allow_list(
        resources.files(_ALLOW_LIST_PACKAGE).joinpath(ALLOW_LIST_FILE_NAME)
    )


class AllowListedTransport(httpx.BaseTransport):
    """Send a request only when it is HTTPS on the default port to an allow-listed host."""

    def __init__(self, allow_list: EgressAllowList, network: httpx.BaseTransport) -> None:
        """Wrap the transport that opens the connections.

        Args:
            allow_list: The hosts that requests may reach.
            network: The transport that sends the allowed requests.
        """
        self._hosts = allow_list.hosts
        self._network = network

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        """Send an allowed request, and refuse every other one before it connects.

        Args:
            request: The request.

        Returns:
            The response of the network transport.

        Raises:
            EgressRefusedError: The request is not HTTPS, names a port, or goes to a host
                outside the allow-list.
        """
        url = request.url
        # httpx writes the host in lowercase and drops the default port of the scheme, so an
        # explicit `:443` passes and every other port is refused.
        if url.scheme != _ALLOWED_SCHEME or url.port is not None or url.host not in self._hosts:
            raise EgressRefusedError(request)
        return self._network.handle_request(request)

    def close(self) -> None:
        """Close the network transport."""
        self._network.close()


def create_egress_client(
    allow_list: EgressAllowList, network: httpx.BaseTransport | None = None
) -> httpx.Client:
    """Create an HTTP client that reaches only the hosts of the allow-list.

    The client reads nothing from the environment (`trust_env=False`): with it, httpx would
    add a proxy transport from `HTTPS_PROXY` that bypasses `AllowListedTransport`. It never
    follows a redirect (`follow_redirects=False`). Only the composition root calls this
    function, once at startup, and closes the client at shutdown (ARCH-21, ARCH-24).

    Args:
        allow_list: The checked allow-list.
        network: The transport that opens the connections. The composition root leaves the
            default, a new `httpx.HTTPTransport`; tests pass a fake.

    Returns:
        The client.
    """
    transport = AllowListedTransport(
        allow_list, httpx.HTTPTransport() if network is None else network
    )
    return httpx.Client(transport=transport, trust_env=False, follow_redirects=False)
