#!/usr/bin/env python3
"""Initialize local SQLite database with schema and seed data."""
import sys
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine
from apps.backend.platform.database import Database
from apps.backend.seed import seed
LOCAL = ROOT / ".local"
LOCAL.mkdir(parents=True, exist_ok=True)

DB_PATH = LOCAL / "supportiq.db"
DB_URL = f"sqlite:///{DB_PATH}"

print(f"Initializing local SQLite database at: {DB_PATH}")
engine = create_engine(DB_URL)
db = Database(engine)
db.create_schema()

passwords = {
    "customer": "password123",
    "staff": "password123",
    "manager": "password123",
    "admin": "password123",
}

seed(db, passwords)

# Save credentials file for reference
credentials = {
    "database_url": DB_URL,
    "demo_accounts": {
        "customer": {"login": "customer-1", "password": "password123"},
        "staff": {"login": "staff-1", "password": "password123"},
        "manager": {"login": "manager-1", "password": "password123"},
        "admin": {"login": "admin-1", "password": "password123"},
    }
}
(LOCAL / "demo_credentials.json").write_text(json.dumps(credentials, indent=2))

print("✓ Database schema created and seeded successfully!")
print("Demo logins available (all use password: password123):")
print("  - Customer: customer-1")
print("  - Staff:    staff-1")
print("  - Manager:  manager-1")
print("  - Admin:    admin-1")
