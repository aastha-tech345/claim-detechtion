"""Add filing_deadline column

Revision ID: 005
Revises: 004
Create Date: 2026-09-09 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '005'
down_revision = '004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'claim_diagnostics',
        sa.Column('filing_deadline', sa.DateTime(timezone=True), nullable=True),
        schema='public'
    )


def downgrade() -> None:
    op.drop_column('claim_diagnostics', 'filing_deadline', schema='public')
