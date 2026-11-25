"""Tests of the TLS of the database engine and of the committed certificate authority (SEC-28).

With a certificate authority, the engine passes asyncpg a TLS context that trusts only that
authority, checks the host name, and requires a server certificate. Without one, it passes
`ssl=False`, so the shell's PGSSLMODE never chooses the mode. The authority in `certs/` is the
root of Supabase; its checksum is the one the backend README records, so a change of the trust
anchor fails here first.
"""

import hashlib
import ssl
from pathlib import Path

import pytest
from sqlalchemy import event

from app.platform.adapters.database import (
    DatabaseCaFileError,
    DatabaseTimeouts,
    create_database_engine,
    verified_tls_context,
)
from app.platform.settings import DEFAULT_DATABASE_CA_FILE

BACKEND_ROOT = Path(__file__).parents[3]
CA_FILE = BACKEND_ROOT / DEFAULT_DATABASE_CA_FILE
# The SHA-256 of the file and the common name of the authority (backend README, TLS).
CA_FILE_SHA256 = "700723581420dd1ac98fd7e9ac529f0ef210eadcaf87fc868a3ad7d114c2f3b7"
CA_COMMON_NAME = "Supabase Root 2021 CA"
URL = "postgresql+asyncpg://supportiq_app:tls-test-password@db.tls.test:5432/postgres"
TIMEOUTS = DatabaseTimeouts(connect_ms=3000, statement_ms=5000, lock_ms=3000, pool_ms=3000)


class StoppedBeforeTheNetworkError(Exception):
    """Raised by the connect listener of these tests, so that no connection is opened."""


async def connect_arguments(ca_file: Path | None) -> dict[str, object]:
    """Return the arguments that the engine passes to asyncpg, without connecting."""
    engine = create_database_engine(URL, TIMEOUTS, ca_file=ca_file)
    seen: list[dict[str, object]] = []

    def stop_before_the_network(
        _dialect: object, _record: object, _args: object, arguments: dict[str, object]
    ) -> None:
        seen.append(dict(arguments))
        raise StoppedBeforeTheNetworkError

    event.listen(engine.sync_engine, "do_connect", stop_before_the_network)
    try:
        with pytest.raises(StoppedBeforeTheNetworkError):
            async with engine.connect():
                pass
    finally:
        await engine.dispose()
    (arguments,) = seen
    return arguments


def assert_trusts_only_the_ca_file_and_checks_the_host(context: object) -> None:
    """Check that `context` requires a certificate of the committed authority for the host."""
    assert isinstance(context, ssl.SSLContext)
    assert context.verify_mode is ssl.CERT_REQUIRED
    assert context.check_hostname
    (authority,) = context.get_ca_certs()
    subject = authority["subject"]
    assert isinstance(subject, tuple)
    assert (("commonName", CA_COMMON_NAME),) in subject


def test_the_committed_certificate_authority_is_the_recorded_one() -> None:
    digest = hashlib.sha256(CA_FILE.read_bytes()).hexdigest()

    assert digest == CA_FILE_SHA256


def test_the_context_of_the_ca_file_trusts_only_it_and_checks_the_host() -> None:
    assert_trusts_only_the_ca_file_and_checks_the_host(verified_tls_context(CA_FILE))


@pytest.mark.anyio
async def test_an_engine_with_a_ca_file_connects_with_the_context_of_that_file() -> None:
    arguments = await connect_arguments(CA_FILE)

    assert_trusts_only_the_ca_file_and_checks_the_host(arguments["ssl"])


@pytest.mark.anyio
async def test_an_engine_without_a_ca_file_turns_tls_off_explicitly() -> None:
    arguments = await connect_arguments(None)

    assert arguments["ssl"] is False


def test_an_engine_with_a_missing_ca_file_is_refused(tmp_path: Path) -> None:
    with pytest.raises(DatabaseCaFileError):
        create_database_engine(URL, TIMEOUTS, ca_file=tmp_path / "absent.crt")


def test_a_file_that_holds_no_certificate_is_refused(tmp_path: Path) -> None:
    not_a_certificate = tmp_path / "not-a-certificate.crt"
    not_a_certificate.write_text("not a certificate\n", encoding="utf-8")

    with pytest.raises(DatabaseCaFileError):
        verified_tls_context(not_a_certificate)


def test_the_error_of_the_ca_file_names_the_setting_and_no_url() -> None:
    error = DatabaseCaFileError()

    assert "database_ca_file" in error.detail
    assert "postgresql" not in error.detail
