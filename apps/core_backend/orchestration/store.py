import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Optional, Dict, Any, Generator

class PersistentStore:
    """Thread-safe SQLite persistent store with guaranteed connection closure and atomic transactions."""
    def __init__(self, db_path: Optional[str] = None):
        if db_path:
            self.db_path = Path(db_path)
        else:
            self.db_path = Path("tmp/orchestration.sqlite3")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager that guarantees connection is closed after use."""
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA busy_timeout = 5000;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self):
        with self._connection() as conn:
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
                    run_id TEXT NOT NULL UNIQUE,
                    decision_id TEXT NOT NULL,
                    target_team TEXT NOT NULL,
                    target_queue TEXT NOT NULL,
                    reason_codes TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS llm_inputs (
                    run_id TEXT PRIMARY KEY,
                    snapshot_json TEXT NOT NULL
                );
            """)
            conn.commit()

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        with self._connection() as conn:
            cur = conn.execute("SELECT payload_json FROM runs WHERE run_id = ?", (run_id,))
            row = cur.fetchone()
            if row:
                return json.loads(row["payload_json"])
        return None

    def save_input_snapshot(self, run_id: str, snapshot: dict) -> None:
        """Persist sanitized evidence before egress, including failed LLM attempts."""
        with self._connection() as conn:
            conn.execute('INSERT OR IGNORE INTO llm_inputs VALUES (?, ?)',
                         (run_id, json.dumps(snapshot, ensure_ascii=False)))

    def save_run_and_escalate_atomic(
        self,
        run_id: str,
        result: Dict[str, Any],
        escalate_info: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Atomically persist run and enqueue escalation in a single transaction.
        If run_id already exists, rolls back and returns False (idempotent rejection).
        """
        with self._connection() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                # Check existence
                cur = conn.execute("SELECT run_id FROM runs WHERE run_id = ?", (run_id,))
                if cur.fetchone():
                    conn.rollback()
                    return False

                # Insert run
                conn.execute(
                    "INSERT INTO runs (run_id, payload_json) VALUES (?, ?)",
                    (run_id, json.dumps(result))
                )

                # Insert escalation queue if applicable
                if escalate_info:
                    conn.execute("""
                        INSERT INTO escalation_queue (run_id, decision_id, target_team, target_queue, reason_codes)
                        VALUES (?, ?, ?, ?, ?)
                    """, (
                        run_id,
                        escalate_info["decision_id"],
                        escalate_info["target_team"],
                        escalate_info["target_queue"],
                        json.dumps(escalate_info["reason_codes"])
                    ))

                conn.commit()
                return True
            except Exception:
                conn.rollback()
                raise

    def enqueue_escalation(
        self,
        run_id: str,
        decision_id: str,
        target_team: str,
        target_queue: str,
        reason_codes: list
    ) -> bool:
        with self._connection() as conn:
            try:
                conn.execute("""
                    INSERT OR IGNORE INTO escalation_queue (run_id, decision_id, target_team, target_queue, reason_codes)
                    VALUES (?, ?, ?, ?, ?)
                """, (run_id, decision_id, target_team, target_queue, json.dumps(reason_codes)))
                conn.commit()
                return True
            except Exception:
                conn.rollback()
                return False
