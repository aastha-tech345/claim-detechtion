"""Create claim_diagnostics table

Revision ID: 001
Revises: 
Create Date: 2026-09-06 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create claim_diagnostics table
    op.create_table(
        'claim_diagnostics',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('token_id', sa.Text(), nullable=False),
        sa.Column('waterfall_stage', sa.Text(), nullable=False),
        sa.Column('deadlock_types', sa.ARRAY(sa.Text()), nullable=False, server_default='{}'),
        sa.Column('active_hold_names', sa.ARRAY(sa.Text()), nullable=False, server_default='{}'),
        sa.Column('eligible_wq_ids', sa.ARRAY(sa.Text()), nullable=False, server_default='{}'),
        sa.Column('unassigned_wq_ids', sa.ARRAY(sa.Text()), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        schema='public'
    )
    
    # Create index
    op.create_index('claim_diagnostics_token_id_idx', 'claim_diagnostics', ['token_id'], schema='public')


def downgrade() -> None:
    op.drop_index('claim_diagnostics_token_id_idx', table_name='claim_diagnostics', schema='public')
    op.drop_table('claim_diagnostics', schema='public')
