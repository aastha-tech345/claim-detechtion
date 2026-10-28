"""Create relationships table for E3 transaction lifecycle tracking.

Revision ID: 006
Revises: 005_add_filing_deadline
Create Date: 2026-10-27 16:45:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '006'
down_revision = '005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create relationships table for E3 relationship tracking."""
    op.create_table(
        'relationships',
        sa.Column('id', sa.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', sa.String(255), nullable=False),
        sa.Column('from_type', sa.String(50), nullable=False),
        sa.Column('from_id', sa.String(255), nullable=False),
        sa.Column('to_type', sa.String(50), nullable=False),
        sa.Column('to_id', sa.String(255), nullable=False),
        sa.Column('relationship_state', sa.String(50), nullable=False),
        sa.Column('evidence', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
    )
    
    # Create indexes for common lookups
    op.create_index('relationships_tenant_id_idx', 'relationships', ['tenant_id'])
    op.create_index('relationships_from_id_idx', 'relationships', ['from_id'])
    op.create_index('relationships_to_id_idx', 'relationships', ['to_id'])
    op.create_index('relationships_state_idx', 'relationships', ['relationship_state'])
    op.create_index('relationships_from_to_idx', 'relationships', ['from_type', 'to_type'])


def downgrade() -> None:
    """Drop relationships table."""
    op.drop_index('relationships_from_to_idx', table_name='relationships')
    op.drop_index('relationships_state_idx', table_name='relationships')
    op.drop_index('relationships_to_id_idx', table_name='relationships')
    op.drop_index('relationships_from_id_idx', table_name='relationships')
    op.drop_index('relationships_tenant_id_idx', table_name='relationships')
    op.drop_table('relationships')

