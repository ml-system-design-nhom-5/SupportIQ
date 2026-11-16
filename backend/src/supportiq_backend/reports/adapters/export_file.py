"""The output file of `backend export-decisions`: JSON lines inside `exports/` only (SEC-33).

The path is resolved before anything is read: `..` segments and symbolic links are followed,
and the result must lie inside the folder `exports/` of the working directory, which is
git-ignored. A path anywhere else, the folder itself, or a link that leads out of it is refused,
so nothing is written outside the folder. Each record becomes one JSON object on its own line;
an absent value is left out, never written as `null` (CON-08).
"""

import asyncio
import json
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path

from supportiq_backend.platform import format_timestamp
from supportiq_backend.reports.domain import (
    EXPORTS_FOLDER_NAME,
    DecisionRecord,
    ExportedDecision,
    ExportedPart,
    ExportPathRefusedError,
    ExportWriteFailedError,
    JsonValue,
    SuggestionSnapshot,
)

_ENCODING = "utf-8"
_LINE_END = "\n"


class JsonLinesDecisionFile:
    """Implement the `DecisionRecordFile` port on one checked path inside `exports/`."""

    def __init__(self, path: Path) -> None:
        """Keep the path that `resolve_export_path` returned.

        Args:
            path: The resolved output path, inside `exports/`.
        """
        self._path = path

    async def save_decision_records(self, records: tuple[DecisionRecord, ...]) -> None:
        """Write the records as one JSON object per line, replacing the file.

        Args:
            records: The records.

        Raises:
            ExportWriteFailedError: The file could not be written.
        """
        text = "".join(_to_json_line(record) for record in records)
        # File writes block, so they run in a worker thread, away from the event loop (PY-30).
        await asyncio.to_thread(self._write, text)

    def _write(self, text: str) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(text, encoding=_ENCODING)
        except OSError as error:
            raise ExportWriteFailedError from error


def resolve_export_path(output: Path, working_directory: Path) -> Path:
    """Resolve an output path and check that it lies inside `exports/`.

    Args:
        output: The path as given on the command line, absolute or relative to the working
            directory.
        working_directory: The working directory of the command.

    Returns:
        The absolute path, with `..` segments and symbolic links resolved.

    Raises:
        ExportPathRefusedError: The path resolves outside `exports/`, or to the folder itself.
    """
    # The folder is not resolved itself: when `exports` is a link to another folder, every
    # path inside it resolves outside `exports/` and is refused.
    folder = working_directory.resolve() / EXPORTS_FOLDER_NAME
    resolved = (working_directory / output).resolve()
    if resolved == folder or not resolved.is_relative_to(folder):
        raise ExportPathRefusedError(output)
    return resolved


def _to_json_line(record: DecisionRecord) -> str:
    return json.dumps(_to_record_object(record), ensure_ascii=False) + _LINE_END


def _to_record_object(record: DecisionRecord) -> Mapping[str, JsonValue]:
    return _without_absent(
        {
            "ticket_id": record.ticket_id,
            "handling_mode": record.handling_mode.value,
            "study_pair_id": record.study_pair_id,
            "study_batch": record.study_batch,
            "created_at": format_timestamp(record.created_at),
            "handling_started_at": _optional_timestamp(record.handling_started_at),
            "escalated_at": _optional_timestamp(record.escalated_at),
            "closed_at": _optional_timestamp(record.closed_at),
            "handling_time_ms": record.handling_time_ms,
            "suggestion": None
            if record.suggestion is None
            else _to_suggestion_object(record.suggestion),
            "decisions": [_to_decision_object(decision) for decision in record.decisions],
        }
    )


def _to_suggestion_object(snapshot: SuggestionSnapshot) -> Mapping[str, JsonValue]:
    return _without_absent(
        {
            "suggestion_id": snapshot.suggestion_id,
            "trigger": snapshot.trigger.value,
            "intent_override": None
            if snapshot.intent_override is None
            else snapshot.intent_override.value,
            "created_at": format_timestamp(snapshot.created_at),
            "pseudonymized_message": snapshot.pseudonymized_message,
            "analysis": _to_part_object(snapshot.analysis),
            "draft": _to_part_object(snapshot.draft),
        }
    )


def _to_part_object(part: ExportedPart) -> Mapping[str, JsonValue]:
    return _without_absent(
        {
            "status": part.status.value,
            "reason_codes": [code.value for code in part.reason_codes],
            "completed_at": _optional_timestamp(part.completed_at),
            "result": part.result_fields,
        }
    )


def _to_decision_object(decision: ExportedDecision) -> Mapping[str, JsonValue]:
    return _without_absent(
        {
            "decision_type": decision.decision_type.value,
            "staff_reason_codes": [code.value for code in decision.staff_reason_codes],
            "change_ratio": decision.change_ratio,
            "final_intent": None if decision.final_intent is None else decision.final_intent.value,
            "is_proposal_changed": decision.is_proposal_changed,
            "decided_at": format_timestamp(decision.decided_at),
        }
    )


def _optional_timestamp(moment: datetime | None) -> str | None:
    return None if moment is None else format_timestamp(moment)


def _without_absent(fields: Mapping[str, JsonValue]) -> Mapping[str, JsonValue]:
    return {name: value for name, value in fields.items() if value is not None}
