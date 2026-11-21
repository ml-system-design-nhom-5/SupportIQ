"""The trial of the named-entity detector (backend ticket workflow design, Choice 1).

Run it on demand from `backend/`, with the report in the git-ignored folder `exports/`:

    uv run python -m tests.trials.named_entity_trial ../exports/named-entity-trial.json

On the fixed `synthetic-dev-only` set, it measures the recall and the over-detection of names
and addresses after the overlap rule, the messages that the pre-send check stops, the peak
resident memory before and after the model loads, and the latency of pseudonymizing one message
with every detector and the pre-send check. Numbers from a laptop are indicative only; the design
asks for the memory and the latency on the free instance.
"""

import json
import platform
import resource
import statistics
import sys
import time
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import TypedDict

from app.composition_root.suggestions_wiring import build_detectors
from app.pseudonymization.domain import (
    Detection,
    PersonalDataLeftError,
    PseudonymType,
    build_pseudonymized_message,
    check_nothing_left,
    drop_product_names,
    resolve_overlaps,
)

TRIAL_SET = Path(__file__).with_name("synthetic-dev-only-named-entity-trial-v1.json")
SEED = Path(__file__).parents[2] / "seed" / "synthetic-dev-only-v1.json"
ROUNDS = 20
# `ru_maxrss` is in bytes on macOS and in KiB on Linux.
RSS_UNIT_BYTES = 1 if sys.platform == "darwin" else 1024


class TrialMessage(TypedDict):
    """One message of the set, with the names and addresses that it holds."""

    text: str
    names: list[str]
    addresses: list[str]


# The type that the pre-send check found, or None when it let the message through.
type Stop = PseudonymType | None
type Pseudonymize = Callable[[str], tuple[tuple[Detection, ...], Stop]]
type Result = tuple[TrialMessage, tuple[Detection, ...], Stop]


def main(output: Path) -> None:
    trial = json.loads(TRIAL_SET.read_text(encoding="utf-8"))
    seed = json.loads(SEED.read_text(encoding="utf-8"))
    rss_before_model = _peak_rss_mib()
    product_names = tuple(p["name"] for p in seed["commerce"]["products"])
    # The detectors that backend runs, so the trial measures them (ADR-0029); building them
    # loads the model.
    detectors = build_detectors()
    rss_with_model = _peak_rss_mib()

    def pseudonymize(text: str) -> tuple[tuple[Detection, ...], Stop]:
        found = (d for detector in detectors for d in detector.detect(text, ()))
        kept = resolve_overlaps(drop_product_names(found, text, product_names))
        built = build_pseudonymized_message(text, kept)
        # backend runs the pre-send check on every message, so the trial times it too, and
        # counts a stop instead of ending the run.
        try:
            check_nothing_left(built.text, built.entries, ())
        except PersonalDataLeftError as error:
            return kept, error.pseudonym_type
        return kept, None

    messages: list[TrialMessage] = trial["messages"]
    results: list[Result] = [(message, *pseudonymize(message["text"])) for message in messages]
    report = {
        "trial_set": f"{TRIAL_SET.name}, version {trial['version']}",
        "machine": f"{platform.platform()}, Python {platform.python_version()}",
        "types": {
            str(kind): _score(results, kind) for kind in (PseudonymType.NAME, PseudonymType.ADDRESS)
        },
        "pre_send_check": _stops(results),
        "peak_rss_mib": {"before_model": rss_before_model, "with_model": rss_with_model},
        "latency_ms": _latency(messages, pseudonymize),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def _score(results: list[Result], kind: PseudonymType) -> dict[str, object]:
    """Count the values of one type that the kept detections cover, and its detections of none."""
    values = covered = covered_as_kind = over = 0
    misses: list[str] = []
    for message, kept, _ in results:
        text = message["text"]
        gold = [_span(text, value) for value in (*message["names"], *message["addresses"])]
        for value in message["names"] if kind is PseudonymType.NAME else message["addresses"]:
            span = _span(text, value)
            values += 1
            if _covers(kept, span):
                covered += 1
            else:
                misses.append(value)
            covered_as_kind += int(_covers([d for d in kept if d.pseudonym_type is kind], span))
        over += sum(
            1 for d in kept if d.pseudonym_type is kind and not any(_overlaps(d, s) for s in gold)
        )
    return {
        "values": values,
        "covered": covered,
        "covered_with_this_type": covered_as_kind,
        "recall": round(covered / values, 3),
        "over_detections": over,
        "misses": misses,
    }


def _stops(results: list[Result]) -> dict[str, object]:
    """Count the messages that the pre-send check stops, by type, and the false stops of them.

    A false stop is a stopped message whose stopped text holds no raw value (leak fixes design,
    Rollout): the kept detections cover every name and address of the message.
    """
    stopped = [(message, kept, stop) for message, kept, stop in results if stop is not None]
    return {
        "messages": len(results),
        "stopped": len(stopped),
        "by_type": dict(Counter(str(stop) for _, _, stop in stopped)),
        "false_stops": sum(1 for message, kept, _ in stopped if _covers_every_value(message, kept)),
    }


def _covers_every_value(message: TrialMessage, kept: tuple[Detection, ...]) -> bool:
    text = message["text"]
    values = (*message["names"], *message["addresses"])
    return all(_covers(kept, _span(text, value)) for value in values)


def _span(text: str, value: str) -> tuple[int, int]:
    start = text.index(value)
    return start, start + len(value)


def _overlaps(detection: Detection, span: tuple[int, int]) -> bool:
    return detection.start < span[1] and span[0] < detection.end


def _covers(detections: list[Detection] | tuple[Detection, ...], span: tuple[int, int]) -> bool:
    """Tell whether the detections cover every character of the span, so no part is sent."""
    return all(any(d.start <= index < d.end for d in detections) for index in range(*span))


def _latency(messages: list[TrialMessage], pseudonymize: Pseudonymize) -> dict[str, object]:
    times: list[float] = []
    for _ in range(ROUNDS):
        for message in messages:
            started = time.perf_counter()
            pseudonymize(message["text"])
            times.append((time.perf_counter() - started) * 1000)
    return {
        "runs": len(times),
        "p50": round(statistics.median(times), 2),
        "p95": round(statistics.quantiles(times, n=100)[94], 2),
        "max": round(max(times), 2),
    }


def _peak_rss_mib() -> float:
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * RSS_UNIT_BYTES / 2**20, 1)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
