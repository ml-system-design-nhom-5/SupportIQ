"""Enforce relational foreign key constraints and check constraints."""
from alembic import op
import sqlalchemy as sa

revision = '0004_relational_constraints'
down_revision = '0003_profile_fields'


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_fks = {fk.get('name') for fk in inspector.get_foreign_keys('tickets')}
    if 'fk_tickets_current_suggestion_id' not in existing_fks:
        op.create_foreign_key(
            'fk_tickets_current_suggestion_id',
            'tickets',
            'suggestions',
            ['current_suggestion_id'],
            ['suggestion_id'],
            ondelete='SET NULL',
            use_alter=True
        )


def downgrade():
    op.drop_constraint('fk_tickets_current_suggestion_id', 'tickets', type_='foreignkey')
