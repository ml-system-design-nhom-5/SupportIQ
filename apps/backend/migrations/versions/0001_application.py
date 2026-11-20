"""Application records, immutable messages, append-only audit and sticky authority."""
from alembic import op

revision = "0001_application"
down_revision = None


def upgrade():
    from apps.backend.platform.database import Database
    connection = op.get_bind()
    Database(connection.engine).create_schema(connection=connection)


def downgrade():
    from apps.backend.platform.models import Base
    Base.metadata.drop_all(op.get_bind())
    op.execute("DROP SEQUENCE IF EXISTS ticket_number_seq")
    for name in ("protect_audit", "protect_authority", "protect_account_role"):
        op.execute(f"DROP FUNCTION IF EXISTS {name}()")
