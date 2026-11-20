"""Tests of the database TLS that the composition root chooses from the settings (SEC-28)."""

from pathlib import Path

from app.composition_root.runtime import database_ca_file
from app.platform.settings import DatabaseTls
from tests.unit.platform.settings_builders import build_test_settings

CA_FILE = Path("certs/another-root-ca.crt")


def test_verify_full_checks_the_ca_file_of_the_settings() -> None:
    settings = build_test_settings(database_tls=DatabaseTls.VERIFY_FULL, database_ca_file=CA_FILE)

    assert database_ca_file(settings) == CA_FILE


def test_disable_gives_no_ca_file_so_no_tls() -> None:
    settings = build_test_settings(database_tls=DatabaseTls.DISABLE, database_ca_file=CA_FILE)

    assert database_ca_file(settings) is None


def test_the_initial_settings_check_the_committed_ca_file() -> None:
    assert database_ca_file(build_test_settings()) == Path("certs/supabase-root-ca.crt")
