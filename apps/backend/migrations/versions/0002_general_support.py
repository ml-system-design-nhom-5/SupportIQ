"""Allow customer support requests without an order, as requested by the user."""
from alembic import op
import sqlalchemy as sa

revision = '0002_general_support'
down_revision = '0001_application'

def upgrade():
    op.alter_column('tickets', 'order_id', existing_type=sa.String(), nullable=True)

def downgrade():
    # Refuse rather than delete general-support tickets during downgrade.
    op.alter_column('tickets', 'order_id', existing_type=sa.String(), nullable=False)
