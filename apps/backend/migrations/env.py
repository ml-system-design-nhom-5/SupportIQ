from alembic import context


def run_migrations():
    connection = context.config.attributes.get("connection")
    if connection is None:
        raise RuntimeError("Use python -m apps.backend.manage initialize to supply the owner connection")
    context.configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()


run_migrations()
