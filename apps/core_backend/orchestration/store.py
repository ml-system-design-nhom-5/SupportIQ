import json
import sqlite3
from pathlib import Path
from typing import Optional, Dict, Any

class PersistentStore:
    """Thread-safe SQLite persistent store for decisions, idempotency, and escalation queues."""
    def __init__(self, db_path: Optional[str] = None):
        if db_path:
            self.db_path = Path(db_path)
        else:
            self.db_path = Path("tmp/orchestration.sqlite3")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS escalation_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    decision_id TEXT NOT NULL,
                    target_team TEXT NOT NULL,
                    target_queue TEXT NOT NULL,
                    reason_codes TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(run_id, decision_id)
                );
            """)
            conn.commit()

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        with self._get_conn() as conn:
            cur = conn.execute("SELECT payload_json FROM runs WHERE run_id = ?", (run_id,))
            row = cur.fetchone()
            if row:
                return json.loads(row["payload_json"])
        return None

    def save_run(self, run_id: str, result: Dict[str, Any]):
        with self._get_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO runs (run_id, payload_json) VALUES (?, ?)",
                (run_id, json.dumps(result))
            )
            conn.commit()

    def enqueue_escalation(self, run_id: str, decision_id: str, team: str, queue: str, reason_codes: list[str]):
        with self._get_conn() as conn:
            conn.execute("""
                INSERT OR IGNORE INTO escalation_queue (run_id, decision_id, target_team, target_queue, reason_codes)
                VALUES (?, ?, ?, ?, ?)
            """, (run_id, decision_id, team, queue, json.dumps(reason_codes)))
            conn.commit()
