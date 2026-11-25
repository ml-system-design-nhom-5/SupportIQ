"""The statement that empties every table of the backend schema, for reset (SEC-32).

Integration tests compare the tables of a migrated database with this statement, so a migration
that adds a table also adds it here, and reset never leaves it behind.
"""

# One statement, so every table empties at once despite the foreign keys. RESTART IDENTITY
# restarts `ticket_number_seq`, which belongs to `tickets.ticket_number`. TRUNCATE fires no
# UPDATE or DELETE trigger, so the audit log trigger allows it; supportiq_app has no TRUNCATE
# privilege, so only the owner can run it (SEC-39).
TRUNCATE_EVERY_TABLE = (
    "TRUNCATE TABLE accounts, sessions, sign_in_failures, idempotency_records, customers, "
    "products, orders, order_lines, shipments, refunds, tickets, customer_messages, "
    "audit_log_entries, suggestions, suggestion_parts, suggestion_jobs, pseudonym_map_entries, "
    "reply_proposals, replies, escalations, staff_decisions RESTART IDENTITY"
)
