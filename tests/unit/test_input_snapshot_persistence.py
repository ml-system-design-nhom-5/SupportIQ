import json
import sqlite3

from apps.core_backend.orchestration.store import PersistentStore


def test_input_snapshot_survives_reopen_and_duplicate_preserves_original(tmp_path):
    path = tmp_path / "store.sqlite3"
    store = PersistentStore(str(path))
    original = {"sources": [{"source_id": "S1", "excerpt": "Approved policy"}]}
    store.save_input_snapshot("run-1", original)
    store.save_input_snapshot("run-1", {"sources": []})

    reopened = PersistentStore(str(path))
    with sqlite3.connect(reopened.db_path) as connection:
        rows = connection.execute("SELECT run_id, snapshot_json FROM llm_inputs").fetchall()

    assert len(rows) == 1
    assert rows[0][0] == "run-1"
    assert json.loads(rows[0][1]) == original


def test_init_db_creates_llm_inputs_schema(tmp_path):
    path = tmp_path / "init_only.sqlite3"
    PersistentStore(str(path))
    with sqlite3.connect(path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    assert {"runs", "escalation_queue", "llm_inputs"} <= tables
