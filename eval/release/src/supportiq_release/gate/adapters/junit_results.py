"""Read the result of a folder of guardrail tests from the JUnit XML file of pytest.

The gate runs `ai-service/tests/integration/guardrails` and `backend/tests/integration/guardrails`
as they are, each in its own container, and pytest writes a JUnit XML file of each run
(`--junit-xml`), with the name of the folder as the name of its suite (`-o junit_suite_name`,
`gate/run-gate.sh`). The file is read with defusedxml, which refuses a document type here, an
entity, and an external reference.

A report counts for its folder only when it is the report of that folder: every `testsuite`
has the name of the folder and holds the four counts as integers of at least 0, as pytest
writes them, so a missing count is never read as no skipped test (TEST-20); it holds one
`testcase` for each test; and every `testcase` is in `tests.integration.guardrails`, the
package of the folder as pytest names it from the root of the component. The counts of every
`testsuite` are added up, and the test classes are recorded.
"""

import re
from collections.abc import Mapping, Sequence
from enum import StrEnum
from pathlib import Path

from defusedxml import DefusedXmlException
from defusedxml.ElementTree import ParseError, fromstring

from supportiq_release.errors import ReleaseCommandError
from supportiq_release.gate.domain import GuardrailResult, GuardrailSuite

_COUNTS = ("tests", "failures", "errors", "skipped")
_COUNT = re.compile(r"0|[1-9][0-9]*")
_GUARDRAIL_PACKAGE = "tests.integration.guardrails."


class GuardrailResultProblem(StrEnum):
    """Why the result of a guardrail folder cannot be read."""

    NOT_A_REGULAR_FILE = "missing_or_not_a_regular_file"
    UNREADABLE = "unreadable"
    NOT_JUNIT_XML = "not_junit_xml"
    OTHER_SUITE = "report_of_another_suite"
    OUTSIDE_THE_FOLDER = "test_outside_the_guardrail_folder"


class GuardrailResultInvalidError(ReleaseCommandError):
    """The result of a guardrail folder cannot be read. The message names the suite only."""

    def __init__(self, suite: GuardrailSuite, problem: GuardrailResultProblem) -> None:
        """Build the error with a message that names the suite and the problem.

        Args:
            suite: The folder of guardrail tests.
            problem: Why its result cannot be read.
        """
        super().__init__(f"The result of {suite} is refused: {problem}.")
        self.suite = suite
        self.problem = problem


def read_guardrail_result(suite: GuardrailSuite, path: Path) -> GuardrailResult:
    """Read the counts and the test classes of one run of a guardrail folder.

    Args:
        suite: The folder of guardrail tests.
        path: The JUnit XML file that pytest wrote for it.

    Returns:
        The counts of tests, failures, errors, and skipped tests, and the test classes.

    Raises:
        GuardrailResultInvalidError: The file is missing, a link, unreadable, not a JUnit XML
            file with at least one `testsuite` and its four counts, or not the report of the
            folder.
    """
    data = _read(suite, path)
    try:
        root = fromstring(data, forbid_dtd=True)
    except (ParseError, DefusedXmlException) as error:
        raise GuardrailResultInvalidError(suite, GuardrailResultProblem.NOT_JUNIT_XML) from error
    suites = [
        (element.attrib, [case.get("classname", "") for case in element.iter("testcase")])
        for element in root.iter("testsuite")
    ]
    if not suites:
        raise GuardrailResultInvalidError(suite, GuardrailResultProblem.NOT_JUNIT_XML)
    counts = [_suite_counts(suite, attributes, classnames) for attributes, classnames in suites]
    tests, failures, errors, skipped = (sum(column) for column in zip(*counts, strict=True))
    classnames = sorted({name for _attributes, names in suites for name in names})
    return GuardrailResult(
        suite=suite,
        tests=tests,
        failures=failures,
        errors=errors,
        skipped=skipped,
        test_classnames=tuple(classnames),
    )


def _read(suite: GuardrailSuite, path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise GuardrailResultInvalidError(suite, GuardrailResultProblem.NOT_A_REGULAR_FILE)
    try:
        return path.read_bytes()
    except OSError as error:
        raise GuardrailResultInvalidError(suite, GuardrailResultProblem.UNREADABLE) from error


def _suite_counts(
    suite: GuardrailSuite, attributes: Mapping[str, str], classnames: Sequence[str]
) -> list[int]:
    # The four counts of one `testsuite` of the folder, each an integer of at least 0.
    if attributes.get("name") != suite.value:
        raise GuardrailResultInvalidError(suite, GuardrailResultProblem.OTHER_SUITE)
    values = [attributes.get(name, "") for name in _COUNTS]
    if any(_COUNT.fullmatch(value) is None for value in values):
        raise GuardrailResultInvalidError(suite, GuardrailResultProblem.NOT_JUNIT_XML)
    counts = [int(value) for value in values]
    if len(classnames) != counts[0]:
        raise GuardrailResultInvalidError(suite, GuardrailResultProblem.NOT_JUNIT_XML)
    if not all(name.startswith(_GUARDRAIL_PACKAGE) for name in classnames):
        raise GuardrailResultInvalidError(suite, GuardrailResultProblem.OUTSIDE_THE_FOLDER)
    return counts
