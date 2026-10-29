"""Create audit_logs table for persistent audit trail (Blocker #3)

Revision ID: 008
Revises: 007
Create Date: 2026-10-28 00:00:00.000000

ISSUE: Audit events are currently logged to Python logger only (ephemeral).
Logs are lost on application restart, creating compliance and security gaps.

SOLUTION: Create audit_logs table in Supabase for durable persistence.
- Stores all security-relevant events (attempt, authorized, denied, success, failure)
- Includes actor, timestamp, action, resource, and outcome information
- Enforces tenant isolation via RLS policy
- Indexed for efficient querying by tenant and user
"""
from alembic import op
import sqlalchemy as sa


revision = '008'
down_revision = '007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create audit_logs table with RLS enforcement"""
    
    # Create audit_logs table
    op.execute('''
        CREATE TABLE IF NOT EXISTS public.audit_logs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            
            -- Identity context
            tenant_id TEXT NOT NULL,
            user_id TEXT,
            user_role TEXT,
            
            -- Event details
            event_type TEXT NOT NULL,
            timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            
            -- Operation context
            operation TEXT,
            resource_type TEXT,
            resource_id TEXT,
            
            -- Outcome
            status TEXT,
            reason TEXT,
            
            -- Additional context (JSONB for flexibility)
            details JSONB,
            
            -- Audit table metadata
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            
            -- Constraints
            CONSTRAINT fk_audit_tenant FOREIGN KEY (tenant_id)
                REFERENCES public.client_configurations(tenant_id)
                ON DELETE CASCADE,
            
            CONSTRAINT chk_event_type CHECK (event_type IN (
                'writeback_attempted',
                'writeback_authorized',
                'writeback_denied',
                'writeback_succeeded',
                'writeback_failed',
                'authorization_check',
                'role_check_passed',
                'role_check_failed'
            )),
            
            CONSTRAINT chk_status CHECK (status IN (
                'pending',
                'authorized',
                'denied',
                'succeeded',
                'failed'
            ))
        )
    ''')
    
    # Create indexes for efficient querying
    op.execute('''
        CREATE INDEX IF NOT EXISTS idx_audit_logs_tenant_timestamp
        ON public.audit_logs(tenant_id, timestamp DESC)
    ''')
    
    op.execute('''
        CREATE INDEX IF NOT EXISTS idx_audit_logs_user_timestamp
        ON public.audit_logs(user_id, timestamp DESC)
    ''')
    
    op.execute('''
        CREATE INDEX IF NOT EXISTS idx_audit_logs_event_type
        ON public.audit_logs(event_type, timestamp DESC)
    ''')
    
    # Enable Row Level Security
    op.execute('''
        ALTER TABLE public.audit_logs ENABLE ROW LEVEL SECURITY
    ''')
    
    # Create RLS policy: users can only read audit logs for their tenant
    op.execute('''
        CREATE POLICY "audit_logs_tenant_isolation"
        ON public.audit_logs
        FOR SELECT
        TO anon, authenticated
        USING (tenant_id = auth.jwt()->>'tenant_id')
    ''')
    
    # Create RLS policy: users cannot update audit logs
    op.execute('''
        CREATE POLICY "audit_logs_no_user_updates"
        ON public.audit_logs
        FOR UPDATE
        TO anon, authenticated
        USING (false)
    ''')
    
    # Create RLS policy: users cannot delete audit logs
    op.execute('''
        CREATE POLICY "audit_logs_no_user_deletes"
        ON public.audit_logs
        FOR DELETE
        TO anon, authenticated
        USING (false)
    ''')


def downgrade() -> None:
    """Drop audit_logs table and policies"""
    
    op.execute('''
        DROP TABLE IF EXISTS public.audit_logs CASCADE
    ''')
