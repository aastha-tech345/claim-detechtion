"""Enable RLS on claim_diagnostics

Revision ID: 002
Revises: 001
Create Date: 2026-09-07 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable RLS
    op.execute('ALTER TABLE public.claim_diagnostics ENABLE ROW LEVEL SECURITY')
    
    # Create read-only policy for dashboard
    op.execute('''
        CREATE POLICY "Allow read-only access for dashboard"
        ON public.claim_diagnostics
        FOR SELECT
        TO anon, authenticated
        USING (true)
    ''')


def downgrade() -> None:
    op.execute('DROP POLICY IF EXISTS "Allow read-only access for dashboard" ON public.claim_diagnostics')
    op.execute('ALTER TABLE public.claim_diagnostics DISABLE ROW LEVEL SECURITY')
