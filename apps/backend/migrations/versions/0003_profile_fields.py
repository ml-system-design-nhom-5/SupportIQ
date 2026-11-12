"""Persist editable contact information and avatar in the account record."""
from alembic import op
import sqlalchemy as sa

revision = '0003_profile_fields'
down_revision = '0002_general_support'

def upgrade():
    # Initial metadata also contains these columns for fresh installations.
    columns={column['name'] for column in sa.inspect(op.get_bind()).get_columns('accounts')}
    for name in ('email','phone','address','avatar_data_url'):
        if name not in columns:
            op.add_column('accounts',sa.Column(name,sa.Text(),nullable=True))

def downgrade():
    for name in ('avatar_data_url','address','phone','email'):
        op.drop_column('accounts',name)
