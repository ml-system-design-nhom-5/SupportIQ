"""The reads that backend serves from ai-service: a KB document version and the versions in use.

`getConsoleKbDocumentVersion` and `getAdminVersions` read ai-service with
`ai_service_read_timeout_ms` and without a retry. The first answers `503 not-ready` when
ai-service cannot answer; the second still answers, without the versions of ai-service
(backend ticket workflow design, The `ai-service` client). Each use case checks the role first,
in the application layer (SEC-16), runs its call in a `call_ai_service` span (LOG-20), and
records a failed call once, at the level that tells a defect from degradation (ERR-05, LOG-15).
"""

from dataclasses import dataclass

from supportiq_backend.accounts import Authorizer, Principal, SupportPrincipal
from supportiq_backend.platform import EventRecorder, OperationId, SpanName, StepTracer
from supportiq_backend.suggestions.application.ai_service_failures import (
    AiServiceOperation,
    record_ai_service_failure,
)
from supportiq_backend.suggestions.domain import (
    AiService,
    AiServiceContractError,
    AiServiceReadContractError,
    AiServiceReadUnavailableError,
    AiServiceUnavailableError,
    AssetVersions,
    KbDocumentId,
    KbDocumentVersion,
    KbDocumentVersionNotFoundError,
    KbDocumentVersionTag,
)


@dataclass(frozen=True, slots=True)
class AiServiceReadPorts:
    """The ports of the reads of ai-service.

    Attributes:
        authorizer: The role checks.
        ai_service: The client of ai-service.
        events: Where a failed call is recorded.
        steps: Runs each call in its span.
    """

    authorizer: Authorizer
    ai_service: AiService
    events: EventRecorder
    steps: StepTracer


@dataclass(frozen=True, slots=True)
class VersionsInUse:
    """The versions in use, for the admin area: versions only (ADR-0012, SEC-41).

    Attributes:
        backend_version: The build version of backend.
        ai_service_versions: The release and asset versions that ai-service serves; absent
            when ai-service did not answer in time or answered with an error.
    """

    backend_version: str
    ai_service_versions: AssetVersions | None


class GetConsoleKbDocumentVersion:
    """Return one KB document version in full (`getConsoleKbDocumentVersion`)."""

    def __init__(self, ports: AiServiceReadPorts) -> None:
        """Keep the ports.

        Args:
            ports: The ports.
        """
        self._ports = ports

    def authorize(self, principal: Principal) -> SupportPrincipal:
        """Allow only staff and managers, before the path is parsed.

        Args:
            principal: The caller.

        Returns:
            The caller as a member of support.

        Raises:
            ForbiddenRoleError: The caller is a customer or an admin.
        """
        return self._ports.authorizer.require_support(
            principal, OperationId.GET_CONSOLE_KB_DOCUMENT_VERSION
        )

    async def execute(
        self, document_id: KbDocumentId, version: KbDocumentVersionTag
    ) -> KbDocumentVersion:
        """Read the document version from ai-service, after `authorize` allowed the caller.

        Args:
            document_id: The KB document.
            version: The version of the document.

        Returns:
            The document version, as ai-service serves it.

        Raises:
            KbDocumentVersionNotFoundError: The loaded KB has no such version.
            AiServiceReadUnavailableError: ai-service timed out, was unreachable, or answered
                `5xx`; the failure is recorded once, as `ai_service.call_failed`.
            AiServiceReadContractError: ai-service refused the read or answered outside its
                contract, a defect recorded once, as `ai_service.contract_violated`.
        """
        operation = AiServiceOperation.GET_KB_DOCUMENT_VERSION
        with self._ports.steps.step(SpanName.CALL_AI_SERVICE):
            self._ports.steps.record_ai_service_endpoint(operation)
            try:
                document = await self._ports.ai_service.fetch_kb_document_version(
                    document_id, version
                )
            # A contract error is also an `AiServiceUnavailableError`, so it is caught first.
            except AiServiceContractError as error:
                record_ai_service_failure(self._ports.events, operation, error)
                raise AiServiceReadContractError from error
            except AiServiceUnavailableError as error:
                record_ai_service_failure(self._ports.events, operation, error)
                raise AiServiceReadUnavailableError from error
        if document is None:
            raise KbDocumentVersionNotFoundError
        return document


class GetAdminVersions:
    """Return the versions in use (`getAdminVersions`). It changes nothing."""

    def __init__(self, ports: AiServiceReadPorts, backend_version: str) -> None:
        """Keep the ports and the build version.

        Args:
            ports: The ports.
            backend_version: The setting `backend_build_version`.
        """
        self._ports = ports
        self._backend_version = backend_version

    async def execute(self, principal: Principal) -> VersionsInUse:
        """Read the versions that ai-service serves, next to the build version of backend.

        Args:
            principal: The caller.

        Returns:
            The versions; without those of ai-service when it could not answer, which is
            recorded once, at `error` when it is a contract violation.

        Raises:
            ForbiddenRoleError: The caller is not an admin.
        """
        self._ports.authorizer.require_admin(principal, OperationId.GET_ADMIN_VERSIONS)
        operation = AiServiceOperation.GET_ASSET_VERSIONS
        with self._ports.steps.step(SpanName.CALL_AI_SERVICE):
            self._ports.steps.record_ai_service_endpoint(operation)
            try:
                versions = await self._ports.ai_service.fetch_asset_versions()
            except AiServiceUnavailableError as error:
                record_ai_service_failure(self._ports.events, operation, error)
                return VersionsInUse(self._backend_version, None)
        return VersionsInUse(self._backend_version, versions)
