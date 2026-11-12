import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Optional, Dict, Any, List, Generator

class DemoStore:
    """Persistent SQLite store for demo session submissions, feedback, and isolated history."""
    def __init__(self, db_path: Optional[str] = None):
        if db_path:
            self.db_path = Path(db_path)
        else:
            self.db_path = Path("tmp/demo.sqlite3")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _connection(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self):
        with self._connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS demo_submissions (
                    submission_id TEXT PRIMARY KEY,
                    fingerprint TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS demo_feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    draft_hash TEXT NOT NULL,
                    edited_text TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.commit()

    def get_submission(self, submission_id: str) -> Optional[Dict[str, Any]]:
        with self._connection() as conn:
            cur = conn.execute("SELECT * FROM demo_submissions WHERE submission_id = ?", (submission_id,))
            row = cur.fetchone()
            if row:
                return {
                    "submission_id": row["submission_id"],
                    "fingerprint": row["fingerprint"],
                    "run_id": row["run_id"],
                    "session_id": row["session_id"],
                    "result": json.loads(row["result_json"]),
                }
        return None

    def save_submission(self, submission_id: str, fingerprint: str, run_id: str, session_id: str, result: Dict[str, Any]):
        with self._connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO demo_submissions (submission_id, fingerprint, run_id, session_id, result_json)
                VALUES (?, ?, ?, ?, ?)
            """, (submission_id, fingerprint, run_id, session_id, json.dumps(result)))
            conn.commit()

    def update_submission_result(self, run_id: str, result: Dict[str, Any]):
        with self._connection() as conn:
            conn.execute("UPDATE demo_submissions SET result_json = ? WHERE run_id = ?", (json.dumps(result), run_id))
            conn.commit()

    def record_feedback(self, run_id: str, session_id: str, action: str, draft_hash: str, edited_text: Optional[str] = None):
        with self._connection() as conn:
            conn.execute("""
                INSERT INTO demo_feedback (run_id, session_id, action, draft_hash, edited_text)
                VALUES (?, ?, ?, ?, ?)
            """, (run_id, session_id, action, draft_hash, edited_text))
            conn.commit()

    def get_feedbacks(self, run_id: str) -> List[Dict[str, Any]]:
        with self._connection() as conn:
            cur = conn.execute("SELECT * FROM demo_feedback WHERE run_id = ? ORDER BY id ASC", (run_id,))
            rows = cur.fetchall()
            return [
                {
                    "id": r["id"],
                    "run_id": r["run_id"],
                    "session_id": r["session_id"],
                    "action": r["action"],
                    "draft_hash": r["draft_hash"],
                    "edited_text": r["edited_text"],
                    "created_at": r["created_at"]
                }
                for r in rows
            ]

    def get_history(self, session_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        with self._connection() as conn:
            cur = conn.execute("""
                SELECT submission_id, run_id, result_json, created_at
                FROM demo_submissions
                WHERE session_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (session_id, limit))
            rows = cur.fetchall()
            return [
                {
                    "submission_id": r["submission_id"],
                    "run_id": r["run_id"],
                    "created_at": r["created_at"],
                    "result": json.loads(r["result_json"])
                }
                for r in rows
            ]
