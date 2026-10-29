"""Fix RLS policy for relationships table (Blocker #2)

Revision ID: 007
Revises: 006
Create Date: 2026-10-28 00:00:00.000000

ISSUE: The existing RLS policy uses current_setting('app.current_tenant_id'),
which does not work in Supabase context because connection variables are not
set by the Supabase authentication layer.

SOLUTION: Replace with auth.jwt()->>'tenant_id', which extracts the tenant_id
claim from the authenticated JWT token. This is the Supabase-recommended
approach for tenant isolation with Row-Level Security.

REQUIREMENTS:
- JWT token must include 'tenant_id' claim (set by application during auth)
- RLS will enforce: SELECT/INSERT/UPDATE/DELETE only on rows matching tenant_id
"""
from alembic import op
import sqlalchemy as sa


revision = '007'
down_revision = '006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply fixed RLS policy using auth.jwt()->>'tenant_id'"""
    
    # Drop existing broken policy if it exists on relationships table
    op.execute('''
        DROP POLICY IF EXISTS "relationships_tenant_isolation"
        ON public.relationships
    ''')
    
    # Create new policy using auth.jwt() for tenant isolation on relationships
    op.execute('''
        CREATE POLICY "relationships_tenant_isolation"
        ON public.relationships
        FOR ALL
        TO anon, authenticated
        USING (tenant_id = auth.jwt()->>'tenant_id')
        WITH CHECK (tenant_id = auth.jwt()->>'tenant_id')
    ''')


def downgrade() -> None:
    """Revert to previous state (broken policy - for rollback only)"""
    
    # Drop the new policy
    op.execute('''
        DROP POLICY IF EXISTS "relationships_tenant_isolation"
        ON public.relationships
    ''')

