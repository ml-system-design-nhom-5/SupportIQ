"""Explicit migration and seed entry point; never called by backend replicas."""

import argparse
import json
from pathlib import Path

from sqlalchemy import create_engine, text

from .platform.database import Database
from .seed import seed


def initialize():
    from alembic import command
    from alembic.config import Config

    root = Path(__file__).resolve().parents[2]
    local = json.loads((root / ".local/application.json").read_text())
    engine = create_engine(local["database_url_owner"], hide_parameters=True)
    config = Config(str(root / "apps/backend/alembic.ini"))
    config.set_main_option("script_location", str(root / "apps/backend/migrations"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
        connection.execute(text("GRANT USAGE ON SCHEMA public TO supportiq_app"))
        connection.execute(text("GRANT SELECT ON accounts, products, orders, tickets, customer_messages, suggestions, audit_log_entries TO supportiq_app"))
        connection.execute(text("GRANT SELECT, INSERT, UPDATE, DELETE ON sessions, sign_in_failures, idempotency_records, suggestion_jobs TO supportiq_app"))
        connection.execute(text("GRANT INSERT ON orders, tickets, customer_messages, suggestions, audit_log_entries TO supportiq_app"))
        connection.execute(text("GRANT UPDATE (role, is_active, display_name, email, phone, address, avatar_data_url) ON accounts TO supportiq_app"))
        connection.execute(text("GRANT UPDATE (payload) ON orders TO supportiq_app"))
        connection.execute(text("GRANT UPDATE (status, is_authority_required, handling_started_at, closed_at, current_suggestion_id, proposal, escalation, reply) ON tickets TO supportiq_app"))
        connection.execute(text("GRANT UPDATE (payload, completed_at) ON suggestions TO supportiq_app"))
        connection.execute(text("GRANT USAGE ON SEQUENCE ticket_number_seq TO supportiq_app"))
    seed(Database(engine), local["passwords"])
    engine.dispose()
    print("Application migrations and synthetic order import complete. Login names: customer-1, staff-1, manager-1, admin-1.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["initialize"])
    parser.parse_args()
    initialize()
