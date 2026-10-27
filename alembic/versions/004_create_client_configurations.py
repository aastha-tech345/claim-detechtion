"""Create client_configurations table

Revision ID: 004
Revises: 003
Create Date: 2026-09-07 02:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'client_configurations',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('tenant_id', sa.VARCHAR(255), nullable=False, unique=True),
        sa.Column('organization_name', sa.VARCHAR(255), nullable=False),
        sa.Column('epic_client_id', sa.VARCHAR(255), nullable=True),
        sa.Column('epic_fhir_base_url', sa.Text(), nullable=True),
        sa.Column('ingestion_mode', sa.VARCHAR(50), nullable=False, server_default='etl_batch'),
        sa.Column('dollar_threshold_default', sa.Numeric(), nullable=False, server_default='500.00'),
        sa.Column('is_onboarding_completed', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        schema='public'
    )
    
    # Enable RLS
    op.execute('ALTER TABLE public.client_configurations ENABLE ROW LEVEL SECURITY')
    
    # Create tenant isolation policy
    op.execute('''
        CREATE POLICY client_config_tenant_isolation ON public.client_configurations
        FOR ALL
        USING (tenant_id = current_setting('request.jwt.claims', true)::json->>'tenant_id')
    ''')


def downgrade() -> None:
    op.execute('DROP POLICY IF EXISTS client_config_tenant_isolation ON public.client_configurations')
    op.drop_table('client_configurations', schema='public')
