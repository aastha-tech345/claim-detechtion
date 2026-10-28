-- E3: Transaction relationship persistence
-- Stores explicit relationships between healthcare transactions (encounter → charge → claim → ack → remittance)
-- Supports lifecycle reconstruction and unresolved relationship quarantine.

CREATE TABLE IF NOT EXISTS public.relationships (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id varchar(255) NOT NULL,
    from_type varchar(50) NOT NULL,  -- "encounter", "charge", "claim", "acknowledgment", "remittance"
    from_id varchar(255) NOT NULL,
    to_type varchar(50) NOT NULL,
    to_id varchar(255) NOT NULL,
    relationship_state varchar(50) NOT NULL,  -- "accepted", "rejected", "unresolved"
    evidence jsonb,  -- Array of evidence objects: [{"evidence_type": "...", "evidence_value": "...", "source": "...", "confidence_score": 0.99}]
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS relationships_tenant_id_idx ON public.relationships(tenant_id);
CREATE INDEX IF NOT EXISTS relationships_from_id_idx ON public.relationships(from_id);
CREATE INDEX IF NOT EXISTS relationships_to_id_idx ON public.relationships(to_id);
CREATE INDEX IF NOT EXISTS relationships_state_idx ON public.relationships(relationship_state);
CREATE INDEX IF NOT EXISTS relationships_from_to_idx ON public.relationships(from_type, to_type);

-- Enable RLS
ALTER TABLE public.relationships ENABLE ROW LEVEL SECURITY;

-- RLS policy: tenants can only see their own relationships
CREATE POLICY relationships_tenant_isolation ON public.relationships
    USING (tenant_id = current_setting('app.current_tenant_id', true)::text);

