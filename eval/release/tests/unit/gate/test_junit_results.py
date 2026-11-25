"""The result of a guardrail folder is read from its JUnit XML file, safely and strictly."""

from collections.abc import Callable
from pathlib import Path

import pytest

from supportiq_release.gate.adapters import (
    GuardrailResultInvalidError,
    GuardrailResultProblem,
    read_guardrail_result,
)
from supportiq_release.gate.domain import GuardrailResult, GuardrailSuite
from tests.unit.gate.fakes import junit_xml

SUITE = GuardrailSuite.BACKEND


def _write(tmp_path: Path, data: bytes) -> Path:
    path = tmp_path / "guardrails.xml"
    path.write_bytes(data)
    return path


def _refusal(path: Path) -> GuardrailResultInvalidError:
    with pytest.raises(GuardrailResultInvalidError) as refused:
        read_guardrail_result(SUITE, path)
    return refused.value


AUTHORIZATION_CLASS = "tests.integration.guardrails.test_service_token"
EGRESS_CLASS = "tests.integration.guardrails.test_egress_allow_list.TestScan"


def test_the_counts_of_every_testsuite_are_added_up_with_the_test_classes(tmp_path: Path) -> None:
    data = junit_xml(
        tests=5,
        failures=1,
        errors=2,
        skipped=3,
        suites=2,
        name="ai_service_guardrails",
        classnames=(AUTHORIZATION_CLASS, EGRESS_CLASS),
    )

    result = read_guardrail_result(GuardrailSuite.AI_SERVICE, _write(tmp_path, data))

    assert result == GuardrailResult(
        suite=GuardrailSuite.AI_SERVICE,
        tests=10,
        failures=2,
        errors=4,
        skipped=6,
        test_classnames=(EGRESS_CLASS, AUTHORIZATION_CLASS),
    )


def test_a_testsuite_at_the_root_is_read(tmp_path: Path) -> None:
    data = (
        b'<testsuite name="backend_guardrails" tests="1" failures="0" errors="0" skipped="1">'
        b'<testcase classname="tests.integration.guardrails.test_audit_log" name="test_x"/>'
        b"</testsuite>"
    )

    result = read_guardrail_result(SUITE, _write(tmp_path, data))

    assert result == GuardrailResult(
        suite=SUITE,
        tests=1,
        failures=0,
        errors=0,
        skipped=1,
        test_classnames=("tests.integration.guardrails.test_audit_log",),
    )


@pytest.mark.parametrize(
    "name", ["pytest", "ai_service_guardrails", ""], ids=["default", "other folder", "empty"]
)
def test_the_report_of_another_suite_is_refused(tmp_path: Path, name: str) -> None:
    refusal = _refusal(_write(tmp_path, junit_xml(name=name)))

    assert refusal.problem is GuardrailResultProblem.OTHER_SUITE


@pytest.mark.parametrize(
    "classname",
    [
        "tests.unit.test_audit_log",
        "tests.integration.guardrailsx.test_audit_log",
        "tests.integration.guardrails",
        "",
    ],
)
def test_a_test_outside_the_guardrail_folder_is_refused(tmp_path: Path, classname: str) -> None:
    data = junit_xml(tests=2, classnames=("tests.integration.guardrails.test_audit_log", classname))

    refusal = _refusal(_write(tmp_path, data))

    assert refusal.problem is GuardrailResultProblem.OUTSIDE_THE_FOLDER


def _missing(tmp_path: Path) -> Path:
    return tmp_path / "absent.xml"


def _folder(tmp_path: Path) -> Path:
    folder = tmp_path / "guardrails.xml"
    folder.mkdir()
    return folder


def _link(tmp_path: Path) -> Path:
    target = _write(tmp_path, junit_xml())
    link = tmp_path / "link.xml"
    link.symlink_to(target)
    return link


@pytest.mark.parametrize("make_path", [_missing, _folder, _link])
def test_a_path_that_is_not_a_regular_file_is_refused(
    tmp_path: Path, make_path: Callable[[Path], Path]
) -> None:
    refusal = _refusal(make_path(tmp_path))

    assert refusal.suite is SUITE
    assert refusal.problem is GuardrailResultProblem.NOT_A_REGULAR_FILE


def test_a_file_that_cannot_be_read_is_refused(tmp_path: Path) -> None:
    path = _write(tmp_path, junit_xml())
    path.chmod(0)
    try:
        refusal = _refusal(path)
    finally:
        path.chmod(0o600)

    assert refusal.problem is GuardrailResultProblem.UNREADABLE


@pytest.mark.parametrize(
    "data",
    [
        pytest.param(b"tests=2 failures=0", id="not-xml"),
        pytest.param(b"", id="empty"),
        pytest.param(b"<testsuites></testsuites>", id="no-testsuite"),
        pytest.param(b"<report><case/></report>", id="other-xml"),
        pytest.param(junit_xml().replace(b'tests="2"', b'tests="two"'), id="count-a-word"),
        pytest.param(junit_xml().replace(b'tests="2"', b'tests="1.5"'), id="count-a-float"),
        pytest.param(junit_xml().replace(b'skipped="0"', b'skipped="-1"'), id="count-negative"),
        pytest.param(junit_xml().replace(b' skipped="0"', b""), id="count-missing"),
        pytest.param(
            junit_xml(suites=2).replace(b'errors="0"', b'errors=" 0"', 1),
            id="count-padded-in-one-suite",
        ),
        pytest.param(junit_xml().replace(b'tests="2"', b'tests="3"'), id="a-test-case-missing"),
        pytest.param(junit_xml().replace(b'tests="2"', b'tests="1"'), id="a-test-case-too-many"),
        pytest.param(
            junit_xml().replace(
                b"<testsuites>", b'<!DOCTYPE testsuites SYSTEM "junit.dtd"><testsuites>'
            ),
            id="document-type",
        ),
        pytest.param(
            b'<?xml version="1.0"?><!DOCTYPE testsuites [<!ENTITY n "3">]>'
            b'<testsuites><testsuite tests="&n;"></testsuite></testsuites>',
            id="entity",
        ),
        pytest.param(
            b'<?xml version="1.0"?><!DOCTYPE testsuites [<!ENTITY n SYSTEM "file:///x">]>'
            b'<testsuites><testsuite tests="&n;"></testsuite></testsuites>',
            id="external-entity",
        ),
    ],
)
def test_a_file_that_is_not_junit_xml_is_refused(tmp_path: Path, data: bytes) -> None:
    refusal = _refusal(_write(tmp_path, data))

    assert refusal.suite is SUITE
    assert refusal.problem is GuardrailResultProblem.NOT_JUNIT_XML


def test_the_message_names_the_suite_and_the_problem_only(tmp_path: Path) -> None:
    secret = junit_xml().replace(b'tests="2"', b'tests="a confidential word"')

    refusal = _refusal(_write(tmp_path, secret))

    assert str(refusal) == "The result of backend_guardrails is refused: not_junit_xml."
